"""Where the published Baige coordinate actually is: 52.9 deg slope, 471 m above the river.

Supports: validation.md 20 (C.0)

Installed from the session that produced the result. Run from anywhere:

    python scripts/baige/09_coordinate_check.py

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

from pyproj import Transformer  # noqa: E402

from config.loader import load_config_with_overlay  # noqa: E402
from detection.water import optical_water_mask  # noqa: E402

LON, LAT = 98.70499, 31.08234

cfg = load_config_with_overlay("baige_2018", load_env=False)
arrays = np.load(ROOT / "data" / "processed" / "baige_arrays.npz")

with rasterio.open(ROOT / "data/raw/baige_2018/DEM_GLO30_v02_EPSG32647.tif") as src:
    transform, crs = src.transform, src.crs

to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
px, py = to_utm.transform(LON, LAT)
prow, pcol = rasterio.transform.rowcol(transform, px, py)

dem = arrays["dem"]
slope = arrays["slope"]
print(f"published coordinate -> row {prow}, col {pcol}")
print(f"  DEM elevation {dem[prow, pcol]:.1f} m, slope {slope[prow, pcol]:.1f} deg")

pre = optical_water_mask(
    arrays["b3_pre"], arrays["b8_pre"], arrays["b11_pre"], cfg,
    invalid=arrays["invalid_pre"],
).water

rows, cols = np.nonzero(pre)
# 10 m grid, so pixel offsets are decametres.
dist = np.hypot(rows - prow, cols - pcol) * 10.0
nearest = int(np.argmin(dist))
print(f"\npre-event water: {pre.sum()} px, median elevation "
      f"{np.median(dem[pre]):.1f} m")
print(f"nearest pre-event water pixel: {dist[nearest]:,.0f} m away, "
      f"DEM {dem[rows[nearest], cols[nearest]]:.1f} m")
print(f"drop from the coordinate to the river: "
      f"{dem[prow, pcol] - dem[rows[nearest], cols[nearest]]:+.1f} m")

# Local relief: is the coordinate on a hillside or a valley floor?
r0, r1 = max(prow - 15, 0), min(prow + 16, dem.shape[0])
c0, c1 = max(pcol - 15, 0), min(pcol + 16, dem.shape[1])
patch = dem[r0:r1, c0:c1]
print(f"\nwithin 150 m of the coordinate: DEM {patch.min():.0f}-{patch.max():.0f} m "
      f"(relief {np.ptp(patch):.0f} m), median slope "
      f"{np.median(slope[r0:r1, c0:c1]):.1f} deg")

report = {
    "published_coordinate": {"lon": LON, "lat": LAT},
    "dem_elevation_m": round(float(dem[prow, pcol]), 1),
    "slope_deg": round(float(slope[prow, pcol]), 1),
    "pre_event_water_median_elevation_m": round(float(np.median(dem[pre])), 1),
    "horizontal_distance_to_nearest_water_m": round(float(dist[nearest]), 1),
    "drop_to_river_m": round(
        float(dem[prow, pcol] - dem[rows[nearest], cols[nearest]]), 1
    ),
    "local_relief_150m_m": round(float(np.ptp(patch)), 1),
    "local_median_slope_deg": round(float(np.median(slope[r0:r1, c0:c1])), 1),
    "interpretation": (
        "The published coordinate lies on the valley side, several hundred "
        "metres above the Jinsha water surface. It marks the landslide body or "
        "source area on the right bank, not the blockage point in the channel."
    ),
}
out = ROOT / "outputs" / "baige_2018_coordinate_check.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
