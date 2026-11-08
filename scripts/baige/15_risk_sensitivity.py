"""What does the Baige CRITICAL level actually depend on?

Supports: validation.md 33

The indicator for Baige is CRITICAL at a score of 0.798 against a threshold of
0.75. That is a margin of 0.048, which is thin enough that the useful question
is not "is it CRITICAL" but "which inputs would have to be wrong, and by how
much, for it not to be".

This varies ONE input at a time, holding the rest at their measured values,
and reports where the level changes. It is a sensitivity analysis, not a
validation: it says how robust the output is to errors in each input and says
nothing about whether any input is right.

The volume rows are WHAT-IFS. Depth and volume are withheld for this site
(validation.md 24) and nothing here supplies a volume; the rows show how far
the level would move if one were available.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from analysis.risk import assess_risk  # noqa: E402
from config.loader import load_config_with_overlay  # noqa: E402

cfg = load_config_with_overlay("baige_2018", load_env=False)
fused = json.load(
    open(ROOT / "outputs" / "baige_2018_rederived_on_fused_water.json",
         encoding="utf-8")
)
measured = {f["name"]: f["value"] for f in fused["phase11"]["factors"]
            if f["available"]}

BASE = {
    "lake_growth_rate_m2_per_day": measured["lake_growth_rate"],
    "new_landslide_area_m2": measured["new_landslide_activity"],
    "blockage_confidence": measured["blockage_confidence"],
    "slope_deg": measured["slope"],
}
CRITICAL = cfg.analysis.risk.levels.critical
HIGH = cfg.analysis.risk.levels.high_risk


def assess(**overrides):
    inputs = {**BASE, **overrides}
    return assess_risk(
        cfg,
        lake_volume_m3=inputs.pop("lake_volume_m3", None),
        volume_unavailable_reason="withheld (validation.md 24)",
        rainfall_mm_24h=None,
        **inputs,
    )



def fmt(value: float) -> str:
    """Format a value without losing the precision that matters.

    A blockage confidence of 0.75 printed with one decimal reads as 0.8, and a
    flip point at 0.595 reads as 0.6 -- both misleading in an analysis whose
    whole point is a thin margin.
    """
    return f"{value:,.3f}" if abs(value) < 10 else f"{value:,.1f}"


def short(level: str) -> str:
    return level.split(" - ")[0].replace(" INDICATORS", "")


base = assess()
print(f"baseline: score {base.score:.4f}  {short(base.level)}  "
      f"(threshold for CRITICAL {CRITICAL}, margin {base.score - CRITICAL:+.4f})")
print(f"  inputs: " + ", ".join(f"{k}={fmt(v)}" for k, v in BASE.items()))
print()


def sweep(name: str, key: str, grid: np.ndarray, unit: str,
          alternatives: dict[str, float]) -> dict:
    """Where does the level leave CRITICAL as ``key`` moves?"""
    levels = [short(assess(**{key: float(v)}).level) for v in grid]
    is_critical = np.array([lvl == "CRITICAL" for lvl in levels])
    base_value = BASE.get(key)
    here = int(np.argmin(np.abs(grid - base_value))) if base_value is not None else 0

    # The contiguous CRITICAL range around the measured value.
    lo = hi = here
    while lo > 0 and is_critical[lo - 1]:
        lo -= 1
    while hi < len(grid) - 1 and is_critical[hi + 1]:
        hi += 1
    held_down = grid[lo] > grid[0]
    held_up = grid[hi] < grid[-1]

    print(f"{name}  (measured {fmt(base_value)} {unit})")
    if held_down and held_up:
        print(f"   stays CRITICAL from {fmt(grid[lo])} to {fmt(grid[hi])} {unit}")
    elif held_down:
        print(f"   stays CRITICAL from {fmt(grid[lo])} {unit} upward "
              f"(measured {fmt(base_value)}, so the margin is "
              f"{fmt(base_value - grid[lo])} {unit}, "
              f"{100 * (base_value - grid[lo]) / abs(base_value):.0f}% of the "
              f"measured value)")
    elif held_up:
        print(f"   stays CRITICAL up to {fmt(grid[hi])} {unit}")
    else:
        print(f"   CRITICAL across the whole range tested "
              f"({grid[0]:,.1f} to {grid[-1]:,.1f} {unit})")
    for label, value in alternatives.items():
        r = assess(**{key: value})
        print(f"     if {label:46s} -> {fmt(value):>10s}  score "
              f"{r.score:.3f}  {short(r.level)}")
    print()
    return {
        "input": key, "measured": base_value,
        "critical_from": float(grid[lo]) if held_down else None,
        "critical_to": float(grid[hi]) if held_up else None,
    }


scales = cfg.analysis.risk.scales
results = [
    sweep("blockage confidence", "blockage_confidence",
          np.round(np.arange(0.0, 1.0001, 0.005), 3), "",
          {"it were the unmerged ND-001 value (validation 21)": 0.5,
           "it were the maximum": 1.0}),
    sweep("lake growth rate", "lake_growth_rate_m2_per_day",
          np.arange(-3000.0, 4000.0, 10.0), "m2/day",
          {"the unmerged, Decreasing rate (validation 26)": -1107.7,
           "the lake were not changing": 0.0}),
    sweep("median slope of the deposit", "slope_deg",
          np.round(np.arange(0.0, 90.0, 0.5), 1), "deg",
          {"the unmerged candidate's slope (validation 26)": 45.5,
           "a flat deposit": 5.0}),
    sweep("new landslide area", "new_landslide_area_m2",
          np.arange(0.0, 120000.0, 500.0), "m2",
          {"only the unmerged fragment (validation 26)": 6700.0,
           "the Phase 5 change map in total": 318900.0}),
]

# --- the withheld factor: what-ifs, not estimates ------------------------- #
print("lake volume  (WITHHELD for this site: these are what-ifs, not values)")
vol_scale = scales.lake_volume_m3
print(f"   scale {vol_scale[0]:,.0f} to {vol_scale[1]:,.0f} m3, weight "
      f"{cfg.analysis.risk.weights.lake_volume:g}")
available_weight = sum(f.weight for f in base.factors if f.available)
print(f"   the baseline scores over the factors that CAN be measured "
      f"(total weight {available_weight:g}); an unavailable factor is left out "
      f"rather than scored as zero risk, so a measured volume would add weight "
      f"{cfg.analysis.risk.weights.lake_volume:g} and pull the score toward "
      f"its own value")
grid = np.arange(0.0, 2.0e7, 1.0e5)
levels = [short(assess(lake_volume_m3=float(v)).level) for v in grid]
crit = np.array([l == "CRITICAL" for l in levels])
if crit.any() and not crit.all():
    first = float(grid[int(np.argmax(crit))])
    print(f"   the level stays CRITICAL only if the volume were at least "
          f"~{first:,.0f} m3")
for v in (0.0, 1.0e6, 3.0e6, 5.0e6, 7.5e6, 1.0e7):
    r = assess(lake_volume_m3=v)
    print(f"     if volume were {v:>12,.0f} m3 -> score {r.score:.3f}  "
          f"{short(r.level)}")
print()

# --- the combination the unmerged analysis actually had ------------------- #
unmerged = assess(
    lake_growth_rate_m2_per_day=-1107.7, new_landslide_area_m2=6700.0,
    blockage_confidence=0.75, slope_deg=45.5,
)
print(f"for reference, the unmerged inputs together (validation 25): "
      f"score {unmerged.score:.3f}  {short(unmerged.level)}")

out = ROOT / "outputs" / "baige_2018_risk_sensitivity.json"
out.write_text(json.dumps({
    "baseline_score": round(float(base.score), 4),
    "baseline_level": base.level,
    "critical_threshold": CRITICAL,
    "margin": round(float(base.score - CRITICAL), 4),
    "one_at_a_time": results,
    "note": ("sensitivity, not validation; the volume rows are what-ifs, "
             "depth and volume being withheld for this site"),
}, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
