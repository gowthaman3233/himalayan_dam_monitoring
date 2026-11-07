"""Vary the candidate-grouping settings and ask whether the same dam is identified each time. 10/10 fused, 4/10 unfused.

Supports: validation.md 26

Installed from the session that produced the result. Run from anywhere:

    python scripts/baige/06_mainstem_robustness.py

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
from detection.barrier_lake import (  # noqa: E402
    _partition_by_proximity, _pixels, _trace_along_stream,
)
from detection.blockage import detect_blockages  # noqa: E402
from detection.water import optical_water_mask  # noqa: E402
from utils.crs import pixel_area_m2  # noqa: E402

cfg = load_config_with_overlay("baige_2018", load_env=False)
arrays = np.load(ROOT / "data" / "processed" / "baige_arrays.npz")
p7 = np.load(ROOT / "data" / "processed" / "baige_phase7.npz")
hydro = ROOT / "data" / "processed" / "baige_hydro"
with rasterio.open(hydro / "baige_streams.tif") as s:
    streams = s.read(1) > 0
with rasterio.open(hydro / "baige_d8_accumulation.tif") as s:
    acc = s.read(1, masked=True).filled(0.0)
with rasterio.open(ROOT / "data/raw/baige_2018/DEM_GLO30_v02_EPSG32647.tif") as s:
    transform, crs = s.transform, s.crs
cell = float(abs(transform.a))
area = pixel_area_m2(transform, crs)

# The AUTHORITATIVE inputs: the fused change map and fused water masks from
# the re-derivation (validation 25-26). The unfused versions in
# baige_arrays.npz / baige_phase7.npz are superseded and would make this
# sweep's "shipped default" row disagree with the published result.
fused = np.load(ROOT / "data" / "processed" / "baige_fused.npz")
change = fused["change"].astype(bool)
water_pre = fused["water_pre"]
water_post = fused["water_post"]
gained = water_post & ~water_pre
main_stem_max = float(acc[streams].max())
print(f"AOI main-stem maximum drainage: {main_stem_max:,.0f} cells")
print(f"a candidate is 'on the main stem' if it reaches >=90% of that "
      f"({0.9 * main_stem_max:,.0f})\n")


def with_blockage(**overrides) -> Config:
    data = cfg.model_dump(mode="python")
    data["detection"]["blockage"].update(overrides)
    return Config.model_validate(data)


def rank(config: Config):
    """Candidates ranked by gained water in their own traced upstream reach."""
    cands = detect_blockages(
        config, landslides=change, streams=streams, cellsize_m=cell,
        pixel_area_m2=area, flow_accumulation=acc,
        water_pre=water_pre, water_post=water_post,
        transform=transform, crs=crs,
        pre_date="2018-11-02", post_date="2018-11-09",
    )
    rows = []
    sp = _pixels(config.detection.barrier_lake.upstream_search_m, cell)
    wp = _pixels(config.detection.barrier_lake.lake_width_m, cell)
    for c in cands:
        a = acc[c.site_mask][np.isfinite(acc[c.site_mask])]
        if a.size == 0:
            continue
        ref = float(a.max())
        up = _trace_along_stream(c.site_mask, streams, acc, ref, sp, upstream=True)
        dn = _trace_along_stream(c.site_mask, streams, acc, ref, sp, upstream=False)
        uz, dz = _partition_by_proximity(up, dn, wp)
        rows.append({
            "code": c.dam_code,
            "confidence": round(c.confidence, 4),
            "drainage": ref,
            "gained_m2": float((gained & uz & ~dz).sum() * area),
            "area_m2": c.landslide_area_m2,
        })
    rows.sort(key=lambda r: -r["gained_m2"])
    return rows


SWEEP = [
    ("shipped default", {}),
    ("merge 250 m", {"merge_along_stream_m": 250.0}),
    ("merge 750 m", {"merge_along_stream_m": 750.0}),
    ("merge 1500 m", {"merge_along_stream_m": 1500.0}),
    ("min area 500 m2", {"min_landslide_area_m2": 500.0}),
    ("min area 2500 m2", {"min_landslide_area_m2": 2500.0}),
    ("stream reach 30 m", {"max_distance_to_stream_m": 30.0}),
    ("stream reach 100 m", {"max_distance_to_stream_m": 100.0}),
    ("evidence search 300 m", {"evidence_search_m": 300.0}),
    ("evidence search 800 m", {"evidence_search_m": 800.0}),
]

print(f"{'variant':24s} {'cands':>5s} {'top':>8s} {'drainage':>10s} "
      f"{'gained m2':>11s} {'main stem?':>10s}")
results = []
for label, overrides in SWEEP:
    rows = rank(with_blockage(**overrides))
    if not rows:
        print(f"{label:24s} {'0':>5s}   no candidates")
        results.append({"variant": label, "candidates": 0})
        continue
    top = rows[0]
    on_main = top["drainage"] >= 0.9 * main_stem_max
    print(f"{label:24s} {len(rows):5d} {top['code']:>8s} "
          f"{top['drainage']:10,.0f} {top['gained_m2']:11,.0f} "
          f"{'YES' if on_main else 'no':>10s}")
    results.append({
        "variant": label, "candidates": len(rows), "top": top["code"],
        "top_drainage_cells": round(top["drainage"], 1),
        "top_gained_m2": round(top["gained_m2"], 1),
        "top_on_main_stem": on_main,
        "top_confidence": top["confidence"],
        "top_landslide_area_m2": round(top["area_m2"], 1),
    })

agreed = [r for r in results if r.get("top_on_main_stem")]
usable = [r for r in results if r.get("candidates", 0) > 0]
print()
print(f"variants where the most-impounding candidate is also on the main stem: "
      f"{len(agreed)}/{len(usable)}")
counts = sorted({r["candidates"] for r in usable})
print(f"candidate counts across variants: {counts}")

out = ROOT / "outputs" / "baige_2018_mainstem_robustness.json"
out.write_text(json.dumps({
    "question": ("whether the agreement between impounded water and main-stem "
                 "drainage survives changes to the settings that decide "
                 "candidate grouping"),
    "main_stem_max_cells": round(main_stem_max, 1),
    "main_stem_threshold_fraction": 0.9,
    "variants": results,
    "agreement_count": len(agreed),
    "variants_with_candidates": len(usable),
}, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
