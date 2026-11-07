"""Score the Baige detections against hand-digitised truth.

Supports: validation.md -- the project's FIRST accuracy figures

This project has never had ground truth. Every number in sections 20-30 is a
plausibility check: a distance to a published point, an elevation, an area
compared with a published figure, or an agreement between two independent
signals. None of it is accuracy, and no amount of further engineering
substitutes for a reference mask.

This script turns two hand-drawn layers into IoU, precision and recall.

WHAT TO DRAW (see the README section below, or docs/validation.md)

    data/validation/baige_landslide_truth.gpkg   the deposit outline
    data/validation/baige_lake_truth.gpkg        the impounded water, 2018-11-09

Both as POLYGON layers in EPSG:32647, digitised over
data/raw/baige_2018/S2_47RMQ_20181109T040948_refl.tif.

Run from anywhere:

    python scripts/baige/12_score_against_truth.py

It reports what it can and says plainly what is missing, so a partial job is
still useful: digitising the lake alone already gives the lake a number.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from config.loader import load_config_with_overlay  # noqa: E402
from detection.barrier_lake import find_barrier_lakes  # noqa: E402
from detection.blockage import detect_blockages  # noqa: E402
from utils.crs import pixel_area_m2  # noqa: E402

TRUTH_DIR = ROOT / "data" / "validation"
LANDSLIDE_TRUTH = TRUTH_DIR / "baige_landslide_truth.gpkg"
LAKE_TRUTH = TRUTH_DIR / "baige_lake_truth.gpkg"
DEM = ROOT / "data/raw/baige_2018/DEM_GLO30_v02_EPSG32647.tif"


def confusion(truth: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    """IoU, precision, recall and F1 for one binary class.

    Precision and recall are reported separately rather than only as IoU,
    because they fail differently and the distinction is actionable: low
    recall means the detector missed the feature, low precision means it
    flagged ground that is not the feature, and the fixes are not the same.
    """
    truth = np.asarray(truth, dtype=bool)
    predicted = np.asarray(predicted, dtype=bool)
    tp = int(np.count_nonzero(truth & predicted))
    fp = int(np.count_nonzero(~truth & predicted))
    fn = int(np.count_nonzero(truth & ~predicted))
    union = tp + fp + fn
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision and recall
        else None
    )
    return {
        "true_positive_px": tp,
        "false_positive_px": fp,
        "false_negative_px": fn,
        "iou": (tp / union) if union else None,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def rasterise(path: Path, transform, shape, crs) -> np.ndarray | None:
    """A truth layer as a boolean mask on the detection grid."""
    if not path.is_file():
        return None

    import geopandas as gpd

    frame = gpd.read_file(path)
    if frame.empty:
        print(f"  {path.name}: file exists but holds no features")
        return None
    if frame.crs is None:
        raise SystemExit(
            f"{path.name} has no CRS. Set it to EPSG:32647 in QGIS "
            "(Layer Properties > Source) -- a layer without a CRS cannot be "
            "placed on the ground and scoring it would be meaningless."
        )
    if frame.crs.to_string() != str(crs):
        print(f"  {path.name}: reprojecting {frame.crs.to_string()} -> {crs}")
        frame = frame.to_crs(crs)

    mask = rasterio.features.rasterize(
        [(geom, 1) for geom in frame.geometry if geom is not None],
        out_shape=shape, transform=transform, dtype="uint8",
    ).astype(bool)
    print(f"  {path.name}: {len(frame)} feature(s), {int(mask.sum())} px")
    return mask


def main() -> int:
    cfg = load_config_with_overlay("baige_2018", load_env=False)
    with rasterio.open(DEM) as src:
        transform, crs, shape = src.transform, src.crs, src.shape
    cell = float(abs(transform.a))
    area = pixel_area_m2(transform, crs)

    fused_path = ROOT / "data" / "processed" / "baige_fused.npz"
    if not fused_path.is_file():
        raise SystemExit(
            f"{fused_path} is missing. Run "
            "scripts/baige/03_rederive_chain.py first -- it produces the "
            "authoritative detections this scores."
        )
    fused = np.load(fused_path)

    print("truth layers:")
    truth_landslide = rasterise(LANDSLIDE_TRUTH, transform, shape, crs)
    truth_lake = rasterise(LAKE_TRUTH, transform, shape, crs)
    if truth_landslide is None:
        print(f"  {LANDSLIDE_TRUTH.name}: NOT FOUND")
    if truth_lake is None:
        print(f"  {LAKE_TRUTH.name}: NOT FOUND")
    if truth_landslide is None and truth_lake is None:
        raise SystemExit(
            f"\nNo truth layers in {TRUTH_DIR}. Digitise at least one (the "
            "module docstring says what to draw) and run this again. Either "
            "one on its own is useful."
        )

    results: dict[str, object] = {
        "scene": "S2_47RMQ_20181109T040948",
        "crs": str(crs),
        "pixel_area_m2": area,
    }

    # ---- the landslide change map ---------------------------------------- #
    if truth_landslide is not None:
        predicted = fused["change"].astype(bool)
        scores = confusion(truth_landslide, predicted)
        results["landslide_change"] = {
            **scores,
            "truth_area_m2": round(float(truth_landslide.sum() * area), 1),
            "predicted_area_m2": round(float(predicted.sum() * area), 1),
        }
        print(f"\n{'=' * 66}\nPHASE 5 landslide change vs truth\n{'=' * 66}")
        report(scores, truth_landslide, predicted, area)

    # ---- the barrier lake ------------------------------------------------- #
    if truth_lake is not None:
        hydro = ROOT / "data" / "processed" / "baige_hydro"
        with rasterio.open(hydro / "baige_streams.tif") as src:
            streams = src.read(1) > 0
        with rasterio.open(hydro / "baige_d8_accumulation.tif") as src:
            accumulation = src.read(1, masked=True).filled(0.0)

        candidates = detect_blockages(
            cfg, landslides=fused["change"].astype(bool), streams=streams,
            cellsize_m=cell, pixel_area_m2=area,
            flow_accumulation=accumulation,
            water_pre=fused["water_pre"], water_post=fused["water_post"],
            transform=transform, crs=crs,
            pre_date="2018-11-02", post_date="2018-11-09",
        )
        best, lake_mask = None, None
        for candidate in candidates:
            lakes = find_barrier_lakes(
                cfg, blockage_site=candidate.site_mask, streams=streams,
                water_post=fused["water_post"], water_pre=fused["water_pre"],
                cellsize_m=cell, pixel_area_m2=area,
                flow_accumulation=accumulation, dam_code=candidate.dam_code,
            )
            if not lakes:
                continue
            biggest = max(lakes, key=lambda x: x.area_m2)
            if best is None or biggest.area_m2 > best:
                best, lake_mask = biggest.area_m2, biggest.mask

        if lake_mask is None:
            print("\nno lake detected, so there is nothing to score")
        else:
            scores = confusion(truth_lake, lake_mask)
            results["barrier_lake"] = {
                **scores,
                "truth_area_m2": round(float(truth_lake.sum() * area), 1),
                "predicted_area_m2": round(float(lake_mask.sum() * area), 1),
                "upstream_search_m": cfg.detection.barrier_lake.upstream_search_m,
            }
            print(f"\n{'=' * 66}\nPHASE 8 barrier lake vs truth\n{'=' * 66}")
            report(scores, truth_lake, lake_mask, area)
            print(
                f"  NOTE: the detected lake is bounded by "
                f"upstream_search_m = "
                f"{cfg.detection.barrier_lake.upstream_search_m:.0f} m and by "
                f"the AOI edge, so low recall here may be truncation rather "
                f"than a detection failure. Compare the shapes before "
                f"concluding."
            )

    out = ROOT / "outputs" / "baige_2018_accuracy.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    print(
        "\nThese are the project's first accuracy figures. They describe ONE "
        "event on ONE date, scored against ONE person's interpretation of the "
        "imagery -- which is ground truth in the sense the field uses the "
        "term, not an absolute."
    )
    return 0


def report(scores, truth, predicted, area) -> None:
    print(f"  truth      {int(truth.sum()):7d} px = "
          f"{truth.sum() * area:>12,.0f} m2")
    print(f"  predicted  {int(predicted.sum()):7d} px = "
          f"{predicted.sum() * area:>12,.0f} m2")
    print()
    for key in ("iou", "precision", "recall", "f1"):
        value = scores[key]
        print(f"  {key:10s} {'n/a' if value is None else f'{value:.4f}'}")
    print()
    print(f"  true positive  {scores['true_positive_px']:7d} px")
    print(f"  false positive {scores['false_positive_px']:7d} px  "
          f"(flagged, not truth)")
    print(f"  false negative {scores['false_negative_px']:7d} px  "
          f"(truth, missed)")
    if scores["recall"] is not None and scores["precision"] is not None:
        if scores["recall"] < scores["precision"]:
            print("\n  Recall below precision: the detector MISSED more of the "
                  "feature than it over-flagged. Thresholds are too strict.")
        else:
            print("\n  Precision below recall: the detector OVER-FLAGGED more "
                  "than it missed. Thresholds are too loose.")


if __name__ == "__main__":
    raise SystemExit(main())
