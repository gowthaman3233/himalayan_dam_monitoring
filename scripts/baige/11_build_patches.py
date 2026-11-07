"""Assemble the 15-channel stack from real imagery and cut demonstration patches. The labels are the project's own detectors, so NOT training data.

Supports: validation.md 27

Installed from the session that produced the result. Run from anywhere:

    python scripts/baige/11_build_patches.py

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
from config.schema import Config  # noqa: E402
from detection.landslide_change import ndvi, snow_mask_from_config  # noqa: E402
from detection.shadow_rejection import fuse  # noqa: E402
from detection.water import mndwi, ndwi, sar_water_threshold  # noqa: E402
from models.build_patches import assemble_stack, build_patches, write_report  # noqa: E402
from preprocessing.cloud_mask import build_masks, select_cloud_score  # noqa: E402
from preprocessing.sar import despeckle  # noqa: E402
from preprocessing.terrain import slope_aspect, terrain_shadow_for_scene  # noqa: E402

RAW = ROOT / "data" / "raw" / "baige_2018"
BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
STEM = "S2_47RMQ_20181109T040948"
SAR = "S1_ASC099_20181108T112511"

cfg = load_config_with_overlay("baige_2018", load_env=False)
SCALE = cfg.detection.water.optical.reflectance_scale
arrays = np.load(ROOT / "data" / "processed" / "baige_arrays.npz")
dem = arrays["dem"]

with rasterio.open(RAW / "DEM_GLO30_v02_EPSG32647.tif") as s:
    transform, crs = s.transform, s.crs
cell = float(abs(transform.a))

with rasterio.open(RAW / f"{STEM}_refl.tif") as s:
    refl = {n: s.read(i + 1).astype("float64") for i, n in enumerate(BANDS)}
with rasterio.open(RAW / f"{STEM}_qa.tif") as s:
    qa = {n: s.read(i + 1) for i, n in enumerate(s.descriptions) if n}
with rasterio.open(RAW / f"{STEM}_cs.tif") as s:
    cs = {n: s.read(i + 1).astype("float64") for i, n in enumerate(s.descriptions) if n}
with rasterio.open(RAW / f"{SAR}.tif") as s:
    sar = {n: s.read(i + 1).astype("float64") for i, n in enumerate(s.descriptions) if n}
print(f"SAR bands available: {sorted(sar)}")

meta = json.load(open(RAW / f"{STEM}_refl.tif.json", encoding="utf-8"))
masks = build_masks(cfg, scl=qa.get("SCL"), cloud_score=select_cloud_score(cs, cfg))
terrain = terrain_shadow_for_scene(
    cfg, dem, cell, meta["sun_azimuth_deg"], meta["sun_zenith_deg"])
slope = slope_aspect(dem, cell).slope_deg
vv = despeckle(sar["VV"], cfg)
vh = despeckle(sar["VH"], cfg)

channels = {
    "S2_B2": refl["B2"] * SCALE, "S2_B3": refl["B3"] * SCALE,
    "S2_B4": refl["B4"] * SCALE, "S2_B8": refl["B8"] * SCALE,
    "S2_B11": refl["B11"] * SCALE, "S2_B12": refl["B12"] * SCALE,
    "NDWI": ndwi(refl["B3"], refl["B8"]),
    "MNDWI": mndwi(refl["B3"], refl["B11"]),
    "NDVI": ndvi(refl["B8"], refl["B4"]),
    "S1_VV": vv, "S1_VH": vh,
    "DEM": dem, "SLOPE": slope,
    "ILLUMINATION": terrain["illumination"],
    "TERRAIN_SHADOW": terrain["terrain_shadow"].astype(np.float32),
}
print(f"assembled {len(channels)} channel(s); config wants "
      f"{cfg.models.in_channels}")
stack = assemble_stack(channels, cfg)
print(f"stack {stack.shape}, finite fraction "
      f"{float(np.isfinite(stack).mean()):.3f}")

# A missing channel must be named, not zero-filled.
try:
    assemble_stack({k: v for k, v in channels.items() if k != "S1_VH"}, cfg)
except Exception as exc:
    print(f"\nmissing channel refused: {str(exc)[:88]}...")

# --- a demonstration label raster from this project's own detections -------
snow = snow_mask_from_config(cfg, refl["B3"], refl["B11"], refl["B8"] * SCALE)
invalid = masks.unusable | snow
res = fuse(
    cfg, water_index=channels["MNDWI"],
    water_index_threshold=cfg.detection.water.optical.mndwi_threshold,
    nir_reflectance=channels["S2_B8"], slope_deg=slope,
    illumination=terrain["illumination"],
    terrain_shadow=terrain["terrain_shadow"].astype(bool),
    sar_db=vv, sar_threshold_db=sar_water_threshold(vv, cfg).value,
    persistence=None, optical_invalid=invalid,
)
water = res.water & ~invalid
change = arrays["change"].astype(bool)

IGNORE = cfg.models.ignore_index
labels = np.full(dem.shape, IGNORE, dtype=np.uint8)
labels[terrain["terrain_shadow"].astype(bool) & ~masks.unusable] = 3
labels[snow] = 4
labels[change] = 2
labels[water] = 1
# Confidently-land: low slope, illuminated, not anything above.
land = (slope < 25.0) & (terrain["illumination"] > 0.5) & (labels == IGNORE) \
    & ~masks.unusable
labels[land] = 0
print(f"\ndemonstration labels: "
      f"{ {n: int((labels==i).sum()) for i, n in enumerate(cfg.models.classes)} }")
print(f"  unlabelled (ignore_index): {int((labels==IGNORE).sum())}")

# Patch size 256 against a 599x599 grid gives few patches; use 128 here so the
# demonstration produces a usable number. The gate's own patches stay at 256.
data = cfg.model_dump(mode="python")
data["models"]["patch"].update(size_px=128, stride_px=64)
demo = Config.model_validate(data)

out = ROOT / "data" / "processed" / "baige_demo_patches"
report = build_patches(
    demo, channels, labels,
    transform=transform, out_dir=out, crs=crs, event="baige-2018",
    unseen=masks.unusable,
)
print()
for key, value in report.as_dict().items():
    print(f"  {key}: {value}")
write_report(report, ROOT / "outputs" / "baige_2018_patch_build.json")

# Round-trip through the dataset layer.
from models.dataset import PatchDataset, assign_splits, discover_patches  # noqa: E402

refs = discover_patches(out)
splits = assign_splits(refs, demo)
print(f"\nround trip: {len(refs)} patch(es) -> "
      f"{ {k: len(v) for k, v in splits.items()} }")
if splits["train"]:
    ds = PatchDataset(splits["train"], demo)
    x, y = ds[0]
    print(f"  first training item: x {tuple(x.shape)}, y {tuple(y.shape)}")
    print(f"  train class pixels: {ds.class_pixel_counts()}")
