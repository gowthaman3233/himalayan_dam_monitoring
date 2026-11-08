"""Where are the lake detection's errors, and are they the kind that matter?

Supports: validation.md 32

An IoU of 0.66 says the detection and the reference disagree. It does not say
HOW, and the two possible answers lead in opposite directions:

* disagreement along the shoreline, within a pixel or two, is mostly
  unavoidable. Sentinel-2 pixels are 10 m, a hand-drawn outline is good to
  perhaps one or two of them, and a mixed water/land pixel has no right
  answer. That is a measurement-resolution limit, not a detector defect.
* disagreement far from the shoreline, in coherent patches, is a real
  detection error -- shadow called water, or water missed.

This separates the two. It uses the truth to DIAGNOSE the detector and
changes nothing: tuning thresholds against the same reference and then
reporting the improved score on the same event would be fitting the answer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from scipy import ndimage  # noqa: E402

scored = ROOT / "data" / "processed" / "baige_lake_scored.npz"
if not scored.is_file():
    raise SystemExit(
        f"{scored} is missing. Run scripts/baige/12_score_against_truth.py "
        "first; it saves the detected and truth masks."
    )
data = np.load(scored)
detected = data["detected"].astype(bool) & data["observed"].astype(bool)
truth = data["truth"].astype(bool) & data["observed"].astype(bool)
arrays = np.load(ROOT / "data" / "processed" / "baige_arrays.npz")
slope = arrays["slope"]

false_pos = detected & ~truth
false_neg = truth & ~detected
true_pos = detected & truth


def dist_to(mask: np.ndarray) -> np.ndarray:
    """Distance in pixels from every pixel to the nearest True pixel of mask."""
    return ndimage.distance_transform_edt(~mask)


d_truth = dist_to(truth)       # for false positives: how far outside the truth
d_detect = dist_to(detected)   # for false negatives: how far outside the detection

print(f"truth {int(truth.sum())} px | detected {int(detected.sum())} px | "
      f"false positive {int(false_pos.sum())} | false negative {int(false_neg.sum())}")
print()

print("FALSE POSITIVES: detected as lake, not in the reference")
print(f"{'within':>10s} {'px':>6s} {'share':>7s}")
for reach in (1, 2, 3, 5):
    n = int((false_pos & (d_truth <= reach)).sum())
    print(f"{reach:>7d} px {n:6d} {100 * n / max(int(false_pos.sum()), 1):6.1f}%")
far_fp = false_pos & (d_truth > 3)
print(f"  more than 3 px from the reference lake: {int(far_fp.sum())} px "
      f"= {100 * far_fp.sum() / max(int(false_pos.sum()), 1):.1f}% of false positives")

print()
print("FALSE NEGATIVES: in the reference, not detected")
print(f"{'within':>10s} {'px':>6s} {'share':>7s}")
for reach in (1, 2, 3, 5):
    n = int((false_neg & (d_detect <= reach)).sum())
    print(f"{reach:>7d} px {n:6d} {100 * n / max(int(false_neg.sum()), 1):6.1f}%")
far_fn = false_neg & (d_detect > 3)
print(f"  more than 3 px from the detected lake: {int(far_fn.sum())} px "
      f"= {100 * far_fn.sum() / max(int(false_neg.sum()), 1):.1f}% of false negatives")

# The score if shoreline disagreement of up to N pixels were forgiven.
print()
print("SCORE WITH A SHORELINE TOLERANCE (the same detection, same reference)")
print(f"{'tolerance':>10s} {'precision':>10s} {'recall':>8s} {'IoU':>7s}")
for tol in (0, 1, 2, 3):
    near_truth = d_truth <= tol
    near_detect = d_detect <= tol
    tp_p = int((detected & near_truth).sum())     # detected pixels matched
    tp_r = int((truth & near_detect).sum())       # truth pixels matched
    precision = tp_p / max(int(detected.sum()), 1)
    recall = tp_r / max(int(truth.sum()), 1)
    iou = (min(tp_p, tp_r)) / max(
        int(detected.sum()) + int(truth.sum()) - min(tp_p, tp_r), 1)
    print(f"{tol:>7d} px {precision:10.3f} {recall:8.3f} {iou:7.3f}")

print()
print("NOTE ON SLOPE: it is deliberately NOT used to judge these pixels.")
print("  The DEM was acquired 2011-2014, four years before this lake formed,")
print("  so the slope under the lake is the OLD VALLEY's slope, not the water's.")
print("  An earlier version of this script treated slope over 15 deg as")
print("  evidence against water. That is backwards here: the true positives")
print(f"  have the steeper median ({np.median(slope[true_pos]):.1f} deg).")

# Coherent patches are real errors; scattered single pixels are noise.
labelled, count = ndimage.label(far_fp, structure=np.ones((3, 3)))
if count:
    sizes = ndimage.sum(far_fp, labelled, range(1, count + 1))
    order = np.argsort(sizes)[::-1]
    print()
    print(f"{count} separate patch(es) of false positive more than 3 px from "
          f"the reference; the largest:")
    truth_rows = np.nonzero(truth.any(axis=1))[0]
    print(f"  (the reference lake occupies rows {truth_rows.min()}-"
          f"{truth_rows.max()}; the scene's top edge is row 0)")
    for k in order[:4]:
        rows, cols = np.nonzero(labelled == k + 1)
        print(f"   {int(sizes[k]):5d} px, rows {rows.min()}-{rows.max()}, "
              f"cols {cols.min()}-{cols.max()}")
        if rows.min() == 0 and truth_rows.min() > 0:
            print("        reaches the scene's top edge while the reference "
                  "stops short of it: the lake continuing north, which the "
                  "reference may simply not have been drawn to include")
else:
    print("\nno false-positive patch lies more than 3 px from the reference")
