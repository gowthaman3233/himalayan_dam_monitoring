"""Derive the stream network, flow direction and accumulation from the Baige DEM, and check the channel against observed water.

Supports: validation.md 21 (Inputs)

Installed from the session that produced the result. Run from anywhere:

    python scripts/baige/02_streams.py

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
from detection.water import optical_water_mask  # noqa: E402
from preprocessing.hydrology import (  # noqa: E402
    derive_stream_network,
    read_stream_mask,
    stream_statistics,
)

cfg = load_config_with_overlay("baige_2018", load_env=False)
dem_path = ROOT / "data/raw/baige_2018/DEM_GLO30_v02_EPSG32647.tif"
out_dir = ROOT / "data" / "processed" / "baige_hydro"

print(f"DEM: {dem_path.name}")
print(f"depression handling: {cfg.preprocessing.hydrology.depression_handling}")
print(f"stream threshold: {cfg.preprocessing.hydrology.stream_threshold_cells} cells")

products = derive_stream_network(dem_path, cfg, out_dir=out_dir, prefix="baige")
print("\nproducts:")
for key, value in products.as_dict().items():
    print(f"  {key}: {value}")

streams = read_stream_mask(products.streams)
print(f"\nstream mask: {streams.sum()} px of {streams.size} "
      f"({100 * streams.sum() / streams.size:.2f}%)")

stats = stream_statistics(products.streams, 10.0)
print("stream statistics:")
for key, value in stats.items():
    print(f"  {key}: {value}")

with rasterio.open(products.flow_accumulation) as src:
    accumulation = src.read(1, masked=True).filled(0.0)

# --- the check that matters: does the derived channel match observed water? --
arrays = np.load(ROOT / "data" / "processed" / "baige_arrays.npz")
water_pre = optical_water_mask(
    arrays["b3_pre"], arrays["b8_pre"], arrays["b11_pre"], cfg,
    invalid=arrays["invalid_pre"],
).water

if streams.shape != water_pre.shape:
    raise SystemExit(
        f"grid mismatch: streams {streams.shape} vs water {water_pre.shape}"
    )

# Streams are one pixel wide; the river is tens of metres. Dilate the stream
# line before asking whether it falls on water, otherwise the comparison
# punishes a correct line for being thin.
def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    out = mask.copy()
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            out |= np.roll(np.roll(mask, dr, axis=0), dc, axis=1)
    return out

near_stream = dilate(streams, 3)  # 30 m either side
on_water = water_pre & near_stream
print(f"\nobserved pre-event water: {water_pre.sum()} px")
print(f"  within 30 m of a derived stream: {on_water.sum()} px "
      f"({100 * on_water.sum() / max(water_pre.sum(), 1):.1f}%)")

main = accumulation >= np.percentile(accumulation[streams], 90) if streams.any() else None
if main is not None:
    print(f"  main-stem cells (top decile of accumulation on streams): "
          f"{int((main & streams).sum())} px")

report = {
    "dem": dem_path.name,
    "products": products.as_dict(),
    "stream_px": int(streams.sum()),
    "stream_fraction": round(float(streams.sum()) / streams.size, 5),
    "stream_statistics": {k: (round(v, 4) if isinstance(v, float) else v)
                          for k, v in stats.items()},
    "observed_water_px": int(water_pre.sum()),
    "observed_water_within_30m_of_stream_px": int(on_water.sum()),
    "observed_water_within_30m_of_stream_fraction": round(
        float(on_water.sum()) / max(float(water_pre.sum()), 1), 4
    ),
}
out = ROOT / "outputs" / "baige_2018_streams.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
