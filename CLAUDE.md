# Project Brief

**Early Detection of Landslide-Induced River Blockages and Barrier Lake Expansion in Himalayan Valleys Using Multi-Modal Sentinel-1/2 Fusion, Terrain-Aware Shadow Rejection and Attention U-Net Segmentation**

This file is the standing context for this repository. Read it fully before doing any work, and re-read the relevant section before starting each phase.

---

## 1. What We Are Building

This is a Python research prototype that, for a user-defined area in the Himalaya (primary study area: Nepal), does the following:

- Detects water using Sentinel-2 optical indices and Sentinel-1 SAR.
- Rejects false water caused by terrain shadow (optical) and radar shadow / layover (SAR). **This is the core scientific contribution.**
- Detects new landslides through before/after (bi-temporal) change.
- Flags potential river blockages: new landslide material intersecting a river channel.
- Detects and tracks barrier lakes upstream of blockages, including their expansion over time.
- Estimates lake depth and volume **only where the data supports it** (see Section 8).
- Produces transparent, configurable risk indicators and warning levels.
- Shows everything in a Streamlit + Folium dashboard, with per-site reports.

This is a research decision-support tool. It **never** predicts when a dam will fail, **never** declares that a dam will form, and **never** presents its outputs as official warnings.

### Scope

**Core (must be delivered):** Phases 0–13 in Section 12.

**Stretch (only after the core is complete and reviewed):**

- Potential future natural-dam formation zones.
- Downstream potential impact zones using HAND (Height Above Nearest Drainage).

Do not start stretch work unless explicitly asked.

---

## 2. Working Agreement

- **Phase gates.** Work on one phase at a time. At the end of each phase: run the tests, show the outputs (maps saved to `outputs/`, numbers, test results), and write a short summary covering what was built, what was verified, known limitations, and open questions. Then **stop and wait for approval** before starting the next phase.
- **Plan first.** Before writing code for a phase, give a short plan: the files to be created, the approach, and any decisions needed.
- **Never fabricate data.** No synthetic satellite imagery passed off as real, no hard-coded measurements, no invented depth values, no made-up event dates or coordinates. Unit tests may use small synthetic arrays, but these must live only in `tests/` and be clearly marked as synthetic.
- **Cite sources for science.** Any threshold, formula, or empirical relationship must have a citation in a code comment and in `docs/methods.md`. If unsure whether a source exists or says what you think, say so rather than guessing.
- **Ask before big decisions.** This includes changing the architecture, adding a heavy dependency, choosing validation events, and implementing empirical depth/volume formulas.
- **Everything configurable.** Thresholds, weights, dates, AOIs and paths go in `config/config.yaml`, validated with Pydantic. No magic numbers in code.
- **Small commits.** Commit in logical steps with clear messages. Never commit credentials, large rasters, or model weights. Respect `.gitignore`.

> Git and GitHub operations are handled by the repository owner. Claude Code does not run git commands in this project.

---

## 3. Development Environment

- **Local machine:** VS Code, Miniconda, Python 3.11, Git/GitHub. All modules, tests, the dashboard and the database run locally.
- **Google Earth Engine:** used for data access and heavy compositing. The GEE Cloud project ID is read from `.env` (`GEE_PROJECT=...`). **Never hard-code it.**
- **Google Colab:** used only for U-Net training (Phase 6). Colab clones this repo and runs `models/train.py`. Training patches and weights live in Google Drive. Provide a thin notebook `notebooks/colab_train.ipynb` that mounts Drive, clones the repo, installs dependencies and calls the training script. **Model logic must never live only in the notebook.**
- Install GDAL and rasterio via **conda-forge**, not pip.
- **No local GPU is assumed.** Local processing must work on small AOIs (on the order of tens of km²), not full Sentinel scenes.

---

## 4. Technology Stack

| Purpose | Tools |
|---|---|
| Data access | `earthengine-api`, `geemap`; `earthaccess` for ICESat-2 ATL13 / SWOT (optional) |
| Raster | `rasterio`, `rioxarray`, `xarray`, `numpy` |
| Vector | `geopandas`, `shapely`, `pyproj` |
| Terrain / hydrology | `whitebox` (WhiteboxTools); `pysheds` acceptable alternative |
| ML | `torch`, `segmentation-models-pytorch` (plain U-Net baseline), custom Attention U-Net, `scikit-learn` |
| Dashboard | `streamlit`, `folium`, `streamlit-folium`, `plotly` |
| Database | SQLite with geometry stored as WKT (or GeoPackage); keep the DB layer swappable |
| Reports | `jinja2` + `weasyprint` (HTML → PDF) |
| Config | `pyyaml` + `pydantic` |
| Testing | `pytest` |

Provide `environment.yml` (conda) and keep it in sync.

---

## 5. Data Sources (via Google Earth Engine unless noted)

Before relying on any collection ID or band name, **verify it against the GEE catalog** and confirm it in the phase plan.

- **Sentinel-2 L2A:** `COPERNICUS/S2_SR_HARMONIZED`. Bands B2, B3, B4, B8, B11, B12, plus SCL. Cloud masking via Cloud Score+ (`GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`) and/or SCL. Solar angles come from the image properties (`MEAN_SOLAR_ZENITH_ANGLE`, `MEAN_SOLAR_AZIMUTH_ANGLE`). **Note: Sentinel-2 data begins in mid-2015.**
- **Sentinel-1 GRD:** `COPERNICUS/S1_GRD`. VV, VH, and the angle band. Keep ascending and descending orbits separate and record orbit metadata.
- **Landsat 8/9 Collection 2 L2:** for history before Sentinel-2 and for long time series.
- **DEM:** Copernicus GLO-30 (`COPERNICUS/DEM/GLO30`). Record that its source data were acquired roughly 2011–2015. **This matters for depth estimation (Section 8).**
- **Rivers:** derive the stream network from the DEM with WhiteboxTools, and optionally cross-check against HydroSHEDS / HydroRIVERS.
- **Water surface elevation (optional):** ICESat-2 ATL13 and SWOT via `earthaccess`.
- **Exposure data (stretch only):** OpenStreetMap (roads, settlements), GHSL or WorldPop.

Every product the system stores must carry: **sensor, acquisition date(s), orbit/tile, processing level, and source collection.**

---

## 6. Study Area and Validation Events

- The AOI is user-defined as a bounding box, polygon (GeoJSON), or point plus buffer. **Never hard-code a single site.**
- Determine the UTM projection **automatically** from the AOI centroid. Nepal spans UTM zones 44N and 45N (EPSG:32644 / EPSG:32645). All areas and volumes are computed in that projected CRS, **never in degrees**.

### Validation events

- **Jure landslide, Sunkoshi River, August 2014.** A well-documented landslide dam in Nepal. It predates Sentinel-2, so it is a test case for the **Landsat + DEM** pipeline path, not for S1/S2 fusion. Check Sentinel-1 coverage for that date before assuming any is available.
- **Existing lakes for water-vs-shadow testing:** glacial lakes in deep valleys (for example Tsho Rolpa, Imja Tsho) give known water bodies surrounded by steep shadowed terrain.
- **Post-2017 landslide-dam events in Nepal:** search for 1–3 documented events with Sentinel-1/2 coverage. For each, give the source (paper or agency report), date and approximate location, and **wait for confirmation**. Do not invent events or coordinates.

---

## 7. Method Requirements by Module

### 7.1 Preprocessing

- Cloud and cloud-shadow masking for Sentinel-2. **Keep cloud shadow separate from terrain shadow.**
- Sentinel-1: convert to dB, apply speckle filtering (configurable, e.g. Refined Lee or a focal median), and keep the incidence angle.
- Co-register all layers to a common 10 m grid in the AOI's UTM CRS.
- DEM derivatives: slope, aspect, hillshade, flow direction, flow accumulation, stream network.
- Terrain shadow mask for **each** Sentinel-2 scene, using the DEM plus that scene's sun zenith/azimuth (e.g. `ee.Terrain.hillShadow`). Also compute a continuous illumination (hillshade) layer.
- SAR layover/shadow mask for **each** Sentinel-1 scene, from the DEM, the incidence angle and the orbit geometry.

### 7.2 Water Detection (rule-based baseline, built before the U-Net)

- Compute NDWI = (Green − NIR) / (Green + NIR) and MNDWI = (Green − SWIR1) / (Green + SWIR1).
- Sentinel-1 water: low VV/VH backscatter, using thresholds chosen by Otsu or another data-driven method. The method must be configurable.
- Output a binary water mask, plus per-water-body polygons with area, perimeter, centroid and boundary.

### 7.3 Shadow Rejection (core contribution)

- Combine the optical indices, the terrain-shadow mask, illumination, SAR backscatter, the SAR layover/shadow mask and multi-temporal persistence.
- Output per-pixel probabilities, for example `p_water`, `p_terrain_shadow`, `p_land`. Use a transparent rule-based or Random Forest fusion as the baseline.
- Logic to encode and document:
  - Dark optical pixel + in terrain shadow + SAR **not** water-like → **shadow**.
  - Dark optical pixel + in terrain shadow + SAR water-like (and not in SAR shadow/layover) → **water**.
  - SAR water-like but inside the SAR shadow/layover mask → **uncertain**; defer to optical evidence.
- Report how many false water pixels were removed, compared with the index-only mask.

### 7.4 Landslide Change Detection (bi-temporal)

- Compare pre- and post-event composites: NDVI drop, brightness/SWIR increase, and Sentinel-1 backscatter change.
- Output a landslide change map and polygons with area.
- **Note:** the U-Net classifies landslide-like surfaces on a single date. The "new" part of "new landslide" must come from this change module, not from the U-Net.

### 7.5 Segmentation Models (Colab training)

- **Classes:** 0 background/land, 1 water, 2 landslide/bare debris, 3 terrain shadow (material indeterminate), 4 snow/ice.
- **Labelling rule** (document it in `docs/labelling.md`): label by **surface material** where it can be determined. Use class 3 only where terrain shadow makes the material indeterminate. A landslide scar or lake inside shadow keeps its material class if it is identifiable.
- **Inputs** (configurable channel stack): S2 B2, B3, B4, B8, B11, B12; NDWI, MNDWI, NDVI; S1 VV, VH; DEM elevation, slope, illumination/hillshade, terrain-shadow mask. Patches of 256×256 at 10 m.
- **Models:**
  - Plain U-Net from `segmentation-models-pytorch` as the baseline.
  - Attention U-Net with attention gates (Oktay et al., 2018), implemented in `models/attention_unet.py`.
  - **The comparison between the two is a required result.**
- **Data:** use existing public datasets where suitable (e.g. Sen1Floods11 for water; Landslide4Sense for landslides). Map their labels to our classes and document the mapping. Add hand-labelled Himalayan patches made in QGIS, especially for shadow and snow.
- **Splits:** geographic/event-based train/validation/test splits. **No random pixel or random patch splits** that leak spatially adjacent data.
- **Metrics:** per-class IoU, Dice, precision, recall, F1, and a confusion matrix. Report the **water-vs-shadow confusion explicitly**. Do not rely on overall accuracy.

### 7.6 River Blockage (Potential Landslide Dam) Detection

- A candidate is created when a new landslide polygon intersects or comes within a configurable distance of the stream network, **and** there is evidence of obstruction: channel narrowing, loss of downstream water continuity, and/or new upstream water.
- Output a dam code (e.g. `ND-001`), type `Potential Landslide Dam`, a confidence score with its contributing factors listed, and the evidence dates.

### 7.7 Barrier Lake Detection and Tracking

- A water body located **upstream** of a blockage candidate, on the same stream, that is new or expanding relative to the pre-event baseline.
- Track each lake through time with stable IDs, and handle merging, splitting and disappearance.

### 7.8 Temporal Change

- Time series of lake area, plus absolute change, percent change and rate of change (e.g. m²/day).
- Classify the trend as Increasing / Decreasing / Stable / Unknown, with configurable thresholds and a minimum number of valid observations.
- Cloudy or missing dates are recorded as **gaps**, never interpolated silently.

---

## 8. Depth and Volume (Strict Rules)

**Never estimate depth from image colour.** Use exactly the following branching logic, and record which branch was used.

**Water surface elevation (WSE):** take the median DEM elevation along the lake shoreline (a buffer just outside the water polygon), and store its spread as uncertainty. Optionally cross-check against ICESat-2 ATL13 or SWOT when tracks or tiles cover the lake.

- **Branch A — the lake formed *after* the DEM was acquired** (after about 2015 for GLO-30): the DEM shows the pre-lake valley floor. For each pixel, `depth = WSE − DEM elevation`, clipped at 0, and `volume = Σ(depth × pixel area)`. Mark the value as **estimated** and propagate uncertainty from the DEM's vertical error and the WSE spread.
- **Branch B — the lake already existed when the DEM was acquired:** the DEM recorded the water surface, so the lake bed is unknown. Return `depth: unavailable` with reason *DEM records water surface; no bathymetry*. An empirical area–volume relationship may be added **only with approval**, with a cited formula. It must be marked **empirical** and reported with wide uncertainty bounds.
- **Branch C — insufficient data** (no reliable shoreline, or a cloudy observation): return `unavailable` with the reason.

**Never output a depth or volume value that cannot be traced to one of these branches.**

---

## 9. Risk Indicators and Warnings

- Use a transparent weighted score built from: lake area growth rate, volume (when available), new landslide activity near the blockage, blockage confidence, and slope. Rainfall is optional.
- All weights and thresholds go in config. **Each warning must list the factors behind it.**
- Levels: 🟢 NORMAL · 🟡 MONITOR · 🟠 HIGH RISK INDICATORS · 🔴 CRITICAL INDICATORS — verification recommended.
- Every warning and report carries this text:

  > Research prototype output. Not an official warning. Verify with authoritative sources.

---

## 10. Data Integrity and Database

Every stored value has a `value_type` drawn from: `observed`, `classified` (model output), `estimated`, `empirical`, `derived`, `unavailable`.

Minimum tables:

- **sites:** id, site_code, site_type, geometry (WKT), lat, lon, elevation, first_detected, last_updated, confidence, status
- **observations:** id, site_id, obs_date, sensor, orbit_or_tile, cloud_fraction, water_area_m2, water_perimeter_m, value_type, method, source_collection
- **depth_volume_estimates:** id, site_id, obs_date, branch (A/B/C), wse_m, wse_uncertainty_m, mean_depth_m, max_depth_m, volume_m3, volume_low_m3, volume_high_m3, value_type, method, notes
- **landslide_events:** id, site_id, pre_date, post_date, area_m2, geometry, confidence, method
- **risk_assessments:** id, site_id, assessed_at, factors_json, score, level, config_version
- **runs:** id, started_at, config_hash, code_version (git commit), aoi, status, log_path

---

## 11. Folder Structure

```text
himalayan_dam_monitoring/
├── CLAUDE.md
├── README.md
├── environment.yml
├── .env.example
├── config/
│   ├── config.yaml
│   └── schema.py            # Pydantic config models
├── acquisition/
│   ├── gee_client.py        # auth, AOI handling, exports
│   ├── sentinel1.py
│   ├── sentinel2.py
│   ├── landsat.py
│   ├── dem.py
│   └── altimetry.py         # optional ICESat-2 / SWOT
├── preprocessing/
│   ├── cloud_mask.py
│   ├── sar.py               # dB, speckle, layover/shadow mask
│   ├── terrain.py           # slope, aspect, hillshade, terrain shadow
│   ├── hydrology.py         # flow, streams (WhiteboxTools)
│   └── stack.py             # co-registration, channel stacking
├── detection/
│   ├── water.py
│   ├── shadow_rejection.py
│   ├── landslide_change.py
│   ├── blockage.py
│   └── barrier_lake.py
├── models/
│   ├── dataset.py
│   ├── unet.py
│   ├── attention_unet.py
│   ├── train.py
│   ├── evaluate.py
│   └── predict.py
├── analysis/
│   ├── change.py
│   ├── depth_volume.py
│   ├── risk.py
│   └── stretch/             # future_potential.py, downstream_hand.py (stretch only)
├── database/
│   └── db.py
├── reports/
│   ├── generate.py
│   └── templates/
├── app/
│   ├── dashboard.py
│   ├── maps.py
│   └── charts.py
├── utils/
│   ├── crs.py
│   ├── io.py
│   └── logging.py
├── notebooks/
│   ├── 01_explore_aoi.ipynb
│   └── colab_train.ipynb
├── docs/
│   ├── methods.md
│   ├── labelling.md
│   └── validation.md
├── data/                    # gitignored: raw/, processed/, training/, validation/
├── outputs/                 # gitignored: maps, figures, reports
└── tests/
```

---

## 12. Development Phases

| Phase | Deliverable | Gate check |
|---|---|---|
| 0 | Repo, environment, config + schema, logging, GEE auth, pytest skeleton | `pytest` passes; GEE test query returns metadata for a test AOI |
| 1 | Acquisition: S1, S2, Landsat and DEM for an AOI and date range, with metadata | Exported GeoTIFFs open in QGIS; metadata recorded |
| 2 | Preprocessing: cloud mask, SAR processing, terrain/SAR shadow masks, co-registered stack | Shadow masks visually match the hillshade for known dates |
| 3 | Rule-based water detection (optical + SAR) | Known glacial lakes detected; areas plausible |
| 4 | Shadow rejection fusion with probabilities | False-water reduction quantified on shadowed valleys |
| 5 | Bi-temporal landslide change detection | Change map produced for a documented event |
| 6 | Dataset building, U-Net + Attention U-Net training (Colab), evaluation | Per-class metrics plus water-vs-shadow confusion reported for both models |
| 7 | River blockage candidate detection | Candidate found at a confirmed validation event |
| 8 | Barrier lake detection and tracking | Lake upstream of the candidate identified and tracked |
| 9 | Temporal change analysis | Time series with gaps handled honestly |
| 10 | Depth/volume per Section 8 | Branch logic tested; no untraceable values |
| 11 | Risk indicators and warnings | Factors listed per warning; disclaimer present |
| 12 | Streamlit dashboard (map, site table, timeline, before/after, warnings) | Runs locally with `streamlit run app/dashboard.py` |
| 13 | Report generation + end-to-end validation write-up in `docs/validation.md` | PDF report for one site; validation results documented |

---

## 13. Required Tests (in addition to unit tests)

1. Normal mountain terrain → no water, no candidate.
2. Deep shadowed valley with no lake → classified as shadow, not water.
3. Known existing lake in a shadowed valley → water detected.
4. Landslide near a river → landslide detected, **no** blockage unless obstruction evidence exists.
5. Landslide crossing a river with obstruction evidence → potential landslide dam.
6. Water accumulating upstream of the blockage → potential barrier lake.
7. Expanding lake → trend Increasing, higher monitoring concern.
8. Lake present in the DEM epoch → depth **unavailable** (Branch B), never a number.
9. Cloudy-only date range → graceful "no valid observation", no crash.

Tests 1–7 use **real imagery** from documented locations where possible. Synthetic arrays are allowed only for unit-level logic and must be labelled as such.

---

## 14. Final System Questions the Dashboard Must Answer per Site

- Is there water here (Yes / No / Uncertain)?
- Water vs shadow probability
- Evidence of a new landslide?
- Is a river potentially blocked?
- Is there a barrier lake?
- Area, estimated depth/volume, or "unavailable" with the reason
- Trend: Increasing / Decreasing / Stable / Unknown
- Current indicator level and contributing factors
- Data sources and observation dates
- Which values are observed, classified, estimated or unavailable
