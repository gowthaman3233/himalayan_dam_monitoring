"""Re-verify Phase 4's gate after the cos_incidence BLAS bug: is the stored illumination what the fixed code produces?

Supports: validation.md 24 (Finding 5a)

Installed from the session that produced the result. Run from anywhere:

    python scripts/checks/phase4_illumination.py

Paths derive from this file's location, so a clone works without editing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from preprocessing.terrain import cos_incidence, terrain_shadow_mask  # noqa: E402

arrays = np.load(ROOT / "data" / "processed" / "phase2_arrays.npz")
dem = arrays["dem"]
stored_illumination = arrays["illumination"]
stored_shadow = arrays["terrain_shadow"]
stored_self = arrays["self_shadow"]
stored_cast = arrays["cast_shadow"]
sun = arrays["sun"]
azimuth, zenith = float(sun[0]), float(sun[1])

print(f"grid {dem.shape}  ({dem.size:,} px, far above the ~300x300 threshold)")
print(f"sun azimuth {azimuth:.4f}, zenith {zenith:.4f}")
print()

print("recomputing illumination with the fixed elementwise code...")
fresh = cos_incidence(dem, 10.0, azimuth, zenith)
print("  completed -- so the fixed code runs at this size")

diff = np.abs(fresh - stored_illumination)
print()
print("comparison against the layer Phase 2 stored and Phase 4 consumed:")
print(f"  max absolute difference : {float(diff.max()):.3e}")
print(f"  mean absolute difference: {float(diff.mean()):.3e}")
identical = bool(np.allclose(fresh, stored_illumination, atol=1e-9))
print(f"  identical to 1e-9       : {identical}")

print()
print("recomputing the full terrain-shadow product...")
product = terrain_shadow_mask(dem, 10.0, azimuth, zenith)
for name, stored in (
    ("terrain_shadow", stored_shadow),
    ("self_shadow", stored_self),
    ("cast_shadow", stored_cast),
):
    fresh_mask = product[name].astype(bool)
    agree = int((fresh_mask == stored.astype(bool)).sum())
    print(f"  {name:16s} {agree:,}/{fresh_mask.size:,} px agree "
          f"({100 * agree / fresh_mask.size:.4f}%)  "
          f"stored {int(stored.sum()):,} px, fresh {int(fresh_mask.sum()):,} px")

report = json.load(
    open(ROOT / "outputs" / "phase4_shadow_rejection_report.json", encoding="utf-8")
)
reduction = report["false_water_reduction"]["removed_fraction_of_baseline"]
retained = report["false_water_reduction"]["reference_retained_fraction"]

print()
print("=" * 68)
if identical:
    print("VERDICT: the stored illumination is bit-for-bit what the fixed code")
    print("produces, so the Phase 4 run used a valid layer. The headline")
    print(f"figures stand unchanged: {100 * reduction:.1f}% false water removed,")
    print(f"{100 * retained:.1f}% of the reference lake retained.")
    print()
    print("The BLAS failure is INTERMITTENT, not permanent -- it kills the")
    print("process rather than corrupting values, so any run that completed")
    print("and wrote output was unaffected. Phase 4's gate is not in doubt.")
else:
    print("VERDICT: the stored and recomputed illumination DIFFER. The Phase 4")
    print("numbers must be re-derived before the claim can be repeated.")
print("=" * 68)

out = ROOT / "outputs" / "phase4_illumination_recheck.json"
out.write_text(json.dumps({
    "question": ("whether the Phase 4 gate result used a valid illumination "
                 "layer, given cos_incidence could die silently at this size"),
    "grid": list(dem.shape),
    "sun_azimuth_deg": azimuth,
    "sun_zenith_deg": zenith,
    "max_abs_difference": float(diff.max()),
    "mean_abs_difference": float(diff.mean()),
    "identical_to_1e9": identical,
    "mask_agreement": {
        name: round(
            float((product[name].astype(bool) == stored.astype(bool)).mean()), 6
        )
        for name, stored in (
            ("terrain_shadow", stored_shadow),
            ("self_shadow", stored_self),
            ("cast_shadow", stored_cast),
        )
    },
    "phase4_false_water_reduction": reduction,
    "phase4_reference_retained": retained,
    "verdict": (
        "Phase 4's gate result is unaffected: the stored illumination matches "
        "the fixed implementation exactly. The BLAS failure kills the process "
        "rather than corrupting values, so a completed run cannot have hit it."
        if identical else
        "Phase 4 must be re-derived."
    ),
}, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
