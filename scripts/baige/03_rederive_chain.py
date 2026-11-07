"""THE AUTHORITATIVE RUN. Fuses water per date (snow screened, persistence wired), then re-derives Phases 5, 7, 8, 9 and 11 on it.

Supports: validation.md 25 and 26

Installed from the session that produced the result. Run from anywhere:

    python scripts/baige/03_rederive_chain.py

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

from analysis.change import AreaObservation, analyse_trend  # noqa: E402
from analysis.risk import assess_risk  # noqa: E402
from config.loader import load_config_with_overlay  # noqa: E402
from config.schema import Config  # noqa: E402
from detection.barrier_lake import (  # noqa: E402
    _partition_by_proximity, _pixels, _trace_along_stream, find_barrier_lakes,
)
from detection.blockage import detect_blockages  # noqa: E402
from detection.landslide_change import (  # noqa: E402
    detect_change, landslide_polygons, ndvi, snow_mask_from_config,
)
from detection.shadow_rejection import fuse  # noqa: E402
from detection.water import mndwi, optical_water_mask, sar_water_threshold  # noqa: E402
from preprocessing.cloud_mask import build_masks, select_cloud_score  # noqa: E402
from preprocessing.sar import despeckle  # noqa: E402
from preprocessing.terrain import slope_aspect, terrain_shadow_for_scene  # noqa: E402
from utils.crs import pixel_area_m2  # noqa: E402

RAW = ROOT / "data" / "raw" / "baige_2018"
BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
SCENES = [
    ("S2_47RMQ_20181102T041940", Date(2018, 11, 2)),
    ("S2_47RMQ_20181109T040948", Date(2018, 11, 9)),
    ("S2_47RMQ_20181119T040944", Date(2018, 11, 19)),
    ("S2_47RMQ_20181122T041940", Date(2018, 11, 22)),
]
PRE, POST = Date(2018, 11, 2), Date(2018, 11, 9)
DAM_FORMED = Date(2018, 11, 3)

cfg = load_config_with_overlay("baige_2018", load_env=False)
SCALE = cfg.detection.water.optical.reflectance_scale
arrays = np.load(ROOT / "data" / "processed" / "baige_arrays.npz")
hydro = ROOT / "data" / "processed" / "baige_hydro"
with rasterio.open(hydro / "baige_streams.tif") as s:
    streams = (s.read(1) > 0)
with rasterio.open(hydro / "baige_d8_accumulation.tif") as s:
    acc = s.read(1, masked=True).filled(0.0)
with rasterio.open(RAW / "DEM_GLO30_v02_EPSG32647.tif") as s:
    transform, crs = s.transform, s.crs
cell = float(abs(transform.a))
area = pixel_area_m2(transform, crs)
dem = arrays["dem"]
slope = slope_aspect(dem, cell).slope_deg
vv_pre = despeckle(arrays["vv_pre"], cfg)
vv_post = despeckle(arrays["vv_post"], cfg)
sar_thr = sar_water_threshold(vv_post, cfg).value


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
    meta = json.load(open(RAW / f"{stem}_refl.tif.json", encoding="utf-8"))
    return refl, masks, meta


print("=== fusing water on all four dates ===")
scenes = {}
for stem, when in SCENES:
    refl, masks, meta = read(stem)
    nir = refl["B8"] * SCALE
    snow = snow_mask_from_config(cfg, refl["B3"], refl["B11"], nir)
    scenes[when] = {
        "refl": refl, "masks": masks, "meta": meta, "nir": nir, "snow": snow,
        "phase3": optical_water_mask(refl["B3"], refl["B8"], refl["B11"], cfg,
                                     invalid=masks.unusable).water,
        "invalid": masks.unusable | snow,
    }

seen = np.zeros(dem.shape); wetc = np.zeros(dem.shape)
for d in scenes.values():
    ok = ~d["invalid"]
    seen += ok
    wetc += d["phase3"] & ok
persistence = np.divide(wetc, seen, out=np.full(dem.shape, np.nan), where=seen > 0)

for when, d in scenes.items():
    terrain = terrain_shadow_for_scene(
        cfg, dem, cell, d["meta"]["sun_azimuth_deg"], d["meta"]["sun_zenith_deg"])
    res = fuse(
        cfg,
        water_index=mndwi(d["refl"]["B3"], d["refl"]["B11"]),
        water_index_threshold=cfg.detection.water.optical.mndwi_threshold,
        nir_reflectance=d["nir"], slope_deg=slope,
        illumination=terrain["illumination"],
        terrain_shadow=terrain["terrain_shadow"].astype(bool),
        sar_db=vv_post if when >= POST else vv_pre, sar_threshold_db=sar_thr,
        persistence=persistence, persistence_observations=int(np.median(seen)),
        optical_invalid=d["invalid"],
    )
    d["optical_ok"] = ~d["invalid"]
    d["fused"] = res.water & d["optical_ok"]
    d["terrain"] = terrain
    print(f"  {when}: optical ok {d['optical_ok'].mean():6.1%}  "
          f"phase3 {int(d['phase3'].sum()):5d} -> fused {int(d['fused'].sum()):5d} px")

water_pre, water_post = scenes[PRE]["fused"], scenes[POST]["fused"]

# ----------------------------------------------------------------- Phase 5 --
print("\n=== Phase 5 on fused water ===")
pre_s, post_s = scenes[PRE], scenes[POST]


def bright(d):
    return (d["refl"]["B4"] + d["refl"]["B11"] + d["refl"]["B12"]) / 3.0 * SCALE


def with_slope(lo: float, med: float) -> Config:
    data = cfg.model_dump(mode="python")
    g = data["detection"]["landslide_change"]["gating"]
    g["min_slope_deg"] = lo
    g["min_median_slope_deg"] = med
    return Config.model_validate(data)


change_runs = {}
for label, conf in (("cited >15 deg", cfg), ("dam-tuned >1 deg", with_slope(1.0, 1.0))):
    r = detect_change(
        conf,
        ndvi_pre=ndvi(pre_s["refl"]["B8"], pre_s["refl"]["B4"]),
        ndvi_post=ndvi(post_s["refl"]["B8"], post_s["refl"]["B4"]),
        brightness_pre=bright(pre_s), brightness_post=bright(post_s),
        sar_db_pre=vv_pre, sar_db_post=vv_post,
        slope_deg=slope,
        snow_pre=pre_s["snow"], snow_post=post_s["snow"],
        water_post=water_post,
        invalid_pre=pre_s["invalid"], invalid_post=post_s["invalid"],
    )
    polys = landslide_polygons(r, transform, crs, conf, slope_deg=slope)
    print(f"  {label}: {r.changed_pixels} px = "
          f"{r.changed_pixels * area / 1e6:.4f} km2, {len(polys)} polygons")
    change_runs[label] = {
        "changed_px": int(r.changed_pixels),
        "changed_km2": round(r.changed_pixels * area / 1e6, 4),
        "polygons": int(len(polys)),
        "_result": r,
    }
change = change_runs["dam-tuned >1 deg"]["_result"].change
# Save the fused change map and water masks so later analyses can reuse the
# authoritative inputs rather than the superseded unfused ones.
np.savez_compressed(
    ROOT / "data" / "processed" / "baige_fused.npz",
    change=change, water_pre=water_pre, water_post=water_post,
)
print("  saved data/processed/baige_fused.npz")

# ----------------------------------------------------------------- Phase 7 --
print("\n=== Phase 7 on fused water ===")
cands = detect_blockages(
    cfg, landslides=change, streams=streams, cellsize_m=cell,
    pixel_area_m2=area, flow_accumulation=acc,
    water_pre=water_pre, water_post=water_post,
    transform=transform, crs=crs,
    pre_date=str(PRE), post_date=str(POST),
)
print(f"  {len(cands)} candidate(s)")
gained = water_post & ~water_pre
best, best_gain = None, -1.0
rows = []
for c in cands:
    a = acc[c.site_mask][np.isfinite(acc[c.site_mask])]
    if a.size == 0:
        continue
    ref = float(a.max())
    sp = _pixels(cfg.detection.barrier_lake.upstream_search_m, cell)
    up = _trace_along_stream(c.site_mask, streams, acc, ref, sp, upstream=True)
    dn = _trace_along_stream(c.site_mask, streams, acc, ref, sp, upstream=False)
    uz, dz = _partition_by_proximity(
        up, dn, _pixels(cfg.detection.barrier_lake.lake_width_m, cell))
    g = float((gained & uz & ~dz).sum() * area)
    rows.append({"dam_code": c.dam_code, "confidence": round(c.confidence, 4),
                 "accumulation_max_cells": round(ref, 1),
                 "gained_upstream_m2": round(g, 1),
                 "landslide_area_m2": round(c.landslide_area_m2, 1)})
    if g > best_gain:
        best, best_gain = c, g
rows.sort(key=lambda r: -r["gained_upstream_m2"])
for r in rows[:4]:
    print(f"    {r['dam_code']}  conf {r['confidence']:.3f}  "
          f"acc {r['accumulation_max_cells']:>9,.0f}  "
          f"gained upstream {r['gained_upstream_m2']:>9,.0f} m2")
print(f"  -> lake-bearing candidate: {best.dam_code}")

# ------------------------------------------------------------- Phases 8/9 --
print("\n=== Phases 8 and 9 on fused water ===")
site = best.site_mask
ref = float(acc[site][np.isfinite(acc[site])].max())
sp = _pixels(cfg.detection.barrier_lake.upstream_search_m, cell)
up = _trace_along_stream(site, streams, acc, ref, sp, upstream=True)
dn = _trace_along_stream(site, streams, acc, ref, sp, upstream=False)
uz, dz = _partition_by_proximity(
    up, dn, _pixels(cfg.detection.barrier_lake.lake_width_m, cell))
zone = uz & ~dz

allw = np.zeros(dem.shape, bool)
for d in scenes.values():
    allw |= d["fused"] & zone
ceiling = float(dem[allw].max()) if allw.any() else float("nan")
floodable = zone & (dem <= ceiling)
thr_obs = cfg.detection.barrier_lake.min_observable_fraction

obs, series = [], []
for stem, when in SCENES:
    d = scenes[when]
    lakes = find_barrier_lakes(
        cfg, blockage_site=site, streams=streams, water_post=d["fused"],
        water_pre=water_pre, cellsize_m=cell, pixel_area_m2=area,
        flow_accumulation=acc, dam_code=best.dam_code,
    )
    la = max((l.area_m2 for l in lakes), default=0.0)
    frac = float((floodable & d["optical_ok"]).sum() / max(floodable.sum(), 1))
    if when < DAM_FORMED:
        status = "pre-event"
    elif frac < thr_obs:
        status = "GAP: zone too clouded"
        obs.append(AreaObservation.gap(
            when, f"only {frac:.0%} of the floodable zone observable",
            sensor="Sentinel-2 MSI"))
    elif not lakes:
        status = "GAP: no lake in an observable zone"
        obs.append(AreaObservation.gap(
            when, "no qualifying lake in an observable zone",
            sensor="Sentinel-2 MSI"))
    else:
        status = "measurement" + ("" if frac >= 0.999 else " (lower bound)")
        obs.append(AreaObservation(obs_date=when, area_m2=la,
                                   sensor="Sentinel-2 MSI",
                                   cloud_fraction=round(1 - frac, 4)))
    print(f"  {when}  zone obs {frac:6.1%}  lake {la:>9,.0f} m2  -> {status}")
    series.append({"date": str(when), "zone_observable": round(frac, 4),
                   "lake_area_m2": round(float(la), 1), "status": status})

trend = analyse_trend(cfg, obs, reference_date=max(o.obs_date for o in obs))
print(f"\n  {trend.describe()}")

# ---------------------------------------------------------------- Phase 11 --
print("\n=== Phase 11 on fused water ===")
ls_slope = float(np.median(slope[best.landslide_mask])) if best.landslide_mask.any() else None
risk = assess_risk(
    cfg,
    lake_growth_rate_m2_per_day=trend.rate_m2_per_day,
    lake_volume_m3=None,
    volume_unavailable_reason="Phase 10 withheld for this site (methods 10.9-10.12)",
    new_landslide_area_m2=best.landslide_area_m2,
    blockage_confidence=best.confidence,
    slope_deg=ls_slope,
    rainfall_mm_24h=None,
)
print(f"  score {risk.score:.4f}  level {risk.level}  "
      f"coverage {risk.data_coverage:.1%}")

out = ROOT / "outputs" / "baige_2018_rederived_on_fused_water.json"
out.write_text(json.dumps({
    "note": "supersedes the unfused numbers in validation 20-23",
    "sar_threshold_db": round(float(sar_thr), 2),
    "water_per_date": {
        str(w): {"optical_ok_fraction": round(float(d["optical_ok"].mean()), 4),
                 "phase3_px": int(d["phase3"].sum()),
                 "fused_px": int(d["fused"].sum())}
        for w, d in scenes.items()},
    "phase5": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
               for k, v in change_runs.items()},
    "phase7": {"candidates": len(cands), "ranked_by_gained_upstream": rows,
               "lake_bearing": best.dam_code,
               "confidence": round(best.confidence, 4)},
    "phase8_9": {"series": series, "trend": trend.as_dict()},
    "phase11": {"score": round(float(risk.score), 4), "level": risk.level,
                "data_coverage": round(float(risk.data_coverage), 4),
                "factors": [{"name": f.name, "available": f.available,
                             "value": None if f.value is None else round(float(f.value), 3),
                             "score": None if f.score is None else round(float(f.score), 4),
                             "weight": f.weight,
                             "contribution": round(float(f.contribution), 4)}
                            for f in risk.factors]},
}, indent=2, default=str), encoding="utf-8")
print(f"\nwrote {out}")
