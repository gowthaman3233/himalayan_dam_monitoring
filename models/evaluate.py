"""Segmentation metrics: per-class IoU, Dice, precision, recall, F1.

Brief, Section 7.5: report per-class IoU, Dice, precision, recall, F1 and a
confusion matrix, **report the water-vs-shadow confusion explicitly**, and
**do not rely on overall accuracy**.

Why overall accuracy is refused, not merely discouraged
-------------------------------------------------------
This project's classes are wildly imbalanced. Over the default AOI, water is
about 4% of valid pixels and terrain shadow about 9%; a model that predicted
"land" everywhere would score roughly 87% accuracy while finding not one lake.
Reporting that number beside the real metrics would invite exactly the wrong
conclusion, so :func:`evaluate` does not compute it. :func:`overall_accuracy`
exists, is documented as misleading here, and must be called deliberately.

Why water-vs-shadow gets its own treatment
------------------------------------------
It is the confusion this project exists to fix, and a macro-averaged F1 hides
it: a model can score well overall while systematically calling shadowed rock
"water", because shadow is a small class and the error is symmetric in the
averages. :func:`water_shadow_confusion` pulls that one 2x2 block out and
reports it on its own.

No torch dependency
-------------------
Everything here operates on integer label arrays, so metrics can be computed,
tested and reported without PyTorch installed -- which matters because the
models are trained on Colab while results are read locally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from utils.logging import get_logger

log = get_logger(__name__)

#: Brief, Section 7.5. The same codes the Phase 4 fusion emits, so a
#: rule-based map and a model prediction are directly comparable.
CLASS_LAND = 0
CLASS_WATER = 1
CLASS_LANDSLIDE = 2
CLASS_TERRAIN_SHADOW = 3
CLASS_SNOW_ICE = 4

CLASS_NAMES = {
    CLASS_LAND: "background/land",
    CLASS_WATER: "water",
    CLASS_LANDSLIDE: "landslide/bare debris",
    CLASS_TERRAIN_SHADOW: "terrain shadow",
    CLASS_SNOW_ICE: "snow/ice",
}

#: Label for pixels excluded from evaluation (unlabelled, cloud, nodata).
IGNORE_INDEX = 255


@dataclass(frozen=True)
class ClassMetrics:
    """Metrics for one class. ``None`` where the class is absent entirely."""

    class_id: int
    name: str
    support: int
    predicted: int
    true_positive: int
    false_positive: int
    false_negative: int

    @property
    def present(self) -> bool:
        """Whether the class occurs in the reference at all.

        A class absent from the reference has no recall to report, and
        averaging a fabricated 0 or 1 for it would distort every summary.
        """
        return self.support > 0

    @property
    def iou(self) -> float | None:
        denominator = self.true_positive + self.false_positive + self.false_negative
        return float(self.true_positive / denominator) if denominator else None

    @property
    def dice(self) -> float | None:
        denominator = 2 * self.true_positive + self.false_positive + self.false_negative
        return float(2 * self.true_positive / denominator) if denominator else None

    @property
    def precision(self) -> float | None:
        return (
            float(self.true_positive / self.predicted) if self.predicted else None
        )

    @property
    def recall(self) -> float | None:
        return float(self.true_positive / self.support) if self.support else None

    @property
    def f1(self) -> float | None:
        precision, recall = self.precision, self.recall
        if precision is None or recall is None or (precision + recall) == 0:
            return None
        return float(2 * precision * recall / (precision + recall))

    def as_dict(self) -> dict[str, Any]:
        return {
            "class_id": self.class_id,
            "name": self.name,
            "support": self.support,
            "predicted": self.predicted,
            "iou": self.iou,
            "dice": self.dice,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


@dataclass(frozen=True)
class ConfusionPair:
    """How two classes are confused, in both directions."""

    a: int
    b: int
    a_name: str
    b_name: str
    a_as_b: int
    b_as_a: int
    a_support: int
    b_support: int

    @property
    def a_as_b_rate(self) -> float | None:
        return float(self.a_as_b / self.a_support) if self.a_support else None

    @property
    def b_as_a_rate(self) -> float | None:
        return float(self.b_as_a / self.b_support) if self.b_support else None

    def describe(self) -> str:
        def rate(value: float | None) -> str:
            return f"{value:.1%}" if value is not None else "n/a"

        return (
            f"{self.a_name} predicted as {self.b_name}: {self.a_as_b} px "
            f"({rate(self.a_as_b_rate)} of {self.a_name}); "
            f"{self.b_name} predicted as {self.a_name}: {self.b_as_a} px "
            f"({rate(self.b_as_a_rate)} of {self.b_name})"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "a": self.a_name,
            "b": self.b_name,
            "a_as_b": self.a_as_b,
            "b_as_a": self.b_as_a,
            "a_as_b_rate": self.a_as_b_rate,
            "b_as_a_rate": self.b_as_a_rate,
        }


@dataclass
class Evaluation:
    """A complete evaluation. Deliberately has no ``accuracy`` attribute."""

    confusion: np.ndarray
    per_class: list[ClassMetrics]
    class_ids: list[int]
    evaluated_pixels: int
    ignored_pixels: int
    water_shadow: ConfusionPair | None = None
    notes: list[str] = field(default_factory=list)

    def metrics_for(self, class_id: int) -> ClassMetrics | None:
        return next((m for m in self.per_class if m.class_id == class_id), None)

    def present_classes(self) -> list[ClassMetrics]:
        return [m for m in self.per_class if m.present]

    def macro(self, metric: str) -> float | None:
        """Mean of a metric over classes **present in the reference**.

        Absent classes are excluded rather than scored zero: a class that does
        not occur cannot be got right or wrong, and including it would move
        the average for a reason unrelated to performance.
        """
        values = [
            getattr(m, metric)
            for m in self.present_classes()
            if getattr(m, metric) is not None
        ]
        return float(sum(values) / len(values)) if values else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluated_pixels": self.evaluated_pixels,
            "ignored_pixels": self.ignored_pixels,
            "per_class": [m.as_dict() for m in self.per_class],
            "macro_iou": self.macro("iou"),
            "macro_dice": self.macro("dice"),
            "macro_f1": self.macro("f1"),
            "confusion": self.confusion.tolist(),
            "class_ids": list(self.class_ids),
            "water_vs_shadow": self.water_shadow.as_dict() if self.water_shadow else None,
            "notes": list(self.notes),
            "accuracy_note": (
                "Overall accuracy is deliberately not reported: with water at "
                "a few percent of pixels, predicting 'land' everywhere scores "
                "~87% while finding no lakes (brief, Section 7.5)."
            ),
        }

    def report(self) -> str:
        """A readable summary, water-vs-shadow called out separately."""
        header = (
            f"{'class':24s} {'support':>9s} {'IoU':>7s} {'Dice':>7s} "
            f"{'prec':>7s} {'recall':>7s} {'F1':>7s}"
        )
        lines = [header, "-" * len(header)]

        def fmt(value: float | None) -> str:
            return f"{value:7.3f}" if value is not None else "      -"

        for metrics in self.per_class:
            lines.append(
                f"{metrics.name:24s} {metrics.support:9d} {fmt(metrics.iou)} "
                f"{fmt(metrics.dice)} {fmt(metrics.precision)} "
                f"{fmt(metrics.recall)} {fmt(metrics.f1)}"
            )
        lines.append("-" * len(header))
        lines.append(
            f"{'macro (present classes)':24s} {'':9s} {fmt(self.macro('iou'))} "
            f"{fmt(self.macro('dice'))} {'':7s} {'':7s} {fmt(self.macro('f1'))}"
        )
        if self.water_shadow is not None:
            lines.append("")
            lines.append("water vs terrain shadow (brief, Section 7.5):")
            lines.append(f"  {self.water_shadow.describe()}")
        lines.extend(f"  note: {n}" for n in self.notes)
        return "\n".join(lines)


def confusion_matrix(
    reference: np.ndarray,
    prediction: np.ndarray,
    class_ids: Sequence[int],
    *,
    ignore_index: int = IGNORE_INDEX,
) -> tuple[np.ndarray, int, int]:
    """Rows are reference classes, columns predicted.

    Returns ``(matrix, evaluated, ignored)``. Pixels whose reference is
    ``ignore_index``, or whose reference or prediction falls outside
    ``class_ids``, are excluded and counted -- never silently folded into a
    class they do not belong to.
    """
    truth = np.asarray(reference).ravel()
    predicted = np.asarray(prediction).ravel()
    if truth.shape != predicted.shape:
        raise ValueError(
            f"reference and prediction differ in size: {truth.shape} vs "
            f"{predicted.shape}"
        )

    ids = list(class_ids)
    index = {class_id: position for position, class_id in enumerate(ids)}

    keep = truth != ignore_index
    keep &= np.isin(truth, ids)
    keep &= np.isin(predicted, ids)

    matrix = np.zeros((len(ids), len(ids)), dtype=np.int64)
    for truth_value, predicted_value in zip(truth[keep], predicted[keep]):
        matrix[index[int(truth_value)], index[int(predicted_value)]] += 1

    return matrix, int(keep.sum()), int(truth.size - keep.sum())


def overall_accuracy(evaluation: Evaluation) -> float:
    """Overall accuracy -- **misleading for this project's class balance**.

    Kept out of :class:`Evaluation` on purpose and provided here so that
    anyone reporting it has to reach for it deliberately. With water at a few
    percent of pixels, predicting "land" everywhere scores around 87% while
    detecting nothing (brief, Section 7.5: "Do not rely on overall accuracy").
    """
    total = evaluation.confusion.sum()
    return float(np.trace(evaluation.confusion) / total) if total else 0.0


def water_shadow_confusion(
    matrix: np.ndarray, class_ids: Sequence[int]
) -> ConfusionPair | None:
    """The water/terrain-shadow block, pulled out and reported on its own.

    ``None`` when either class is missing from ``class_ids``.
    """
    ids = list(class_ids)
    if CLASS_WATER not in ids or CLASS_TERRAIN_SHADOW not in ids:
        return None
    water = ids.index(CLASS_WATER)
    shadow = ids.index(CLASS_TERRAIN_SHADOW)
    return ConfusionPair(
        a=CLASS_WATER,
        b=CLASS_TERRAIN_SHADOW,
        a_name=CLASS_NAMES[CLASS_WATER],
        b_name=CLASS_NAMES[CLASS_TERRAIN_SHADOW],
        a_as_b=int(matrix[water, shadow]),
        b_as_a=int(matrix[shadow, water]),
        a_support=int(matrix[water].sum()),
        b_support=int(matrix[shadow].sum()),
    )


def evaluate(
    reference: np.ndarray,
    prediction: np.ndarray,
    *,
    class_ids: Sequence[int] | None = None,
    ignore_index: int = IGNORE_INDEX,
) -> Evaluation:
    """Per-class metrics, the confusion matrix and the water/shadow block.

    Args:
        reference: integer labels. ``ignore_index`` marks pixels to exclude.
        prediction: integer labels on the same grid.
        class_ids: defaults to all five classes of Section 7.5, so a class the
            model never predicted still appears in the report with zero
            recall rather than vanishing from it.
    """
    ids = list(class_ids) if class_ids is not None else sorted(CLASS_NAMES)
    matrix, evaluated, ignored = confusion_matrix(
        reference, prediction, ids, ignore_index=ignore_index
    )

    per_class: list[ClassMetrics] = []
    for position, class_id in enumerate(ids):
        true_positive = int(matrix[position, position])
        support = int(matrix[position].sum())
        predicted = int(matrix[:, position].sum())
        per_class.append(
            ClassMetrics(
                class_id=class_id,
                name=CLASS_NAMES.get(class_id, f"class {class_id}"),
                support=support,
                predicted=predicted,
                true_positive=true_positive,
                false_positive=predicted - true_positive,
                false_negative=support - true_positive,
            )
        )

    notes: list[str] = []
    absent = [m.name for m in per_class if not m.present]
    if absent:
        notes.append(
            f"absent from the reference, excluded from the macro averages: "
            f"{', '.join(absent)}"
        )
    if ignored:
        notes.append(f"{ignored} pixel(s) ignored (unlabelled, cloud or out of range)")

    evaluation = Evaluation(
        confusion=matrix,
        per_class=per_class,
        class_ids=ids,
        evaluated_pixels=evaluated,
        ignored_pixels=ignored,
        water_shadow=water_shadow_confusion(matrix, ids),
        notes=notes,
    )
    log.info(
        "evaluated %d px over %d class(es); macro IoU %s",
        evaluated,
        len(evaluation.present_classes()),
        f"{evaluation.macro('iou'):.3f}" if evaluation.macro("iou") is not None else "n/a",
    )
    return evaluation


def compare(
    evaluations: dict[str, Evaluation], *, metric: str = "iou"
) -> dict[str, Any]:
    """Compare models class by class -- the brief's required result.

    Section 7.5 makes the plain U-Net vs Attention U-Net comparison a required
    output. This returns it per class rather than as a single headline number,
    because the interesting difference is expected in the small classes
    (water, shadow) that a macro average flattens.
    """
    names = list(evaluations)
    class_ids = sorted({c for e in evaluations.values() for c in e.class_ids})

    table: dict[str, dict[str, float | None]] = {}
    for class_id in class_ids:
        row: dict[str, float | None] = {}
        for name in names:
            metrics = evaluations[name].metrics_for(class_id)
            row[name] = getattr(metrics, metric) if metrics else None
        table[CLASS_NAMES.get(class_id, f"class {class_id}")] = row

    water_shadow = {
        name: evaluation.water_shadow.as_dict() if evaluation.water_shadow else None
        for name, evaluation in evaluations.items()
    }
    return {
        "metric": metric,
        "models": names,
        "per_class": table,
        "macro": {n: e.macro(metric) for n, e in evaluations.items()},
        "water_vs_shadow": water_shadow,
        "note": (
            "Compared per class on purpose: the difference between these "
            "models is expected in the small classes, which a macro average "
            "flattens."
        ),
    }
