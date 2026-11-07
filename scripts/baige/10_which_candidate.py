"""Which blockage candidate holds the impounded water, tested against gained-water elevation rather than flow accumulation alone.

Supports: validation.md 22

Installed from the session that produced the result. Run from anywhere:

    python scripts/baige/10_which_candidate.py

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
from detection.barrier_lake import (  # noqa: E402
    _partition_by_proximity,
    _pixels,
    _trace_along_stream,
    find_barrier_lakes,
)
from utils.crs import pixel_area_m2  # noqa: E402

cfg = load_config_with_overlay("baige_2018", load_env=False)
st = cfg.detection.barrier_lake

arrays = np.load(ROOT / "data" / "processed" / "baige_arrays.npz")
p7 = np.load(ROOT / "data" / "processed" / "baige_phase7.npz")
with rasterio.open(ROOT / "data/raw/baige_2018/DEM_GLO30_v02_EPSG32647.tif") as s:
    transform, crs = s.transform, s.crs
cell = float(abs(transform.a))
area = pixel_area_m2(transform, crs)

dem = arrays["dem"]
streams, acc = p7["streams"], p7["accumulation"]
pre, post = p7["water_pre"], p7["water_post"]

gained = post & ~pre
lost = pre & ~post
print(f"gained water {gained.sum()} px, median DEM {np.median(dem[gained]):.0f} m")
print(f"lost water   {lost.sum()} px, median DEM {np.median(dem[lost]):.0f} m")
print(f"-> the gain is {np.median(dem[gained]) - np.median(dem[lost]):+.0f} m "
      f"above the loss, so the gain is UPSTREAM\n")

search_px = _pixels(st.upstream_search_m, cell)
width_px = _pixels(st.lake_width_m, cell)
site_keys = {k[5:]: k for k in p7.files if k.startswith("site_")}

rows = []
print(f"{'code':8s} {'site px':>7s} {'acc max':>9s} {'up trace':>8s} "
      f"{'dn trace':>8s} {'gained in up zone':>17s} {'lake found':>11s}")
for code in sorted(site_keys):
    site = p7[site_keys[code]].astype(bool)
    a = acc[site]
    a = a[np.isfinite(a)]
    if a.size == 0:
        continue
    ref = float(np.max(a))
    up = _trace_along_stream(site, streams, acc, ref, search_px, upstream=True)
    dn = _trace_along_stream(site, streams, acc, ref, search_px, upstream=False)
    uz, dz = _partition_by_proximity(up, dn, width_px)
    gained_up = int((gained & uz & ~dz).sum())
    lakes = find_barrier_lakes(
        cfg, blockage_site=site, streams=streams, water_post=post,
        water_pre=pre, cellsize_m=cell, pixel_area_m2=area,
        flow_accumulation=acc, dam_code=code,
    )
    largest = max((l.area_m2 for l in lakes), default=0.0)
    print(f"{code:8s} {int(site.sum()):7d} {ref:9,.0f} {int(up.sum()):8d} "
          f"{int(dn.sum()):8d} {gained_up * area:14,.0f} m2 "
          f"{largest:9,.0f} m2")
    rows.append({
        "code": code,
        "site_px": int(site.sum()),
        "accumulation_max_cells": round(ref, 1),
        "upstream_trace_px": int(up.sum()),
        "downstream_trace_px": int(dn.sum()),
        "gained_water_in_upstream_zone_m2": round(gained_up * area, 1),
        "largest_lake_m2": round(float(largest), 1),
        "lake_count": len(lakes),
    })

best = max(rows, key=lambda r: r["gained_water_in_upstream_zone_m2"])
print(f"\nmost gained water upstream: {best['code']} with "
      f"{best['gained_water_in_upstream_zone_m2']:,.0f} m2 "
      f"(largest lake {best['largest_lake_m2']:,.0f} m2)")
print(f"total gained water anywhere: {gained.sum() * area:,.0f} m2")

out = ROOT / "outputs" / "baige_2018_phase8_candidate_choice.json"
out.write_text(json.dumps({
    "gained_water_m2": round(float(gained.sum() * area), 1),
    "gained_median_dem_m": round(float(np.median(dem[gained])), 1),
    "lost_water_m2": round(float(lost.sum() * area), 1),
    "lost_median_dem_m": round(float(np.median(dem[lost])), 1),
    "candidates": rows,
    "most_gained_upstream": best["code"],
}, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
