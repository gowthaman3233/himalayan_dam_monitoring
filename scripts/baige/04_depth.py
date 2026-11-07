"""Phase 10 branch logic on the real lake, and why its numbers are withheld.

Supports: validation.md 24

Installed from the session that produced the result. Run from anywhere:

    python scripts/baige/04_depth.py

Paths derive from this file's location, so a clone works without editing.
"""

from __future__ import annotations

import json
import sys
from datetime import date as Date
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from analysis.depth_volume import (  # noqa: E402
    decide_branch,
    estimate_depth_volume,
    water_surface_elevation,
)
from config.loader import load_config_with_overlay  # noqa: E402
from detection.barrier_lake import find_barrier_lakes  # noqa: E402
from detection.water import optical_water_mask  # noqa: E402
from preprocessing.cloud_mask import build_masks, select_cloud_score  # noqa: E402
from utils.crs import pixel_area_m2  # noqa: E402

RAW = ROOT / "data" / "raw" / "baige_2018"
BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
DEM_EPOCH_END = Date(2014, 9, 11)
LAKE_FIRST_OBSERVED = Date(2018, 11, 9)

cfg = load_config_with_overlay("baige_2018", load_env=False)
arrays = np.load(ROOT / "data" / "processed" / "baige_arrays.npz")
p7 = np.load(ROOT / "data" / "processed" / "baige_phase7.npz")
with rasterio.open(RAW / "DEM_GLO30_v02_EPSG32647.tif") as s:
    transform, crs = s.transform, s.crs
cell = float(abs(transform.a))
area = pixel_area_m2(transform, crs)

dem = arrays["dem"]
wbm = arrays["wbm"]       # GLO-30 water body mask: what the DEM called water
hem = arrays["hem"]       # height error mask
streams, acc = p7["streams"], p7["accumulation"]
site = p7[{k[5:]: k for k in p7.files if k.startswith("site_")}["ND-001"]].astype(bool)


def read(stem: str):
    with rasterio.open(RAW / f"{stem}_refl.tif") as s:
        refl = {n: s.read(i + 1).astype("float64") for i, n in enumerate(BANDS)}
    with rasterio.open(RAW / f"{stem}_qa.tif") as s:
        qa = {n: s.read(i + 1) for i, n in enumerate(s.descriptions) if n}
    cs = None
    if (RAW / f"{stem}_cs.tif").is_file():
        with rasterio.open(RAW / f"{stem}_cs.tif") as s:
            cs = {n: s.read(i + 1).astype("float64")
                  for i, n in enumerate(s.descriptions) if n}
    masks = build_masks(cfg, scl=qa.get("SCL"),
                        cloud_score=None if cs is None
                        else select_cloud_score(cs, cfg))
    water = optical_water_mask(refl["B3"], refl["B8"], refl["B11"], cfg,
                               invalid=masks.unusable).water
    return water, masks


water_pre, _ = read("S2_47RMQ_20181102T041940")
water_post, masks_post = read("S2_47RMQ_20181109T040948")

lake = max(
    find_barrier_lakes(
        cfg, blockage_site=site, streams=streams, water_post=water_post,
        water_pre=water_pre, cellsize_m=cell, pixel_area_m2=area,
        flow_accumulation=acc, dam_code="ND-001",
    ),
    key=lambda x: x.area_m2,
).mask

newly_flooded = lake & ~water_pre
pre_existing = lake & water_pre
print(f"lake                 {int(lake.sum()):6d} px = {lake.sum() * area:>9,.0f} m2")
print(f"  newly flooded      {int(newly_flooded.sum()):6d} px = "
      f"{newly_flooded.sum() * area:>9,.0f} m2  (DEM holds pre-lake ground)")
print(f"  pre-existing river {int(pre_existing.sum()):6d} px = "
      f"{pre_existing.sum() * area:>9,.0f} m2  (DEM recorded a water surface)")

wbm_in_lake = float((wbm > 0)[lake].mean())
print(f"\nGLO-30 water-body mask covers {wbm_in_lake:.1%} of the lake")
print(f"  of the pre-existing river part: "
      f"{float((wbm > 0)[pre_existing].mean()):.1%}")
print(f"  of the newly flooded part:      "
      f"{float((wbm > 0)[newly_flooded].mean()):.1%}")
print(f"DEM inside the lake: sd {dem[lake].std():.2f} m, "
      f"range {dem[lake].min():.0f}-{dem[lake].max():.0f} m")
print(f"HEM zero inside the lake: "
      f"{float((hem[lake] == 0.0).mean()):.1%}")
print(f"DEM epoch ended {DEM_EPOCH_END}; lake first observed "
      f"{LAKE_FIRST_OBSERVED}")

# ---------------------------------------------------------------- shipped run
print(f"\n{'=' * 70}\nWHAT THE SHIPPED LOGIC DOES (whole lake, one branch)\n{'=' * 70}")
est = estimate_depth_volume(
    cfg, lake, dem,
    cellsize_m=cell, pixel_area_m2=area,
    dem_water_mask=(wbm > 0), dem_height_error=hem,
    dem_epoch_end=DEM_EPOCH_END, lake_first_observed=LAKE_FIRST_OBSERVED,
    observation_is_usable=True,
)
print(f"branch {est.branch}   value_type {est.value_type}")
print(f"reason: {est.reason}")
for k, v in (est.evidence or {}).items():
    print(f"  evidence {k}: {v}")
print(f"mean depth {est.mean_depth_m}  max depth {est.max_depth_m}  "
      f"volume {est.volume_m3}")

# ------------------------------------------------- what each part would give
print(f"\n{'=' * 70}\nWHAT EACH PART WOULD GIVE (measurement, not a new branch)\n{'=' * 70}")
wse = water_surface_elevation(dem, lake, cfg, cellsize_m=cell)
if wse is None:
    print("no reliable shoreline; nothing further can be said")
    sys.exit(0)
print(f"water surface elevation from the shoreline ring: {wse.wse_m:.2f} m "
      f"+/- {wse.spread_m:.2f} ({wse.samples} samples, "
      f"{wse.statistic}/{wse.spread_statistic})")

for label, part in (("newly flooded (Branch A applies)", newly_flooded),
                    ("pre-existing river (Branch B)", pre_existing)):
    if not part.any():
        continue
    d = np.clip(wse.wse_m - dem[part], 0.0, None)
    vol = float(d.sum() * area)
    print(f"\n{label}: {int(part.sum())} px")
    print(f"  depth vs DEM: mean {d.mean():.2f} m, max {d.max():.2f} m")
    print(f"  implied volume {vol:,.0f} m3 ({vol / 1e6:.3f} x 10^6 m3)")
    dec = decide_branch(
        cfg, dem, part, wse=wse, dem_water_mask=(wbm > 0),
        dem_height_error=hem, dem_epoch_end=DEM_EPOCH_END,
        lake_first_observed=LAKE_FIRST_OBSERVED,
    )
    print(f"  decide_branch on this part alone -> Branch {dec.branch}")
    print(f"    {dec.reason}")

new_d = np.clip(wse.wse_m - dem[newly_flooded], 0.0, None)
lower_bound = float(new_d.sum() * area)
print(f"\n{'=' * 70}")
print(f"A traceable LOWER BOUND on the impounded volume is the Branch A sum")
print(f"over the newly flooded ground only: {lower_bound:,.0f} m3 "
      f"({lower_bound / 1e6:.3f} x 10^6 m3).")
print(f"It omits the water the Jinsha already held below its 2011-2014")
print(f"surface, which is Branch B and unmeasurable from this DEM.")
print(f"Published Baige lake figures are 105-775 x 10^6 m3 (validation 2.2),")
print(f"so this bound is {105e6 / max(lower_bound, 1):.0f}-"
      f"{775e6 / max(lower_bound, 1):.0f}x below them -- as expected for a")
print(f"3 km AOI that truncates the lake, and NOT a comparison of like with like.")

out = ROOT / "outputs" / "baige_2018_phase10_depth.json"
out.write_text(json.dumps({
    "lake": "BL-001", "obs_date": str(LAKE_FIRST_OBSERVED),
    "dem_epoch_end": str(DEM_EPOCH_END),
    "lake_px": int(lake.sum()),
    "lake_area_m2": round(float(lake.sum() * area), 1),
    "newly_flooded_px": int(newly_flooded.sum()),
    "newly_flooded_area_m2": round(float(newly_flooded.sum() * area), 1),
    "pre_existing_river_px": int(pre_existing.sum()),
    "pre_existing_river_area_m2": round(float(pre_existing.sum() * area), 1),
    "glo30_water_mask_fraction_of_lake": round(wbm_in_lake, 4),
    "dem_sd_inside_lake_m": round(float(dem[lake].std()), 3),
    "hem_zero_fraction_inside_lake": round(float((hem[lake] == 0.0).mean()), 4),
    "shipped_result": {
        "branch": est.branch, "value_type": est.value_type, "reason": est.reason,
        "mean_depth_m": est.mean_depth_m, "max_depth_m": est.max_depth_m,
        "volume_m3": est.volume_m3, "evidence": est.evidence,
    },
    "wse": {"wse_m": round(wse.wse_m, 2),
            "spread_m": round(wse.spread_m, 2),
            "samples": wse.samples},
    "branch_a_lower_bound_on_newly_flooded_only_m3": round(lower_bound, 1),
    "published_lake_volume_range_m3": [105e6, 775e6],
    "comparison_note": (
        "NOT comparable: the AOI truncates the lake and the bound omits the "
        "pre-dam river's own depth (Branch B)."
    ),
}, indent=2, default=str), encoding="utf-8")
print(f"\nwrote {out}")
