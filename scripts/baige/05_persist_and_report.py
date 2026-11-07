"""Store the results with their value_types and generate the site PDF.

Supports: validation.md 19 (B)

Installed from the session that produced the result. Run from anywhere:

    python scripts/baige/05_persist_and_report.py

Paths derive from this file's location, so a clone works without editing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from config.loader import config_hash, load_config_with_overlay  # noqa: E402
from database.db import Database, code_version  # noqa: E402
from reports.generate import site_report_from_database  # noqa: E402

cfg = load_config_with_overlay("baige_2018", load_env=False)
fused = json.load(
    open(ROOT / "outputs" / "baige_2018_rederived_on_fused_water.json",
         encoding="utf-8")
)


def geometries():
    """Lake outlines per date, the deposit, and the blockage point, as WKT.

    Re-derived from the fused inputs rather than read from a sidecar, so the
    shapes the dashboard draws are the same objects the numbers came from. In
    EPSG:4326, because the map is.
    """
    import numpy as np
    import rasterio
    import rasterio.features
    from pyproj import Transformer
    from shapely.geometry import shape as to_shape
    from shapely.ops import transform as reproject, unary_union

    from detection.barrier_lake import find_barrier_lakes
    from detection.blockage import detect_blockages
    from utils.crs import pixel_area_m2

    processed = ROOT / "data" / "processed"
    hydro = processed / "baige_hydro"
    fused_arrays = np.load(processed / "baige_fused.npz")
    with rasterio.open(hydro / "baige_streams.tif") as src:
        streams = src.read(1) > 0
    with rasterio.open(hydro / "baige_d8_accumulation.tif") as src:
        accumulation = src.read(1, masked=True).filled(0.0)
    with rasterio.open(
        ROOT / "data/raw/baige_2018/DEM_GLO30_v02_EPSG32647.tif"
    ) as src:
        transform_, crs_ = src.transform, src.crs

    cell = float(abs(transform_.a))
    area_px = pixel_area_m2(transform_, crs_)
    to_wgs84 = Transformer.from_crs(crs_, "EPSG:4326", always_xy=True).transform

    def wkt_of(mask):
        """One WKT geometry for a boolean mask, in EPSG:4326."""
        mask = np.asarray(mask, dtype=bool)
        if not mask.any():
            return None
        shapes = [
            to_shape(geom)
            for geom, value in rasterio.features.shapes(
                mask.astype("uint8"), mask=mask, transform=transform_
            )
            if value == 1
        ]
        if not shapes:
            return None
        return reproject(to_wgs84, unary_union(shapes)).wkt

    candidates = detect_blockages(
        cfg,
        landslides=fused_arrays["change"].astype(bool),
        streams=streams, cellsize_m=cell, pixel_area_m2=area_px,
        flow_accumulation=accumulation,
        water_pre=fused_arrays["water_pre"], water_post=fused_arrays["water_post"],
        transform=transform_, crs=crs_,
        pre_date="2018-11-02", post_date="2018-11-09",
    )
    dam_code = fused["phase7"]["lake_bearing"]
    candidate = next(
        (c for c in candidates if c.dam_code == dam_code), candidates[0]
    )

    lakes = find_barrier_lakes(
        cfg, blockage_site=candidate.site_mask, streams=streams,
        water_post=fused_arrays["water_post"], water_pre=fused_arrays["water_pre"],
        cellsize_m=cell, pixel_area_m2=area_px,
        flow_accumulation=accumulation, dam_code=dam_code,
    )
    biggest = max(lakes, key=lambda x: x.area_m2) if lakes else None

    return {
        "lake": None if biggest is None else wkt_of(biggest.mask),
        "landslide": wkt_of(candidate.landslide_mask),
        "blockage": wkt_of(candidate.site_mask),
        "search_distance_m": cfg.detection.barrier_lake.upstream_search_m,
    }


shapes = geometries()
print("geometry derived:")
for key in ("lake", "landslide", "blockage"):
    value = shapes[key]
    print(f"  {key:10s} {'none' if value is None else value[:46] + '...'}")
print(f"  search distance {shapes['search_distance_m']:.0f} m")
p7 = json.load(open(ROOT / "outputs" / "baige_2018_phase7.json", encoding="utf-8"))

DB = ROOT / "outputs" / "baige_2018.sqlite"
if DB.exists():
    DB.unlink()

SENSOR = "Sentinel-2 MSI"
COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
METHOD_WATER = (
    "Phase 4 shadow-rejection fusion over Phase 3 optical water; snow screened "
    "as an invalid observation; kept only where optical data exists"
)

with Database(DB) as db:
    db.initialise()
    run = db.start_run(
        config_hash=config_hash(cfg),
        aoi=cfg.aoi.name,
        log_path=None,
    )
    print(f"run {run.id} started; code {code_version() or 'unknown'}")

    dam = fused["phase7"]["lake_bearing"]
    conf = fused["phase7"]["confidence"]
    ranked = fused["phase7"]["ranked_by_gained_upstream"]
    top = next((r for r in ranked if r["dam_code"] == dam), ranked[0])
    nd_area = top["landslide_area_m2"]
    slope_deg = next(
        (f["value"] for f in fused["phase11"]["factors"] if f["name"] == "slope"),
        None,
    )

    # The blockage candidate. Its lon/lat come from the Phase 7 run; the
    # published coordinate is NOT used, because it is the landslide source
    # area on the valley side, not the blockage (validation 20, C.0).
    nd = next(
        (c for c in p7["candidates"] if c["dam_code"] == dam),
        p7["candidates"][0],
    )
    site_id = db.upsert_site(
        site_code=dam,
        site_type=cfg.detection.blockage.site_type,
        geometry=shapes["blockage"],
        lat=nd["centroid_lat"],
        lon=nd["centroid_lon"],
        first_detected="2018-11-09",
        confidence=conf,
        status="observed",
    )
    print(f"site {dam} -> id {site_id}")

    # The landslide that produced it.
    db.add_landslide_event(
        site_id=site_id,
        pre_date="2018-11-02",
        post_date="2018-11-09",
        area_m2=nd_area,
        geometry=shapes["landslide"],
        confidence=conf,
        method=(
            "Phase 5 bi-temporal change (NDVI drop, brightness increase, SAR "
            "change; 2 of 3 required), dam-tuned slope gate, post-date water "
            "excluded; components merged along the reach"
        ),
        value_type="classified",
        run_id=run.id,
    )

    # The lake series. Cloud fraction is the share of the floodable zone that
    # could NOT be seen, so a reader can tell a small lake from a hidden one.
    for entry in fused["phase8_9"]["series"]:
        if entry["status"] == "pre-event":
            continue
        is_gap = entry["status"].startswith("GAP")
        db.add_observation(
            site_id,
            obs_date=entry["date"],
            sensor=SENSOR,
            orbit_or_tile="47RMQ",
            cloud_fraction=round(1.0 - entry["zone_observable"], 4),
            water_area_m2=None if is_gap else entry["lake_area_m2"],
            water_perimeter_m=None,
            # The outline is stored only for the date it was derived from.
            # Attaching one date's shape to another would misreport where the
            # water was.
            geometry=(
                shapes["lake"]
                if (not is_gap and entry["date"] == "2018-11-09")
                else None
            ),
            # Without this the area is uninterpretable: the same lake measured
            # over 500 m and 3,000 m of channel differs threefold (section 22).
            search_distance_m=shapes["search_distance_m"],
            value_type="unavailable" if is_gap else "classified",
            method=METHOD_WATER if not is_gap else entry["status"],
            source_collection=COLLECTION,
            run_id=run.id,
        )
    print(f"observations: {len(db.observations(site_id))}")

    # Depth and volume: Branch C, deliberately. The DEM postdates nothing
    # here -- the lake is 64% pre-existing river, so 64% of it is Branch B --
    # and the shoreline WSE has a +/-24.61 m spread on a surface that must be
    # level (validation 24). No number is emitted.
    db.add_depth_volume(
        {
            "site_id": site_id,
            "obs_date": "2018-11-09",
            "branch": "C",
            "wse_m": None,
            "wse_uncertainty_m": None,
            "mean_depth_m": None,
            "max_depth_m": None,
            "volume_m3": None,
            "volume_low_m3": None,
            "volume_high_m3": None,
            "value_type": "unavailable",
            "method": "Section 8 branch logic",
            "notes": (
                "Withheld. The lake is 64% pre-existing Jinsha channel, which "
                "the DEM recorded as a water surface (Branch B), and the "
                "shoreline water-surface elevation has a +/-24.61 m spread on "
                "a surface that must be level, because a single WSE does not "
                "describe a long impoundment in a steep valley. See "
                "docs/validation.md 24."
            ),
        },
        run_id=run.id,
    )

    # Recomputed here rather than copied from the run's JSON. A stored
    # assessment must carry whatever the current assessor reports -- copying a
    # previous run's factor list silently drops any field added since, which
    # is how the scale-ceiling flag went missing from the first report.
    from analysis.risk import assess_risk

    trend = fused["phase8_9"]["trend"]
    assessment = assess_risk(
        cfg,
        lake_growth_rate_m2_per_day=trend["rate_m2_per_day"],
        lake_volume_m3=None,
        volume_unavailable_reason=(
            "withheld for this site: see docs/validation.md 24"
        ),
        new_landslide_area_m2=nd_area,
        blockage_confidence=conf,
        slope_deg=slope_deg,
        rainfall_mm_24h=None,
        config_hash=config_hash(cfg),
    )
    db.add_risk_assessment(assessment.as_record(site_id), run_id=run.id)
    pinned = [f.name for f in assessment.factors if f.saturated]
    print(f"saturated factor(s): {pinned or 'none'}")
    db.finish_run(run.id)

    print(f"\nstored: {db.counts()}")
    latest = db.latest_risk_assessment(site_id)
    print(f"level: {latest['level']} (score {latest['score']:.4f})")

    # --- the report ------------------------------------------------------- #
    out_dir = ROOT / "outputs" / "reports"
    result = site_report_from_database(db, dam, cfg, out_dir=out_dir)
    print(f"\nreport engine: {result.pdf_engine}")
    print(f"  HTML: {result.html_path}")
    print(f"  PDF : {result.pdf_path}")
    if result.pdf_path and Path(result.pdf_path).is_file():
        print(f"  PDF size: {Path(result.pdf_path).stat().st_size:,} bytes")
    for note in ([result.pdf_error] if result.pdf_error else []):
        print(f"  note: {note}")

    html = Path(result.html_path).read_text(encoding="utf-8")
    print(f"\nchecks on the rendered report:")
    print(f"  disclaimer present      : {cfg.project.disclaimer in html}")
    print(f"  level present           : {latest['level'] in html}")
    print(f"  depth reported as absent: "
          f"{'unavailable' in html.lower() or 'not available' in html.lower()}")
    print(f"  a factor is listed      : "
          f"{'blockage_confidence' in html or 'Blockage confidence' in html}")
