"""Acquire Sentinel-2, Sentinel-1 and the DEM for the Baige AOI from GEE.

Supports: validation.md 20 (Event and data)

Installed from the session that produced the result. Run from anywhere:

    python scripts/baige/01_fetch.py

Paths derive from this file's location, so a clone works without editing.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from acquisition import dem as dem_mod  # noqa: E402
from acquisition import sentinel1, sentinel2  # noqa: E402
from acquisition.gee_client import aoi_area_km2, aoi_to_ee_geometry, initialize  # noqa: E402
from config.loader import load_config_with_overlay  # noqa: E402

STAGE = (sys.argv[1] if len(sys.argv) > 1 else "s2").lower()
OUT = ROOT / "data" / "raw" / "baige_2018"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = ROOT / "outputs" / "baige_2018_acquisition.json"

cfg = load_config_with_overlay("baige_2018")
t0 = time.time()
initialize(cfg)
print(f"EE init {time.time() - t0:.0f}s | stage={STAGE}", flush=True)

area = aoi_area_km2(aoi_to_ee_geometry(cfg.aoi))
pixels = int(area * 1e6 / (cfg.gee.default_scale_m ** 2))
print(
    f"AOI {area:.1f} km² = {pixels:,} px "
    f"(guard {cfg.gee.max_request_pixels:,}); "
    f"6-band ≈ {pixels * 6 * 4 / 1e6:.1f} MB "
    f"(guard {cfg.acquisition.max_export_bytes / 1e6:.1f} MB)",
    flush=True,
)

report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
report.setdefault("aoi", cfg.aoi.name)
report.setdefault("area_km2", round(area, 1))
report.setdefault("exports", [])


def record(entry: dict) -> None:
    report["exports"] = [
        e for e in report["exports"]
        if not (e.get("sensor") == entry.get("sensor") and e.get("date") == entry.get("date"))
    ] + [entry]
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")


def fetch(module, scene, label: str) -> None:
    t = time.time()
    try:
        products = module.export_scene(cfg, scene, out_dir=OUT)
        names = [Path(raster).name for raster, _ in products]
        print(f"  {label}: {names} in {time.time() - t:.0f}s", flush=True)
        record({"sensor": label.split()[0], "date": str(scene.acquisition_start.date()),
                "files": [str(n) for n in names]})
    except Exception as exc:
        print(f"  {label}: FAILED {type(exc).__name__}: {str(exc)[:220]}", flush=True)
        record({"sensor": label.split()[0], "date": str(scene.acquisition_start.date()),
                "error": f"{type(exc).__name__}: {str(exc)[:220]}"})


if STAGE == "s2":
    scenes = sentinel2.list_scenes(cfg, start=date(2018, 11, 1), end=date(2018, 11, 12))
    print(f"S2 candidates: {len(scenes)}", flush=True)
    for want in (date(2018, 11, 2), date(2018, 11, 9)):
        matches = [s for s in scenes if s.acquisition_start.date() == want]
        if not matches:
            print(f"  {want}: NOT FOUND", flush=True)
            continue
        best = min(matches, key=lambda s: s.cloud_fraction if s.cloud_fraction is not None else 100)
        print(f"  {want} cloud {best.cloud_fraction:.2f}% ...", flush=True)
        fetch(sentinel2, best, f"S2 {want}")

elif STAGE == "s1":
    scenes = sentinel1.list_scenes(cfg, start=date(2018, 10, 20), end=date(2018, 11, 12))
    by_orbit: dict = {}
    for scene in scenes:
        by_orbit.setdefault(scene.relative_orbit, []).append(scene)

    chosen = None
    for orbit, group in sorted(by_orbit.items()):
        group.sort(key=lambda s: s.acquisition_start)
        pre = [s for s in group if s.acquisition_start.date() < date(2018, 11, 3)]
        post = [s for s in group if s.acquisition_start.date() > date(2018, 11, 3)]
        print(
            f"  orbit {orbit} ({group[0].orbit_pass}): "
            f"{', '.join(str(s.acquisition_start.date()) for s in group)}",
            flush=True,
        )
        if pre and post and chosen is None:
            chosen = (orbit, pre[-1], post[0])

    if chosen is None:
        print("  NO same-orbit pair brackets the second dam", flush=True)
    else:
        orbit, pre_scene, post_scene = chosen
        print(
            f"  -> orbit {orbit} {pre_scene.orbit_pass}: "
            f"{pre_scene.acquisition_start.date()} -> {post_scene.acquisition_start.date()}",
            flush=True,
        )
        report["s1_pair"] = {
            "relative_orbit": orbit,
            "orbit_pass": pre_scene.orbit_pass,
            "pre": str(pre_scene.acquisition_start.date()),
            "post": str(post_scene.acquisition_start.date()),
            "note": "same relative orbit: differencing across orbits would "
                    "measure viewing geometry, not surface change",
        }
        for scene in (pre_scene, post_scene):
            fetch(sentinel1, scene, f"S1 {scene.acquisition_start.date()}")

elif STAGE == "dem":
    t = time.time()
    try:
        products, epoch = dem_mod.export_dem(cfg, out_dir=OUT)
        names = [Path(raster).name for raster, _ in products]
        print(f"  DEM {names} in {time.time() - t:.0f}s", flush=True)
        print(f"  epoch: {epoch}", flush=True)
        report["dem"] = {"files": [str(n) for n in names], "epoch": str(epoch)}
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"  DEM FAILED {type(exc).__name__}: {str(exc)[:250]}", flush=True)
        report["dem"] = f"{type(exc).__name__}: {str(exc)[:250]}"
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
else:
    print(f"unknown stage {STAGE!r}; use s2 | s1 | dem", flush=True)

print("\nfiles on disk:", flush=True)
for path in sorted(OUT.glob("*")):
    print(f"  {path.stat().st_size / 1e6:8.2f} MB  {path.name}", flush=True)
