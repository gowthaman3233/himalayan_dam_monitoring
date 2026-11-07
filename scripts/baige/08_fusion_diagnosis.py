"""Why the fusion adds pixels over optical nodata: what each evidence term actually saw.

Supports: validation.md 24 (Finding 4a)

Installed from the session that produced the result. Run from anywhere:

    python scripts/baige/08_fusion_diagnosis.py

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
from detection.landslide_change import snow_mask_from_config  # noqa: E402
from detection.shadow_rejection import fuse  # noqa: E402
from detection.water import mndwi, optical_water_mask, sar_water_threshold  # noqa: E402
from preprocessing.cloud_mask import build_masks, select_cloud_score  # noqa: E402
from preprocessing.sar import despeckle  # noqa: E402
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

terrain = terrain_shadow_for_scene(cfg, dem, cell, SUN_AZIMUTH, SUN_ZENITH)
slope = slope_aspect(dem, cell).slope_deg
vv = despeckle(arrays["vv_post"], cfg)
thr = sar_water_threshold(vv, cfg)

unfused = optical_water_mask(refl["B3"], refl["B8"], refl["B11"], cfg,
                             invalid=masks.unusable).water
res = fuse(
    cfg,
    water_index=mndwi(refl["B3"], refl["B11"]),
    water_index_threshold=cfg.detection.water.optical.mndwi_threshold,
    nir_reflectance=refl["B8"] * SCALE,
    slope_deg=slope,
    illumination=terrain["illumination"],
    terrain_shadow=terrain["terrain_shadow"].astype(bool),
    sar_db=vv, sar_threshold_db=thr.value,
    persistence=None,
    optical_invalid=masks.unusable,
)
added = res.water & ~unfused
print(f"fusion adds {int(added.sum())} px over the Phase 3 mask\n")

river = 2870.0
high = added & (dem > river + 120.0)
print(f"of the added pixels, {int(high.sum())} are >120 m above the river "
      f"({100 * high.sum() / max(added.sum(), 1):.1f}%)")

nir = refl["B8"] * SCALE
snow = snow_mask_from_config(cfg, refl["B3"], refl["B11"], nir)
print(f"\nthe project's own snow screen flags {int(snow.sum())} px "
      f"({snow.mean():.1%} of the AOI)")
print(f"  of the ADDED pixels, {float(snow[added].mean()):.1%} are snow by "
      f"that screen")
print(f"  of the added pixels >120 m up, {float(snow[high].mean()):.1%} are snow")

print(f"\nwhat each term saw on the added pixels (median):")
print(f"  {'term':22s} {'support':>8s}  {'weight':>6s}")
for name, term in res.terms.items():
    sup = term.support[added] if term.support is not None else None
    w = getattr(cfg.detection.shadow_rejection.weights, name, None)
    if sup is None or sup.size == 0:
        print(f"  {name:22s} {'n/a':>8s}  {w if w is not None else '?':>6}")
    else:
        print(f"  {name:22s} {float(np.median(sup)):8.3f}  "
              f"{w if w is not None else '?':>6}")

print(f"\nraw values on the added pixels (median):")
print(f"  NIR reflectance  {float(np.median(nir[added])):.3f}  "
      f"(water requires < {cfg.detection.shadow_rejection.membership.nir.water_max_reflectance})")
print(f"  slope            {float(np.median(slope[added])):.1f} deg  "
      f"(water requires < {cfg.detection.shadow_rejection.membership.slope.water_max_deg})")
print(f"  MNDWI            {float(np.median(mndwi(refl['B3'], refl['B11'])[added])):.3f}")
print(f"  VV               {float(np.median(vv[added])):.1f} dB  "
      f"(threshold {thr.value:.1f})")
print(f"  DEM              {float(np.median(dem[added])):.0f} m")
print(f"  p_water          {float(np.median(res.p_water[added])):.3f}")

out = ROOT / "outputs" / "baige_2018_fusion_diagnosis.json"
out.write_text(json.dumps({
    "scene": STEM,
    "added_px": int(added.sum()),
    "added_above_river_plus_120m_px": int(high.sum()),
    "snow_screen_px": int(snow.sum()),
    "added_that_are_snow_fraction": round(float(snow[added].mean()), 4),
    "high_added_that_are_snow_fraction": round(float(snow[high].mean()), 4),
    "medians_on_added": {
        "nir_reflectance": round(float(np.median(nir[added])), 4),
        "slope_deg": round(float(np.median(slope[added])), 2),
        "mndwi": round(float(np.median(mndwi(refl["B3"], refl["B11"])[added])), 4),
        "vv_db": round(float(np.median(vv[added])), 2),
        "dem_m": round(float(np.median(dem[added])), 1),
        "p_water": round(float(np.median(res.p_water[added])), 4),
    },
    "term_support_medians_on_added": {
        n: (None if t.support is None else round(float(np.median(t.support[added])), 4))
        for n, t in res.terms.items()
    },
}, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
