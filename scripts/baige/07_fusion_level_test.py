"""The level-surface test: a lake is level, so no real water pixel sits far above the waterline.

Supports: validation.md 24 (Finding 4)

Installed from the session that produced the result. Run from anywhere:

    python scripts/baige/07_fusion_level_test.py

Paths derive from this file's location, so a clone works without editing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from config.loader import load_config_with_overlay  # noqa: E402
from detection.shadow_rejection import false_water_reduction, fuse  # noqa: E402
from detection.water import mndwi, ndwi, optical_water_mask, sar_water_threshold  # noqa: E402
from preprocessing.cloud_mask import build_masks, select_cloud_score  # noqa: E402
from preprocessing.sar import despeckle, looks_like_decibels  # noqa: E402
from preprocessing.terrain import slope_aspect, terrain_shadow_for_scene  # noqa: E402
from utils.crs import pixel_area_m2  # noqa: E402

RAW = ROOT / "data" / "raw" / "baige_2018"
BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
STEM = "S2_47RMQ_20181109T040948"
SUN_ZENITH, SUN_AZIMUTH = 50.0815177920521, 161.174680325524

cfg = load_config_with_overlay("baige_2018", load_env=False)
SCALE = cfg.detection.water.optical.reflectance_scale
arrays = np.load(ROOT / "data" / "processed" / "baige_arrays.npz")
with rasterio.open(RAW / "DEM_GLO30_v02_EPSG32647.tif") as s:
    transform, crs = s.transform, s.crs
cell = float(abs(transform.a))
area = pixel_area_m2(transform, crs)
dem = arrays["dem"]

with rasterio.open(RAW / f"{STEM}_refl.tif") as s:
    refl = {n: s.read(i + 1).astype("float64") for i, n in enumerate(BANDS)}
with rasterio.open(RAW / f"{STEM}_qa.tif") as s:
    qa = {n: s.read(i + 1) for i, n in enumerate(s.descriptions) if n}
cs = None
if (RAW / f"{STEM}_cs.tif").is_file():
    with rasterio.open(RAW / f"{STEM}_cs.tif") as s:
        cs = {n: s.read(i + 1).astype("float64")
              for i, n in enumerate(s.descriptions) if n}
masks = build_masks(cfg, scl=qa.get("SCL"),
                    cloud_score=None if cs is None else select_cloud_score(cs, cfg))

# ---------------------------------------------------- 1. the fusion
unfused = optical_water_mask(refl["B3"], refl["B8"], refl["B11"], cfg,
                             invalid=masks.unusable).water
print(f"Phase 3 optical mask (what every Baige run used): "
      f"{int(unfused.sum())} px = {unfused.sum() * area / 1e6:.4f} km2")

terrain = terrain_shadow_for_scene(cfg, dem, cell, SUN_AZIMUTH, SUN_ZENITH)
shadow = terrain["terrain_shadow"].astype(bool)
illum = terrain["illumination"]
slope = slope_aspect(dem, cell).slope_deg
print(f"terrain shadow on this scene: {int(shadow.sum())} px "
      f"({shadow.mean():.1%} of the AOI)")

vv = arrays["vv_post"]
if not looks_like_decibels(vv):
    raise SystemExit("VV is not in dB; the fusion expects dB")
vv = despeckle(vv, cfg)
decision = sar_water_threshold(vv, cfg)
print(f"SAR threshold: available={decision.available} "
      f"method={decision.method}"
      + (f" value={decision.value:.2f} dB" if decision.value is not None else "")
      + (f" reason={decision.reason}" if decision.reason else ""))
sar_thr = decision.value

result = fuse(
    cfg,
    water_index=mndwi(refl["B3"], refl["B11"]),
    water_index_threshold=cfg.detection.water.optical.mndwi_threshold,
    nir_reflectance=refl["B8"] * SCALE,
    slope_deg=slope,
    illumination=illum,
    terrain_shadow=shadow,
    sar_db=vv,
    sar_threshold_db=sar_thr,
    persistence=None,
    optical_invalid=masks.unusable,
)
fused = result.water
print(f"Phase 4 fused water: {int(fused.sum())} px = "
      f"{fused.sum() * area / 1e6:.4f} km2")
removed = unfused & ~fused
added = fused & ~unfused
print(f"  removed by fusion: {int(removed.sum())} px "
      f"({100 * removed.sum() / max(unfused.sum(), 1):.1f}% of the Phase 3 mask)")
print(f"  added by fusion:   {int(added.sum())} px")
if removed.any():
    print(f"  removed pixels: {float(shadow[removed].mean()):.1%} were in "
          f"terrain shadow; median DEM {np.median(dem[removed]):.0f} m, "
          f"median slope {np.median(slope[removed]):.1f} deg")

# ---------------------------------------------- 2. a lake must be level
print(f"\n{'=' * 70}\nA LAKE SURFACE MUST BE LEVEL\n{'=' * 70}")
water_pre, _ = (
    optical_water_mask(
        *[rasterio.open(RAW / "S2_47RMQ_20181102T041940_refl.tif").read(i + 1)
          .astype("float64") for i in (1, 3, 4)], cfg,
        invalid=arrays["invalid_pre"],
    ).water, None
)
river = float(np.median(dem[water_pre])) if water_pre.any() else float("nan")
print(f"pre-dam river surface (median DEM of 11-02 water): {river:.0f} m")

for label, mask in (("Phase 3 mask", unfused), ("Phase 4 fused", fused)):
    d = dem[mask]
    print(f"\n{label}: {int(mask.sum())} px, DEM {d.min():.0f}-{d.max():.0f} m "
          f"(sd {d.std():.1f} m)")
    for rise in (20.0, 50.0, 80.0, 120.0):
        above = int((d > river + rise).sum())
        print(f"  pixels more than {rise:5.0f} m above the river: {above:5d} "
              f"({100 * above / max(int(mask.sum()), 1):5.1f}%)")

impossible = unfused & (dem > river + 120.0)
print(f"\nPhase 3 'water' more than 120 m above the river: "
      f"{int(impossible.sum())} px = {impossible.sum() * area:,.0f} m2")
if impossible.any():
    print(f"  of those, {float(shadow[impossible].mean()):.1%} are in terrain "
          f"shadow and median slope is {np.median(slope[impossible]):.1f} deg")
    print(f"  the fusion removes {float((~fused)[impossible].mean()):.1%} of them")

out = ROOT / "outputs" / "baige_2018_fusion_check.json"
out.write_text(json.dumps({
    "scene": STEM,
    "sun_zenith_deg": SUN_ZENITH, "sun_azimuth_deg": SUN_AZIMUTH,
    "phase3_water_px": int(unfused.sum()),
    "phase3_water_km2": round(float(unfused.sum() * area / 1e6), 4),
    "phase4_fused_water_px": int(fused.sum()),
    "phase4_fused_water_km2": round(float(fused.sum() * area / 1e6), 4),
    "removed_px": int(removed.sum()),
    "removed_fraction_of_phase3": round(
        float(removed.sum()) / max(float(unfused.sum()), 1), 4),
    "added_px": int(added.sum()),
    "terrain_shadow_px": int(shadow.sum()),
    "sar_threshold_db": None if sar_thr is None else round(float(sar_thr), 2),
    "pre_dam_river_dem_m": round(river, 1),
    "phase3_px_above_river_plus_120m": int(impossible.sum()),
    "phase3_dem_range_m": [round(float(dem[unfused].min()), 1),
                           round(float(dem[unfused].max()), 1)],
    "phase4_dem_range_m": [round(float(dem[fused].min()), 1),
                           round(float(dem[fused].max()), 1)],
}, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
