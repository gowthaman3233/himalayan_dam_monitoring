"""The per-site answers the dashboard must give.

Brief, Section 14 lists eleven questions the dashboard must answer for every
site. This module assembles those answers from the database and the analysis
objects, as plain data -- no Streamlit, no Folium, no rendering.

That separation is deliberate. The answers are where the project's integrity
rules have to survive contact with a user interface: "unavailable" must not
render as a blank, a gap must not render as zero, and a NORMAL level built on
a tenth of the evidence must not render as a green tick. Keeping them in
plain dataclasses means they can be tested without a browser, and the
rendering layer has no opportunity to quietly reinterpret them.

Every answer carries its ``value_type`` from the Section 10 vocabulary, so the
dashboard can show -- as Section 14 requires -- which values are observed,
classified, estimated or unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from utils.logging import get_logger

log = get_logger(__name__)

#: Section 14's first question is explicitly three-valued.
WATER_YES = "Yes"
WATER_NO = "No"
WATER_UNCERTAIN = "Uncertain"

#: Shown wherever a quantity could not be determined. Never an empty cell: a
#: blank reads as "nothing to report", which is a different claim.
UNAVAILABLE_TEXT = "Unavailable"


@dataclass(frozen=True)
class Answer:
    """One question, its answer, and how much weight the answer carries."""

    question: str
    value: str
    value_type: str = "derived"
    detail: str | None = None
    caveat: str | None = None

    @property
    def available(self) -> bool:
        return self.value_type != "unavailable"

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "value": self.value,
            "value_type": self.value_type,
            "detail": self.detail,
            "caveat": self.caveat,
        }


@dataclass
class SiteView:
    """Everything the dashboard shows for one site."""

    site_code: str
    site_type: str
    answers: list[Answer] = field(default_factory=list)
    disclaimer: str = ""

    def answer(self, question: str) -> Answer | None:
        return next((a for a in self.answers if a.question == question), None)

    def unavailable_answers(self) -> list[Answer]:
        return [a for a in self.answers if not a.available]

    def as_dicts(self) -> list[dict[str, Any]]:
        return [a.as_dict() for a in self.answers]


def water_verdict(
    p_water: float | None,
    p_terrain_shadow: float | None,
    *,
    uncertain: bool = False,
) -> tuple[str, str | None]:
    """Section 14's "Is there water here (Yes / No / Uncertain)?".

    Three-valued on purpose. A pixel the fusion could not decide is
    ``Uncertain``, not ``No`` -- the brief asks for the distinction and
    collapsing it would hide exactly the cases a reviewer should look at.
    """
    if p_water is None:
        return WATER_UNCERTAIN, "no fused probability available"
    if uncertain:
        return WATER_UNCERTAIN, "classified below the confidence threshold"
    if p_terrain_shadow is not None and p_terrain_shadow > p_water:
        return WATER_NO, "terrain shadow is the more probable explanation"
    return (WATER_YES, None) if p_water >= 0.5 else (WATER_NO, None)


def build_site_view(
    *,
    site: dict[str, Any],
    disclaimer: str,
    p_water: float | None = None,
    p_terrain_shadow: float | None = None,
    water_uncertain: bool = False,
    landslide_event: dict[str, Any] | None = None,
    blockage: dict[str, Any] | None = None,
    barrier_lake: dict[str, Any] | None = None,
    latest_observation: dict[str, Any] | None = None,
    depth_estimate: dict[str, Any] | None = None,
    trend: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
    sources: list[str] | None = None,
) -> SiteView:
    """Assemble the Section 14 answers for one site.

    Every argument is optional, because in practice most will be missing: a
    site with no blockage has no blockage confidence, a Branch B lake has no
    volume, and a cloudy window has no observation. Each absent input becomes
    an explicit ``Unavailable`` answer with a reason rather than a gap in the
    table.
    """
    answers: list[Answer] = []

    # 1. Is there water here?
    verdict, why = water_verdict(p_water, p_terrain_shadow, uncertain=water_uncertain)
    answers.append(
        Answer(
            question="Is there water here?",
            value=verdict,
            value_type="classified" if p_water is not None else "unavailable",
            detail=why,
        )
    )

    # 2. Water vs shadow probability
    if p_water is None or p_terrain_shadow is None:
        answers.append(
            Answer(
                question="Water vs shadow probability",
                value=UNAVAILABLE_TEXT,
                value_type="unavailable",
                detail="no fused probabilities for this site",
            )
        )
    else:
        answers.append(
            Answer(
                question="Water vs shadow probability",
                value=f"water {p_water:.2f} / shadow {p_terrain_shadow:.2f}",
                value_type="classified",
                caveat=(
                    "a transparent evidence score passed through a softmax, "
                    "not a calibrated probability"
                ),
            )
        )

    # 3. Evidence of a new landslide?
    if landslide_event:
        area = landslide_event.get("area_m2")
        answers.append(
            Answer(
                question="Evidence of a new landslide?",
                value="Yes",
                value_type=landslide_event.get("value_type", "classified"),
                detail=(
                    f"{area:,.0f} m² between {landslide_event.get('pre_date')} "
                    f"and {landslide_event.get('post_date')}"
                    if area is not None
                    else None
                ),
            )
        )
    else:
        answers.append(
            Answer(
                question="Evidence of a new landslide?",
                value="None detected",
                value_type="classified",
                detail="no bi-temporal change recorded for this site",
            )
        )

    # 4. Is a river potentially blocked?
    if blockage:
        confidence = blockage.get("confidence")
        answers.append(
            Answer(
                question="Is a river potentially blocked?",
                value=f"{blockage.get('site_type', 'Potential Landslide Dam')}",
                value_type="classified",
                detail=(
                    f"confidence {confidence:.2f} from "
                    f"{blockage.get('evidence_count', 0)} obstruction signal(s)"
                    if confidence is not None
                    else None
                ),
                caveat="a potential blockage, not a confirmed dam",
            )
        )
    else:
        answers.append(
            Answer(
                question="Is a river potentially blocked?",
                value="No candidate",
                value_type="classified",
                detail="no landslide met both the proximity and obstruction tests",
            )
        )

    # 5. Is there a barrier lake?
    if barrier_lake:
        answers.append(
            Answer(
                question="Is there a barrier lake?",
                value="Yes",
                value_type="classified",
                detail=(
                    f"{barrier_lake.get('lake_id', '?')}, "
                    f"{barrier_lake.get('qualifies_as', 'present')}, upstream of "
                    f"{barrier_lake.get('upstream_of', 'the blockage')}"
                ),
            )
        )
    else:
        answers.append(
            Answer(
                question="Is there a barrier lake?",
                value="None identified",
                value_type="classified",
            )
        )

    # 6. Area, estimated depth/volume, or "unavailable" with the reason
    area_m2 = (latest_observation or {}).get("water_area_m2")
    answers.append(
        Answer(
            question="Water area",
            value=f"{area_m2:,.0f} m² ({area_m2 / 1e6:.4f} km²)"
            if area_m2 is not None
            else UNAVAILABLE_TEXT,
            value_type=(latest_observation or {}).get("value_type", "unavailable")
            if area_m2 is not None
            else "unavailable",
            detail=(latest_observation or {}).get("method"),
        )
    )
    answers.append(_depth_answer(depth_estimate))

    # 7. Trend
    answers.append(_trend_answer(trend))

    # 8. Indicator level and contributing factors
    answers.extend(_risk_answers(risk))

    # 9. Data sources and observation dates
    answers.append(
        Answer(
            question="Data sources and observation dates",
            value="; ".join(sources) if sources else UNAVAILABLE_TEXT,
            value_type="observed" if sources else "unavailable",
        )
    )

    view = SiteView(
        site_code=str(site.get("site_code", "?")),
        site_type=str(site.get("site_type", "?")),
        answers=answers,
        disclaimer=disclaimer,
    )
    log.info(
        "site view %s: %d answer(s), %d unavailable",
        view.site_code,
        len(view.answers),
        len(view.unavailable_answers()),
    )
    return view


def _depth_answer(estimate: dict[str, Any] | None) -> Answer:
    """Depth and volume, or unavailable **with the branch's own reason**.

    Brief, Section 8: a value that cannot be traced to a branch is never
    emitted, and Section 14 asks for the reason to be shown rather than an
    empty cell.
    """
    if not estimate:
        return Answer(
            question="Estimated depth / volume",
            value=UNAVAILABLE_TEXT,
            value_type="unavailable",
            detail="no depth or volume estimate recorded for this site",
        )

    branch = estimate.get("branch", "?")
    if estimate.get("volume_m3") is None:
        return Answer(
            question="Estimated depth / volume",
            value=UNAVAILABLE_TEXT,
            value_type="unavailable",
            detail=f"Branch {branch}: {estimate.get('notes') or 'no reason recorded'}",
        )

    volume = float(estimate["volume_m3"])
    low, high = estimate.get("volume_low_m3"), estimate.get("volume_high_m3")
    bounds = (
        f" [{low / 1e6:.3f}–{high / 1e6:.3f}]"
        if low is not None and high is not None
        else ""
    )
    mean_depth = estimate.get("mean_depth_m")
    return Answer(
        question="Estimated depth / volume",
        value=f"{volume / 1e6:.3f} million m³{bounds}",
        value_type=estimate.get("value_type", "estimated"),
        detail=(
            f"Branch {branch}; mean depth {mean_depth:.1f} m"
            if mean_depth is not None
            else f"Branch {branch}"
        ),
        caveat="a conservative envelope, not a statistical confidence interval",
    )


def _trend_answer(trend: dict[str, Any] | None) -> Answer:
    if not trend:
        return Answer(
            question="Trend",
            value="Unknown",
            value_type="unavailable",
            detail="no time series for this site",
        )

    label = trend.get("trend", "Unknown")
    if label == "Unknown":
        return Answer(
            question="Trend",
            value="Unknown",
            value_type="unavailable",
            detail=trend.get("reason"),
        )

    rate = trend.get("rate_m2_per_day")
    percent = trend.get("percent_change")
    detail = []
    if rate is not None:
        detail.append(f"{rate:+,.0f} m²/day")
    if percent is not None:
        detail.append(f"{percent:+.1f}% over {trend.get('span_days')} days")
    gaps = trend.get("n_gaps") or 0
    if gaps:
        detail.append(f"{gaps} gap(s), not interpolated")
    return Answer(
        question="Trend",
        value=label,
        value_type="derived",
        detail="; ".join(detail) or None,
    )


def _risk_answers(risk: dict[str, Any] | None) -> list[Answer]:
    """The indicator level, and the factors behind it.

    Section 9 requires every warning to list its factors, and Section 14 asks
    for the level *and* the contributing factors. A level shown without its
    data coverage is the failure recorded in methods.md 11.3, so the coverage
    travels with it here too.
    """
    if not risk:
        # Both questions are still answered. Section 14 asks for the level
        # *and* the contributing factors; dropping the second question when
        # there is no assessment would leave a reader unsure whether the
        # factors were unmeasured or simply not shown.
        return [
            Answer(
                question="Indicator level",
                value=UNAVAILABLE_TEXT,
                value_type="unavailable",
                detail="no assessment recorded for this site",
            ),
            Answer(
                question="Contributing factors",
                value=UNAVAILABLE_TEXT,
                value_type="unavailable",
                detail="no assessment recorded for this site",
            ),
        ]

    level = risk.get("level", UNAVAILABLE_TEXT)
    coverage = risk.get("data_coverage")
    insufficient = bool(risk.get("insufficient_data"))

    caveat = None
    if insufficient:
        caveat = (
            "INSUFFICIENT DATA: this level rests on less than the configured "
            "minimum share of the evidence. Absence of a measurement is not "
            "evidence of safety."
        )

    answers = [
        Answer(
            question="Indicator level",
            value=level,
            value_type="classified",
            detail=(
                f"score {risk.get('score', 0.0):.2f}"
                + (f", data coverage {coverage:.0%}" if coverage is not None else "")
            ),
            caveat=caveat,
        )
    ]

    factors = risk.get("factors") or []
    present = [f for f in factors if f.get("available")]
    missing = [f for f in factors if not f.get("available")]
    answers.append(
        Answer(
            question="Contributing factors",
            value=(
                "; ".join(
                    f"{f['name']} {f.get('value', '?')} "
                    f"(contributes {f.get('contribution', 0.0):.2f})"
                    for f in present
                )
                if present
                else "none could be measured"
            ),
            value_type="derived" if present else "unavailable",
            detail=(
                "not measured: " + ", ".join(f["name"] for f in missing)
                if missing
                else None
            ),
        )
    )
    return answers
