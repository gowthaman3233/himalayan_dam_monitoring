# Methods and Citation Register

Every threshold, formula and empirical relationship used anywhere in this
repository is recorded here with its source, as required by the project brief
(Section 2). A value with no entry in this file is a bug.

Conventions used below:

| Marker | Meaning |
|---|---|
| **cited** | Taken from the literature; the source is given and has been checked. |
| **convention** | An engineering default with no scientific claim attached (e.g. a file layout, a query window chosen for low cloud). Needs no citation, but must be labelled so it is never mistaken for a published value. |
| **pending** | Will be introduced at a later phase. Listed so the gap is visible. |

---

## Phase 0 — Repository, configuration, logging, Earth Engine access

### 0.1 Default area of interest — Tsho Rolpa

**cited.** `config/config.yaml`, `aoi` block.

Position: **27° 52′ N, 86° 28′ E** (= 27.867° N, 86.467° E), Rolwaling Valley,
Dolakha District, Nepal.

| Quantity | Value | Source |
|---|---|---|
| Position, elevation | 27° 52′ N, 86° 28′ E; 4546 m a.s.l. | Kayastha, R. B. and Maskey, S. (2024). "Glacial lake outburst flood (GLOF) modeling of Tsho Rolpa glacial lake, Nepal". *Proceedings of IAHS* **387**, 59–63. <https://doi.org/10.5194/piahs-387-59-2024> |
| Position, surface area 1.537 km², max length 3.45 km, max width 0.5 km, elevation 4580 m | 27.867° N, 86.467° E | Shrestha, B. B. and Nakagawa, H. (2014). "Assessment of potential outburst floods from the Tsho Rolpa glacial lake in Nepal". *Natural Hazards* **71**(2). |
| Lake growth: 0.23 km² (1959) → ~1.65 km² (2021) | — | Kayastha and Maskey (2024), as above. |

Two independent peer-reviewed sources agree on the position. Note the
**arcminute precision** (≈ ±1 km) of the published coordinates: the AOI is
therefore encoded as a *point plus buffer*, not a bounding box, so that no box
corner is stated to a precision the sources do not support.

Buffer radius **4000 m** — **convention.** A circle of ≈50 km², chosen to
contain the 3.45 km × 0.5 km lake (which needs a radius of at least ≈1.8 km) plus
roughly 2 km of flanking valley wall, the steep terrain that produces the shadow
this prototype must reject. It stays inside the "tens of km²" local-processing
budget of the brief, Section 3. No scientific claim is attached to this number.

Relevant to Section 8 (depth and volume): Tsho Rolpa **predates** the Copernicus
GLO-30 DEM epoch (source data ≈ 2011–2015), so it is a **Branch B** lake — the
DEM recorded its water surface, not its bed. Depth and volume for this site must
be reported as `unavailable`. It is a water-vs-shadow test case, not a
depth-estimation test case.

### 0.2 UTM zone selection

**convention** (standard definition, not a research choice). `utils/crs.py`.

UTM zone *n* spans longitudes `[-180 + 6(n − 1), -180 + 6n)`. EPSG codes are
`32600 + n` for the northern hemisphere and `32700 + n` for the southern. The
zone is always derived from the AOI centroid; it is never assumed.

Nepal spans zones 44 N (78–84° E) and 45 N (84–90° E), i.e. **EPSG:32644** and
**EPSG:32645** (brief, Section 6). Tsho Rolpa at 86.467° E falls in **32645**.

Deliberate simplification, documented so it is not mistaken for an oversight:
the Norway and Svalbard grid irregularities (MGRS zones 31V/32V and 31X–37X)
widen some *grid* zones but do not change which EPSG UTM code to reproject into,
so they are not special-cased. UTM is applied only between 80° S and 84° N;
outside that range `utm_epsg_from_lonlat` raises rather than returning a
meaningless code.

### 0.3 Default query window

**convention.** `config/config.yaml`, `dates.query_window`: 2023-10-01 to
2023-11-30.

A post-monsoon window, chosen only because cloud cover over Nepal is lowest in
those months. This is a convenience default for exploratory queries, carries no
scientific claim, and is overridden per run. Phase-specific pre-/post-event date
pairs are passed as arguments, not read from here.

### 0.4 Earth Engine collections

**Verified against the live catalog on 2026-10-03** by
`tests/test_gee_smoke.py`, over the default Tsho Rolpa AOI (49.665 km²) and the
default query window (2023-10-01 → 2023-11-30). Full record:
`outputs/gee_catalog_probe.json`.

| Key | Collection ID | Status | Images over AOI | Notes |
|---|---|---|---|---|
| `s2_sr` | `COPERNICUS/S2_SR_HARMONIZED` | ✅ verified | 12 | All required bands present (B2, B3, B4, B8, B11, B12, SCL). MGRS tile `45RVL`. Solar angles present. |
| `s2_cloud_score_plus` | `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` | ✅ verified | 12 | Bands `cs`, `cs_cdf`. Matches S2 image count 1:1. |
| `s1_grd` | `COPERNICUS/S1_GRD` | ✅ verified | 15 | Bands VV, VH, angle. **Both** ASCENDING and DESCENDING; relative orbits 12, 85, 121; IW mode. |
| `landsat8_l2` | `LANDSAT/LC08/C02/T1_L2` | ✅ verified | 4 | `SR_B1`–`SR_B7`, `QA_PIXEL`, `QA_RADSAT`, thermal `ST_*`. |
| `landsat9_l2` | `LANDSAT/LC09/C02/T1_L2` | ✅ verified | 3 | Same band structure as Landsat 8. |
| `dem_glo30` | `COPERNICUS/DEM/GLO30` | ⚠️ **DEPRECATED** | 1 | Resolves, but Earth Engine warns it is superseded by `COPERNICUS/DEM/GLO30_2024_1`. See §0.6. |

Measured sun geometry for the first S2 scene in the window (2023-10-04), which
the Phase 2 terrain-shadow mask will consume:

| Property | Value |
|---|---|
| `MEAN_SOLAR_ZENITH_ANGLE` | 35.077° |
| `MEAN_SOLAR_AZIMUTH_ANGLE` | 152.565° |

Known temporal constraints to respect downstream (brief, Section 5):

- **Sentinel-2** begins mid-2015, so it cannot be used for the August 2014 Jure
  event. That event is a Landsat + DEM test case.
- **Copernicus GLO-30** source data were acquired ≈ 2011–2015. This date is the
  hinge of the Branch A / Branch B decision in Section 8 and must be carried
  through to every depth estimate. Now **measured** rather than assumed — see
  §0.6.

### 0.6 Copernicus DEM: deprecation and the Branch A/B hinge date

**Finding, 2026-10-03.** `COPERNICUS/DEM/GLO30` is deprecated in Earth Engine
and superseded by `COPERNICUS/DEM/GLO30_2024_1`
(<https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30_2024_1>).
Both carry the same bands: `DEM`, `EDM`, `FLM`, `HEM`, `WBM`.

This matters for Section 8 more than a routine deprecation would, because the
**DEM acquisition date is the hinge of the Branch A / Branch B decision**.

| | `GLO30` (deprecated) | `GLO30_2024_1` |
|---|---|---|
| Catalog availability | 2010-12-01 → 2015-01 | 2010-12-01 → 2020-11-13 |
| Per-image dates over the AOI | **Placeholder only** — a single entry with `system:time_start` = 2006-01-01, which is not an acquisition date | **Real per-tile acquisition windows** |
| Extra metadata | none | `tile_version` |

Measured over the Tsho Rolpa AOI from `GLO30_2024_1`:

| Quantity | Value |
|---|---|
| Distinct acquisition start dates | 2011-01-05, 2013-05-22, 2013-05-23, 2014-05-19 |
| Distinct acquisition end dates | 2014-05-22, 2014-05-23, 2014-05-24, 2014-09-08 |
| **Overall epoch for this AOI** | **2011-01-05 → 2014-09-08** |
| `tile_version` values present | `01`, `02` |

Two consequences:

1. The brief's estimate of "roughly 2011–2015" is **confirmed** for this AOI, and
   the effective hinge date here is **2014-09-08**, not a global "about 2015".
2. The deprecated collection **cannot** support this check at all: its dates are
   placeholders, so a Branch A/B decision taken against it would rest on an
   assumed constant rather than a queried value. `GLO30_2024_1` makes the hinge
   date a **per-AOI measured quantity**, which is what Section 8's requirement
   that every estimate be traceable actually demands.

**Caveat for Phase 1.** 361 `GLO30_2024_1` entries intersect this 49.665 km²
AOI, and each tile footprint is ≈10,980 km² (1°×1°). The entries therefore
overlap heavily rather than tiling the AOI, and two `tile_version` values are
present. Any DEM mosaic must apply explicit, documented de-duplication and
version-selection logic; naively mosaicking the filtered collection would blend
tile versions. This is deferred to Phase 1 and must not be done implicitly.

**Status: awaiting a decision** on whether to switch `dem_glo30` to
`COPERNICUS/DEM/GLO30_2024_1`. Changing a data source is a decision for the
repository owner (brief, Section 2), so `config.yaml` is unchanged for now and
still points at the deprecated collection.

### 0.5 Mandatory disclaimer

**brief requirement**, Section 9. Stored once in `config.yaml`
(`project.disclaimer`) and re-used by every warning and report so the wording
cannot drift between the dashboard and the PDF output:

> Research prototype output. Not an official warning. Verify with authoritative
> sources.

`config/schema.py` refuses to load a configuration whose disclaimer no longer
contains the phrase *"Not an official warning"*, and `tests/test_config.py`
asserts the full text.

---

## Phase 1 — Acquisition

### 1.1 Per-scene export, not composites

**convention**, with a stated reason. Scenes are exported individually rather
than composited at acquisition time, because:

1. compositing before cloud masking would blend cloud into the result, and cloud
   masking is Phase 2;
2. the per-scene sun geometry (`MEAN_SOLAR_ZENITH_ANGLE`,
   `MEAN_SOLAR_AZIMUTH_ANGLE`) is required to build a terrain-shadow mask **per
   scene** (brief, Section 7.1), and a composite discards it;
3. Sentinel-1 ascending and descending passes must stay separate (brief, Section
   5), which a composite would destroy.

Reflectance and QA bands are written to **separate** GeoTIFFs: Sentinel-2 SCL is
8-bit class codes and reflectance is 16-bit scaled integers, so a single file
would force a lossy common dtype. Landsat `QA_PIXEL` is bit-packed and is
separated for the same reason.

### 1.2 Export extent

**Measured.** `getDownloadURL` returns the **bounding box** of the requested
region. For the default point+buffer AOI, the circular 49.665 km² buffer is
therefore delivered as its circumscribing 7970 × 7990 m box — **63.68 km²**,
797 × 799 pixels at 10 m. This is not a defect, but area statistics computed
over a whole exported raster refer to the box, not the AOI, and must say so.

### 1.3 Scene-level cloud screening

**convention**, `acquisition.max_cloud_fraction` (default 40%).

This selects which scenes are worth downloading and is **not** the per-pixel
cloud mask, which is Phase 2. Both are needed and they are different things.

Rejected scenes are counted and logged, never silently dropped, so a cloudy
window reports as a cloudy window rather than as absent coverage (brief, Section
7.8: gaps are recorded as gaps). A scene with **no** reported cloud fraction is
kept, because a missing value is not evidence of clear sky.

The 40% default is an engineering choice, not a published threshold. Measured
over the default AOI for 2023-10-01 → 2023-11-30, Sentinel-2 cloud ranges from
0.84% to 99.88%, so a threshold in this region cleanly separates usable from
unusable scenes:

| Sensor | Scenes found | Kept at 40% | Cloud range |
|---|---|---|---|
| Sentinel-2 | 12 | 8 | 0.84% – 99.88% |
| Landsat 8/9 | 7 | 7 | 4.02% – 28.74% |
| Sentinel-1 | 15 | 15 (n/a) | SAR is unaffected by cloud |

### 1.4 Units and scaling, recorded but not applied

Raw values are exported unchanged so the stored product stays auditable;
conversions happen in preprocessing. The factors are written into each sidecar.

| Product | Stored as | Conversion | Status |
|---|---|---|---|
| Sentinel-2 L2A | 16-bit scaled integer | reflectance = DN × 1e-4 | recorded, not applied |
| Landsat C2 L2 | 16-bit scaled integer | reflectance = DN × 2.75e-5 − 0.2 | recorded, not applied |
| Sentinel-1 GRD | float, **already decibels** | none needed | see below |
| GLO-30 DEM | float, metres | EGM2008 orthometric height | — |

**Finding on Sentinel-1 units.** The brief (Section 7.1) asks for a conversion
to dB. `COPERNICUS/S1_GRD` already serves VV/VH **in decibels** — it is
`COPERNICUS/S1_GRD_FLOAT` that carries linear power. Confirmed empirically from
the exported rasters: VV spans −49.1 to +13.8 dB and VH −52.6 to +7.3 dB, ranges
that are only meaningful on a log scale. **No dB conversion is therefore
required in Phase 2**, and applying one would corrupt the data. Recorded in each
Sentinel-1 sidecar.

### 1.5 DEM tile de-duplication

**convention**, `acquisition.dem.tile_version_policy` (default `highest`).

`COPERNICUS/DEM/GLO30_2024_1` returns **361 entries** intersecting the default
49.665 km² AOI, each a 1° tile of ≈10,980 km², carrying `tile_version` `01` and
`02`. They overlap almost entirely rather than tiling the AOI, so mosaicking the
filtered collection directly would blend versions non-deterministically.

The implemented policy selects a single `tile_version` first (**361 → 9
entries** for the default AOI), then mosaics those sorted by acquisition time so
that later data wins on any remaining overlap. The selection is recorded in the
product sidecar and in `dem_epoch.json`.

### 1.6 Measured DEM epoch for the default AOI

Produced by `acquisition.dem.acquisition_epoch`, written to
`data/raw/dem/dem_epoch.json`:

| Quantity | Value |
|---|---|
| Earliest acquisition | 2011-01-05T12:17:01Z |
| Latest acquisition | 2014-09-08T12:19:52Z |
| Distinct start dates | 2011-01-05, 2014-05-19 |
| Distinct end dates | 2014-05-24, 2014-09-08 |
| **Branch A/B hinge date** | **2014-09-08** |

The hinge is deliberately the **latest** acquisition, not the earliest or a
mean. If any part of the DEM footprint could already have seen the lake, the DEM
may record its water surface, and claiming Branch A would risk fabricating a
depth. Ambiguity therefore resolves towards `unavailable`, per the brief,
Section 8.

### 1.7 Georeferencing validation

Three independent estimates of the Tsho Rolpa water surface agree, which
validates the AOI coordinates, the derived UTM zone, the pixel size and the
georeferencing together:

| Source | Lake area | Nature |
|---|---|---|
| Shrestha & Nakagawa (2014) | 1.537 km² | published measurement |
| Copernicus DEM `WBM` band | 1.550 km² | provider's water-body mask, DEM epoch |
| Sentinel-2 `SCL` class 6 | 1.502 km² | provider's scene classifier, 2023-10-24 |

Spread **≈3%**. This is a *georeferencing* check, not a water-detection result:
both masks are the data providers' own classifiers, and this project's water
detection is Phase 3. It is recorded because agreement across an independent
published figure, a 2011–2014 radar-derived mask and a 2023 optical classifier
is strong evidence that the pipeline is looking at the right ground.

Also measured on that scene, and relevant to the core contribution: SCL class 2
(`dark area / shadow`) covers **9.76 km²**, 15.3% of the exported raster. That
is the scale of the terrain-shadow problem Phase 4 must solve.

## Phase 2 — Preprocessing

### 2.1 Citation register

| Quantity | Source |
|---|---|
| Slope, aspect (3×3 kernel), hillshade | Horn, B. K. P. (1981). "Hill shading and the reflectance map." *Proc. IEEE* **69**(1), 14–47. [doi:10.1109/PROC.1981.11918](https://doi.org/10.1109/PROC.1981.11918) |
| Cast-shadow horizon search | Dozier, J. & Frew, J. (1990). "Rapid calculation of terrain parameters for radiation modeling from digital elevation data." *IEEE TGRS* **28**(5), 963–969. |
| SAR layover / shadow conditions | Kropatsch, W. G. & Strobl, D. (1990). "The generation of SAR layover and shadow maps from digital elevation models." *IEEE TGRS* **28**(1), 98–107. [doi:10.1109/36.45752](https://doi.org/10.1109/36.45752) |
| Speckle filter | Lee, J. S. (1980). "Digital image enhancement and noise filtering by use of local statistics." *IEEE TPAMI* **PAMI-2**(2), 165–168. |
| Cloud Score+, 0.60 clear threshold (0.50–0.65 usable) | Pasquarella, V. J., Brown, C. F., Czerwinski, W. & Rucklidge, W. J. (2023). "Comprehensive Quality Assessment of Optical Satellite Imagery Using Weakly Supervised Video Learning." *IEEE/CVF CVPRW*, 2125–2135. [doi:10.1109/CVPRW59228.2023.00206](https://doi.org/10.1109/CVPRW59228.2023.00206) |

All five were verified against the literature before use, not quoted from memory.

### 2.2 Self-shadow and cast shadow are computed separately

Two physically distinct effects are both called "shadow":

* **self-shadow** — the facet faces away from the sun, `cos(incidence) ≤ 0`;
* **cast shadow** — the facet faces the sun but another landform blocks it,
  requiring a horizon search along the solar azimuth.

They are returned as separate layers and unioned only on request, because Phase
4 treats "dark because the slope tilts away" and "dark because a ridge is in the
way" as different evidence.

**Measured over the default AOI** (S2 2023-10-24, sun azimuth 158.7°, zenith
41.6°):

| Component | Fraction of raster |
|---|---|
| self-shadow | 5.6% |
| cast shadow | 14.6% |
| **cast-only share of all shadowed area** | **66.4%** |

A `cos(incidence) < 0` test alone — the obvious implementation — would therefore
**miss roughly two thirds of the shadowed area** in this terrain. This is the
quantitative justification for implementing the horizon search.

### 2.3 Validation of the cast-shadow algorithm

Validated two independent ways, neither of which re-runs the implementation:

1. **Analytic.** A vertical wall of height `h` under a sun at elevation `e`
   casts a shadow of exactly `h / tan(e)`. Measured against that identity at
   four sun elevations, the implementation agrees to **within one 10 m cell**
   (`tests/test_terrain.py::test_cast_shadow_length_matches_analytic_solution`).
2. **Independent implementation.** Against `ee.Terrain.hillShadow` — the Earth
   Engine function the brief names — over the same DEM, grid and sun angles:
   **92.3% pixel agreement**, IoU 48.2%. Our mask is the more conservative of
   the two (13.4% vs 8.7% of the raster).

Geometry conventions were confirmed by aspect: under a sun at 157.5° (SSE),
shadow fraction runs NW 57.6% > N 39.7% > W 27.6% … > SE 0.4%, which is the
expected ordering.

### 2.4 Finding: observed brightness is a poor validator of shadow in this terrain

An additional, stricter check was attempted — does the shadow mask predict
observed Sentinel-2 brightness? **It does not**, and the investigation is
recorded here because the negative result matters for Phase 4.

Measured over clear pixels: `r(illumination, brightness) = −0.18`; high-pass
`r ≈ +0.02` at every spatial scale from 20 m to 640 m. Shadowed pixels are
consistently **brighter** than sunlit ones.

Ruled out, each by direct test:

| Candidate cause | Test | Result |
|---|---|---|
| Shadow algorithm wrong | analytic + `ee.Terrain.hillShadow` | ruled out — 92.3% agreement |
| Orientation / flip bug | all four flips correlated | ruled out — none improves on as-is |
| DEM/scene misregistration | lake-mask cross-correlation, ±600 m | ruled out — best IoU (78%) at **zero** shift |
| DEM export or mosaic wrong | compared against **NASADEM** | ruled out — r = **0.999**, mean diff −1.4 m |
| Snow/material confound | stratified by elevation, slope, and within snow-only and snow-free strata | inversion persists in every stratum |
| SCL selection bias | stratified by DEM variables only | real but secondary (SCL 2 is 49.6% shadowed vs SCL 5 at 5.5%) |

NASADEM, an entirely independent DEM, reproduces the same weak correlation
(−0.16). The conclusion is therefore about the **scene**, not the code: at
4150–6600 m with roughly 20–40% snow cover, Sentinel-2 L2A surface reflectance
is dominated by surface material and by diffuse skylight multiply scattered
between high-albedo snow surfaces, which fills terrain shadows. Direct-beam
geometry is not the controlling term.

**Consequence for Phase 4.** The brief's Section 7.3 rule begins "Dark optical
pixel + in terrain shadow …". On this evidence, *darkness must not be used as a
proxy for being shadowed* in snow-dominated high-altitude scenes — the terrain
shadow mask has to come from geometry (as it does here), and the fusion must not
assume shadowed pixels are dark. This is recorded as an open design input to
Phase 4 rather than silently worked around.

### 2.5 Cloud masking, and why the separation is enforced

`SCL` class 2 ("dark area pixels") is **refused** as a cloud or cloud-shadow
class by the config schema, not merely by convention: in steep terrain it is
dominated by topographic shadow, which this project must keep and reason about.

Measured on S2 2023-10-19 over the default AOI:

| Quantity | Value |
|---|---|
| terrain shadow | 14.76% |
| cloud shadow | 0.18% |
| overlap | 0.10% |
| terrain shadow **not** cloud shadow | 14.65% |
| **terrain shadow still usable** | **14.41%** |

Merging the two categories would have discarded **14.41% of the scene** as
unusable when it is real, usable ground observation.

### 2.6 Sentinel-1 units: no dB conversion

Confirmed again in Phase 2: `COPERNICUS/S1_GRD` serves VV/VH already in
decibels. `preprocessing.sar.to_decibels` **raises** on input that already looks
logarithmic, because a silent double conversion produces plausible-looking
nonsense. `convert_to_db` is `false` by default.

### 2.7 SAR geometry, and why both orbit passes are needed

Layover where `α ≥ θ`, shadow where `α ≤ θ − 90°`, foreshortening where
`0 < α < θ`, with `α` the terrain slope in the ground-range direction and `θ`
the incidence angle (Kropatsch & Strobl 1990). Sentinel-1 is right-looking, so
from a target the sensor lies at `heading − 90°`; the configured defaults are
257.5° (ascending) and 102.5° (descending).

Measured over the default AOI:

| Pass | Incidence | Layover | Radar shadow | Foreshortening | **Unreliable** |
|---|---|---|---|---|---|
| ASC012 | 32.9° | 22.6% | 9.0% | 23.9% | **31.6%** |
| DESC121 | 40.3° | 20.6% | 6.6% | 30.0% | **27.2%** |

| Combination | Fraction |
|---|---|
| unreliable in **both** passes | **15.7%** |
| unreliable in either | 43.1% |
| of those, recovered by the second pass | **63.5%** |

A single orbit pass leaves roughly 30% of this AOI geometrically unusable; using
both halves that to 15.7%. This is the quantitative reason the brief's
requirement to keep passes separate (Section 5) matters operationally, and it
directly feeds the "defer to optical evidence" rule in Section 7.3.

### 2.8 Hydrology

Depression handling defaults to **breaching** rather than filling: filling
raises every pit to its spill level, which in steep terrain can flood real
valley floors and shift channels, whereas breaching cuts a narrow outlet and
preserves the drainage pattern.

Measured over the default AOI at `stream_threshold_cells: 500` (0.05 km² at
10 m):

| Quantity | Value |
|---|---|
| stream cells | 24,037 |
| approximate channel length | 240.4 km |
| drainage density | 3.78 km/km² |

The channel-length figure counts one cell as one cell-width of channel, which
under-reports diagonal runs by up to √2. Stated rather than silently assumed.

### 2.9 Stacking rules

Categorical layers (`SCL`, masks, SAR geometry classes, stream mask) are
resampled **nearest-neighbour regardless of configuration**: interpolating class
codes would invent classes that do not exist — averaging "cloud" (9) and
"snow/ice" (11) would yield "thin cirrus" (10), a fabricated observation.

## Phase 3 — Rule-based water detection

The baseline water detector: spectral indices plus a data-driven Sentinel-1
threshold. It is built before the U-Net and before the shadow-rejection fusion,
and it is deliberately **shadow-naive** — nothing in `detection/water.py` reads
the terrain-shadow mask. Section 7.3 of the brief requires Phase 4 to report its
false-water reduction "compared with the index-only mask", so that mask has to
exist here, unimproved, as the thing to measure against.

### 3.1 Citation register

| Quantity | Source |
|---|---|
| NDWI = (Green − NIR)/(Green + NIR), water > 0 | McFeeters, S. K. (1996). "The use of the Normalized Difference Water Index (NDWI) in the delineation of open water features." *Int. J. Remote Sensing* **17**(7), 1425–1432. [doi:10.1080/01431169608948714](https://doi.org/10.1080/01431169608948714) |
| MNDWI = (Green − SWIR1)/(Green + SWIR1), water > 0 | Xu, H. (2006). "Modification of normalised difference water index (NDWI) to enhance open water features in remotely sensed imagery." *Int. J. Remote Sensing* **27**(14), 3025–3033. [doi:10.1080/01431160600589179](https://doi.org/10.1080/01431160600589179) |
| Between-class-variance thresholding | Otsu, N. (1979). "A threshold selection method from gray-level histograms." *IEEE Trans. SMC* **9**(1), 62–66. [doi:10.1109/TSMC.1979.4310076](https://doi.org/10.1109/TSMC.1979.4310076) |
| Tiled thresholding where the water class is a small image fraction | Chini, M., Hostache, R., Giustarini, L. & Matgen, P. (2017). "A hierarchical split-based approach for parametric thresholding of SAR images: Flood inundation as a test case." *IEEE TGRS* **55**(12), 6975–6988. [doi:10.1109/TGRS.2017.2737664](https://doi.org/10.1109/TGRS.2017.2737664) |
| Two-peak separation criterion Δμ ≥ 2 | Ashman, K. M., Bird, C. M. & Zepf, S. E. (1994). "Detecting bimodality in astronomical datasets." *Astronomical Journal* **108**, 2348–2361, eqs. 3.1–3.2 (citing Everitt & Hand 1981). [doi:10.1086/117248](https://doi.org/10.1086/117248) |
| Water/snow discriminator: NIR reflectance < 0.11 | Hall, D. K., Riggs, G. A. & Salomonson, V. V. (1995). "Development of methods for mapping global snow cover using MODIS data." *Remote Sensing of Environment* **54**(2), 127–140. [doi:10.1016/0034-4257(95)00137-P](https://doi.org/10.1016/0034-4257(95)00137-P); restated in Hall et al. (2002), *RSE* **83**(1–2), 181–194. [doi:10.1016/S0034-4257(02)00095-0](https://doi.org/10.1016/S0034-4257(02)00095-0) |

Every entry was checked against the source before use. Two checks changed what
was implemented, and are recorded in 3.2 and 3.4 rather than quietly absorbed.

### 3.2 Finding: MNDWI is the same expression as NDSI, so it scores snow as water

MNDWI (Xu 2006) is `(Green − SWIR1)/(Green + SWIR1)`. The Normalized Difference
Snow Index (Hall et al. 1995) is **the same formula on the same two bands**.
MNDWI therefore cannot distinguish snow from water even in principle — snow is
bright in green and strongly absorbing in SWIR1, so it scores *high*, exactly
like water.

This matters here more than in most settings. Measured over the default AOI
(Tsho Rolpa, S2 tile 45RVL, 2023-10-19, 592 221 cloud-free pixels, 42% of them
SCL snow/ice):

| Optical rule | Water | Largest body | Fraction SCL snow/ice |
|---|---|---|---|
| MNDWI > 0 | 32.233 km² | 13.302 km² | 74.0% |
| NDWI > 0 | 19.174 km² | 7.195 km² | 65.5% |
| NDWI > 0 **and** MNDWI > 0 | 18.542 km² | 6.821 km² | 67.5% |
| NDWI > 0 and MNDWI > 0 and NIR < 0.11 | **2.683 km²** | **1.601 km²** | **5.6%** |

With indices alone the 1.5 km² lake is merged into a 13 km² blob of glacier and
snowfield. Neither index rejects snow; MNDWI is merely the worse of the two.

**The screen applied.** The MODIS snow-mapping algorithm faces the mirror image
of this problem — water reaching NDSI ≥ 0.4 and being mapped as snow — and
resolves it with a near-infrared test: "Since water may also have an NDSI ≥ 0.4,
an additional test is necessary to separate snow and water. Snow and water may
be discriminated because the reflectance of water is <11% in TM band 4" (Hall
et al. 1995; restated as MODIS band 2 in Hall et al. 2002). The same test is
used here in the opposite direction, to stop snow being mapped as water:
`detection.water.optical.snow_screen_nir_max_reflectance`, default **0.11**.

It removes **85.5%** of index-only water pixels (158 591 of 185 417) and brings
the largest body from 13.302 to **1.601 km²**, against a published 1.537 km²
(Shrestha & Nakagawa 2014) and an independent DEM-epoch water-body mask of
1.550 km². Recall of that DEM-epoch mask stays at **95.7%**, so the screen is
removing snow rather than shaving the lake.

The threshold is in physical reflectance, while Sentinel-2 is stored as scaled
integers (§1.4), so `optical.reflectance_scale` (1 × 10⁻⁴) converts them. The
indices are ratios and need no scaling; `S2_SR_HARMONIZED` already absorbs the
post-baseline-04.00 `BOA_ADD_OFFSET`, so no offset term is required.

The unscreened mask is retained as `WaterEvidence.pre_screen_water` whatever the
configuration, because it is the Phase 4 baseline. Setting the screen to `null`
disables it.

### 3.3 Sentinel-1 thresholding: tiled, because the water class is small

Otsu's method maximises between-class variance and so assumes two classes of
comparable mass. Over this project's AOIs water is a few percent of the scene,
which Chini et al. (2017) identify as the case that breaks whole-image
thresholding: "the histogram of the image values is often not obviously bimodal
when the target class covers only a small part of the image".

`tiled_otsu` (the default) thresholds each 128 px tile, keeps only tiles whose
histogram actually separates, pools those pixels and thresholds once — a single
scene-wide threshold, so no seams appear at tile boundaries. It is a
simplification of the hierarchical split-based approach, which searches tile
size hierarchically; here the scale is a single configured value.

Measured on a synthetic image with a 0.39% water fraction (`tests/test_water.py`):

| Method | Threshold | Selected as water | Truth |
|---|---|---|---|
| Whole-image Otsu | −8.16 dB | **43.53%** | 0.39% |
| Tiled Otsu, 32 px | −17.34 dB | 0.39% | 0.39% |

Note what fails: under that imbalance global Otsu still *reports* a valid
separation, and what it gets wrong is **where** it puts the threshold — it
splits the dominant land mode instead of dividing land from water. The
bimodality guard of 3.4 therefore does not catch this on its own; tiling is what
fixes it.

### 3.4 Finding: the separation statistic must be computed on *fitted* modes

The guard on Otsu's assumption is the two-peak criterion of Ashman, Bird & Zepf
(1994): Δμ = (μ₂ − μ₁)/σ ≥ 2. Checking the paper changed the implementation
twice.

**First, what the paper actually says.** The criterion is usually quoted as
"Ashman's D > 2". Equations 3.1–3.2 define a *dimensionless separation of the
means* for **equal-variance** Gaussians, Δμ = (μ₂ − μ₁)/σ, with the ≥ 2
condition attributed to Everitt & Hand (1981), and the paper is explicit that
this is the two-peak condition for infinite N, not a detection cutoff for finite
samples. The unequal-variance form used in this project,
√2·|μ₂ − μ₁| / √(s₁² + s₂²), is the standard later generalisation and reduces to
eq. 3.1 when s₁ = s₂; it is **not** from that paper, and is labelled as such in
the code.

**Second, and more consequential: the statistic must not be computed by
hard-splitting the sample at the threshold.** Truncating a distribution at a
threshold pushes the two resulting means apart and shrinks both standard
deviations, so the statistic is inflated by the split itself. Measured on a
single Gaussian split at its own Otsu threshold:

| Sample | Hard-split statistic | EM-fitted statistic |
|---|---|---|
| Single Gaussian, σ = 2 | **2.67** | **0.99** |
| Single skewed (gamma) mode | 2.67 | 1.48 |
| Two weakly separated modes (Δμ = 1.5) | 2.73 | 1.40 |
| Two separated modes (Δμ ≈ 9) | 9.26 | 9.27 |

The hard-split value for a *single Gaussian* is 2.67, which clears the ≥ 2
criterion. A guard built that way would certify every unimodal histogram as
bimodal — it would always pass, and so would guard nothing. This was caught by
a unit test asserting that a single Gaussian is not bimodal, which failed.

`detection.water.bimodality` therefore fits a two-component 1-D Gaussian mixture
by expectation-maximisation (initialised from the Otsu split, so it stays
deterministic; responsibilities in log space) and measures the separation
between the **fitted** components. The fit recovers a generating Δμ of 4.0 as
4.0002, so it neither inflates nor deflates.

### 3.5 Finding: single-scene SAR amplitude thresholding fails in this terrain

Over the default AOI the derived Sentinel-1 threshold is supported by the
bimodality test and is still wrong in substance:

- Descending VV: −10.42 dB from 33 of 49 tiles, fitted modes −21.36 ± 1.65 and
  −6.99 ± **7.67** dB, separation 2.59. It selects **47.6% of the AOI** as water.
- Ascending VV: −7.79 dB, separation 2.42. Similar behaviour.

The cause is terrain, not thresholding. **27.2%** of this AOI is radar layover
or shadow, and **42.3%** of the SAR "water" falls inside that mask: a radar
shadow in a steep valley is as dark as a lake. The fitted bright mode's standard
deviation of 7.67 dB is itself the symptom — that is topographic modulation, not
a land class.

Deriving the threshold from geometrically reliable pixels only (excluding
layover and shadow) does **not** fix it: −8.46 dB, still 37.5% of the AOI. So
the problem is radiometric as well as geometric, and a geometry mask alone will
not repair it. Radiometric terrain correction or multi-temporal persistence is
required. **This is an open design input to Phase 4**, recorded here rather than
worked around.

Phase 3 does not apply the layover/shadow mask to the SAR water mask, because
deciding what a SAR-water-like pixel inside that mask *means* is Section 7.3's
"uncertain → defer to optical evidence", which is Phase 4's judgement. The
unmodified SAR mask is the baseline; the geometry statistics above are reported
alongside it as a diagnostic.

### 3.6 Combination rule: intersection, on measured evidence

`detection.water.combine` was initially set to `union`, reasoning that the most
inclusive mask gives Phase 4 the most false water to remove. The data refuted
that, because union inherits the SAR failure of 3.5 wholesale. Measured over the
default AOI against two independent references (DEM-epoch water-body mask
1.550 km²; published 1.537 km²):

| Rule | Water | Bodies | Largest | DEM-WBM recall | SCL snow/ice | In SAR layover/shadow |
|---|---|---|---|---|---|---|
| optical | 2.683 km² | 102 | 1.601 km² | 95.7% | 5.6% | 10.3% |
| sar | 30.299 km² | 219 | 12.868 km² | 98.4% | 44.3% | 42.3% |
| union | 30.608 km² | 224 | 13.041 km² | 98.5% | 44.0% | 42.0% |
| **intersection** | **2.373 km²** | **95** | **1.578 km²** | **95.6%** | **4.5%** | 10.6% |

Intersection — both sensors must agree — gives the largest body closest to both
references, with the least snow contamination, at no measurable cost in recall
of the DEM-epoch surface. It also matches the brief's own Section 7.3
instruction to defer to optical evidence where SAR is unreliable.

Note that SAR's apparently excellent 98.4% recall is not evidence of quality: a
mask covering 47.6% of the AOI recovers most of anything. Recall is reported
only alongside total area, never on its own.

All four rules are recomputed and recorded in `outputs/phase3_water_report.json`
on every run, so the choice of default stays reproducible and reversible.

### 3.7 Water bodies

`water_bodies` polygonises the mask with `rasterio.features.shapes` and measures
each body in the projected CRS, which `utils.crs.ensure_projected` enforces —
a geographic CRS is refused outright (brief, Section 6). Polygon area accounts
for interior rings, so an island inside a lake is not counted as water. Bodies
below `polygons.min_area_m2` (1000 m², i.e. 10 pixels — a convention, not a
published threshold) are dropped and the count is logged, never discarded
silently. 8-connectivity is the default so that a channel running diagonally
across the pixel grid stays one body.

Each body carries area, perimeter, pixel count, projected centroid and
geographic centroid; `boundaries()` derives the outline from the polygon rather
than storing it as a second column that could drift.

### 3.8 What is *not* claimed

- Areas are `derived` from a `classified` mask, not `observed`. A rule-based
  threshold is a classification.
- The agreement with the published 1.537 km² is a plausibility check, not an
  accuracy assessment: the published figure predates these 2023 scenes, Tsho
  Rolpa has been growing, and one date is not a validation.
- The GLO-30 water-body mask is an **independent observation** from the
  2011–2014 DEM epoch, not ground truth.
- No depth or volume is computed here. Tsho Rolpa existed when the DEM was
  acquired, which places it in depth **Branch B** (brief, Section 8): the DEM
  recorded the water surface, so the lake bed is unknown and depth is
  `unavailable`. Phase 10 enforces this.

## Phase 4 — Shadow rejection

The core contribution. Per-pixel `p_water`, `p_terrain_shadow` and `p_land`
from a transparent additive fusion of the optical indices, the terrain-shadow
mask, illumination, SAR backscatter, the SAR layover/shadow mask and
multi-temporal persistence — and a measured reduction in false water relative
to the Phase 3 index-only mask.

### 4.1 Citation register

| Quantity | Source |
|---|---|
| Topographic shadow where slope > 10° **and** shaded relief < 0.25 | Chen, F., Zhang, M., Guo, H., Allen, S., Kargel, J. S., Haritashya, U. K. & Watson, C. S. (2021). "Annual 30 m dataset for glacial lakes in High Mountain Asia from 2008 to 2017." *ESSD* **13**(2), 741–766. [doi:10.5194/essd-13-741-2021](https://doi.org/10.5194/essd-13-741-2021) |
| Water/snow discrimination at NIR < 0.11 reflectance | Hall, D. K., Riggs, G. A. & Salomonson, V. V. (1995), as §3.1 |

Chen et al. is the closest published analogue to this project: glacial lakes,
High Mountain Asia, the same shadow-versus-water confusion. Their two
topographic criteria are adopted verbatim as the **crossing points** of the
slope and illumination memberships, so each threshold keeps its cited meaning
while producing a probability rather than a hard veto. Verified against the
paper: "Topographic shadows were masked using the slopes (larger than 10∘) and
shaded relief values (less than 0.25)", calculated from SRTM. This project
computes both from Copernicus GLO-30 and, for illumination, from **each scene's
own sun angles** rather than a nominal illumination.

### 4.2 What `p_terrain_shadow` means, and why it is not "is shadowed"

Three mutually exclusive probabilities only make sense under a careful reading
of what the shadow class *is*. A lake inside a shadow is still a lake: "water"
and "in shadow" are not alternatives, so a naive three-way competition would be
incoherent.

The brief resolves this itself. Section 7.5 names class 3 "terrain shadow
(**material indeterminate**)", and the labelling rule in Section 7.5 adds that
"a landslide scar or lake inside shadow keeps its material class if it is
identifiable". So:

> `p_terrain_shadow` is the probability that shadow leaves the surface material
> **indeterminate** — not the probability that the pixel is geometrically
> shadowed, which the Phase 2 mask already states deterministically.

Implemented as a **determinacy discount**: the shadow score is reduced by
`material_determinacy_weight` × the strength of determinate material evidence.
If the material can be told, the pixel is not "shadow, material indeterminate".

This is what makes the three Section 7.3 rules *fall out* of the fusion rather
than being special-cased, which matters because a special case would not
generalise to evidence combinations the brief does not enumerate:

| Section 7.3 rule | How it arises |
|---|---|
| dark optical + terrain shadow + SAR **not** water-like → shadow | SAR support is negative, so water loses; the shadow score stands |
| dark optical + terrain shadow + SAR water-like (not in SAR shadow/layover) → water | SAR support is positive *and* determinate, which both raises water and discounts shadow |
| SAR water-like but inside SAR layover/shadow → uncertain, defer to optical | the SAR term is withdrawn entirely, nothing is fully determinate, the verdict rests on optical evidence, and the pixel is flagged `sar_deferred_to_optical` |

Each is pinned by a test in `tests/test_shadow_rejection.py::TestSection73Rules`,
including one asserting that rules 1 and 2 differ **only** in the SAR evidence.

### 4.3 How determinate each source is

Not all evidence determines *material*; some only reports illumination.

- **SAR and persistence count fully.** SAR is illumination-independent, so a
  shadow does not weaken it at all — this is exactly why SAR resolves a shadow
  ambiguity. A pixel reading as water across observations is likewise not
  material-indeterminate.
- **The optical indices count partially**, at
  `membership.optical_determinacy_scale` (0.5, convention). NDWI and MNDWI are
  band *ratios*, in which the illumination factor cancels to first order; that
  first-order cancellation is why ratio indices are usable in steep terrain at
  all, and it means they do retain material information inside a shadow. Only
  to first order, though: diffuse skylight is spectrally unlike the direct
  beam, and §2.4 measured that reflectance in these snow-dominated scenes is
  not governed by direct-beam geometry. Hence a scale below 1, not equal to it.
- **Illumination and the shadow mask determine nothing about material.** They
  are the shadow evidence itself.

Setting the optical scale to 0 makes a flat, strongly water-like, NIR-dark
pixel inside a shadow come out as *shadow* rather than water when SAR is
unavailable — which contradicts the brief's own instruction to defer to optical
evidence in that case. That failure is what identified this term.

### 4.4 Finding: flatness is a necessary condition for water, not evidence of it

The first implementation treated slope symmetrically: flat ground supported
water as strongly as steep ground opposed it. The ablation exposed the error —
**removing the slope term entirely *reduced* detected water**, from 6.67 to
3.25 km², which is only possible if the term was manufacturing water.

It was. Almost all flat ground in any AOI is dry land, so "flat" carries
essentially no information in favour of water, while "steep" is decisive
against it. Chen et al. (2021) use slope the same way: as an exclusion
criterion, never an inclusion one.

`membership.slope.flat_support_scale` (default **0.0**) makes the term
one-sided. Measured over the default AOI with all other evidence fixed and
persistence excluded, so the slope term is isolated:

| `flat_support_scale` | Water | False water removed | Known water kept |
|---|---|---|---|
| 0.0 (one-sided, default) | 4.18 km² | 81.9% | 96.6% |
| 0.5 | 6.85 km² | 76.1% | 97.0% |
| 1.0 (symmetric) | 9.50 km² | 73.2% | 97.1% |

Symmetry more than doubles detected water — promoting valley floors and flat
glacier surfaces — to buy 0.5 points of known-water retention. The asymmetry is
physics, not tuning.

### 4.5 Finding: persistence cannot discriminate shadow over a short window

Section 7.3 lists multi-temporal persistence as a fusion input, on the
reasoning that a lake stays put while a shadow moves. **That reasoning fails
when the scenes share an overpass geometry.**

The two available Sentinel-2 dates over the default AOI are 2023-10-19 and
2023-10-24, from the same relative orbit. Their sun angles differ by 1.6° in
zenith and 1.2° in azimuth, so the shadow barely moves: the
intersection-over-union of the shaded-relief criterion (hillshade < 0.25)
between the two dates is **0.933**.

Persistence is therefore implemented and used, but over this window it
discriminates **cloud and speckle**, not shadow. It is still worth having —
dropping it raises detected water from 2.49 to 4.18 km² — but the improvement
comes from suppressing transient false positives, not from shadow logic.
Discriminating shadow this way needs dates months apart, at substantially
different solar elevations. Recorded so the term is not credited with something
it did not do.

The term is skipped entirely below `min_observations` (default 2) rather than
being computed from too little evidence.

### 4.6 Results, ablation and sensitivity

Over the Phase 2 stack of Tsho Rolpa (S2 45RVL 2023-10-19 + 2023-10-24,
S1 DESC121, GLO-30), against the Phase 3 index-only baseline, with the GLO-30
DEM-epoch water-body mask as an independent reference:

| Quantity | Value |
|---|---|
| Index-only baseline | 18.542 km² (185 417 px) |
| After fusion | **2.487 km²** (24 868 px) |
| **False water removed** | **162 199 px — 87.5% of the baseline** |
| **Known water retained** | **96.4%** (baseline retained 97.9%) |
| Classified: land / water / terrain shadow | 86.8% / 4.0% / 9.2% |
| Uncertain | 0.6% |
| Water bodies ≥ 1000 m² | 87; largest **1.614 km²** |

Of what was removed, 76.4% is SCL snow/ice, 82.5% has slope > 10°, 31.3% lies
in terrain shadow — and only **0.2%** falls inside the known-water reference.
The removals are overwhelmingly justified, and the 1.5-point cost in retention
is what they cost.

**Ablation** (each term's weight set to zero; "water" is the confident water
area):

| Configuration | Water | Removed | Retained |
|---|---|---|---|
| all evidence (default) | 2.49 km² | 87.5% | 96.4% |
| without NIR | 5.34 km² | 77.6% | 96.7% |
| without persistence | 4.18 km² | 81.9% | 96.6% |
| without slope | 3.28 km² | 85.4% | 96.9% |
| without SAR | 2.33 km² | 87.7% | 96.1% |
| without water index | 2.34 km² | 88.6% | 96.1% |
| without illumination | 2.47 km² | 87.5% | 96.4% |
| without terrain-shadow mask | 2.49 km² | 87.2% | 96.4% |

NIR is the single most load-bearing term, which is consistent with §3.2: snow
is the dominant false-water source here, and NIR is what separates it. The two
*geometric* shadow terms barely move the totals — not because shadow is
unimportant, but because slope has already excluded most of the same pixels,
and the three are strongly correlated in this terrain.

**Sensitivity.** The weights are convention; there is no published weighting
for this combination. Halving and then doubling each of the seven weights in
turn, and varying `material_determinacy_weight` over 1–3 (16 variants):

- false water removed: **80.1% – 89.0%**
- known water retained: **95.8% – 96.8%**

The conclusion does not depend on the weights. They are reported this way
rather than presented as tuned constants, and every per-pixel verdict can be
traced to its contributing factors through `FusionResult.explain()`.

### 4.7 What is *not* claimed

- The reduction is measured against **one scene pair at one site**. It is not a
  validation of the method, and no accuracy figure is claimed.
- The GLO-30 water-body mask is an independent observation from the 2011–2014
  DEM epoch, not ground truth. "Known water retained" is retention of *that
  mask*, which itself contains shoreline error.
- `p_water` is a transparent evidence score passed through a softmax. It is
  **not a calibrated probability**: no reliability diagram has been produced,
  and none can be without labelled data. Phase 6 is where labels arrive.
- Snow and landslide/debris are not classes here. A pixel that is neither
  water nor shadow-indeterminate is "land", which lumps rock, debris, snow and
  vegetation together. Phase 6's five-class model is where that is resolved.
- The SAR term still rests on the single-scene threshold that §3.5 showed to be
  unreliable in this terrain. The fusion contains the damage — the layover and
  shadow gate plus a modest weight — but does not repair it. Radiometric
  terrain correction remains the right fix.

## Phase 5 — Bi-temporal landslide change detection

**Status: module complete and unit-tested; the real-data gate is not yet run.**
The gate ("change map produced for a documented event") needs imagery of one of
the events confirmed in `validation.md` §2, which needs Earth Engine access.
Everything below is implemented and tested on synthetic pairs; nothing is
claimed about real performance yet.

This module is the **sole source of novelty** in the system. The brief
(Section 7.4) is explicit that the U-Net classifies landslide-*like* surfaces
on a single date, so "new" must come from here. A scar that was already present
before the event is not a new landslide, however confidently a classifier
labels it.

### 5.1 Citation register

| Quantity | Source |
|---|---|
| NDVI | Rouse, J. W., Haas, R. H., Schell, J. A. & Deering, D. W. (1974). "Monitoring vegetation systems in the Great Plains with ERTS." *NASA SP-351*, 309–317 |
| NDVIvar = NDVI_post − NDVI_pre; threshold −0.20 to −0.15; pixel slope > 15°; polygon median slope ≥ 17°/20° | Notti, D., Cignetti, M., Godone, D. & Giordan, D. (2023). "Semi-automatic mapping of shallow landslides using free Sentinel-2 images and Google Earth Engine." *NHESS* **23**(7), 2625–2648. [doi:10.5194/nhess-23-2625-2023](https://doi.org/10.5194/nhess-23-2625-2023) |
| Snow where NDSI ≥ 0.4 **and** NIR > 0.11 | Hall, Riggs & Salomonson (1995), as §3.1 |
| Backscatter rises on some parts of a landslide and falls on others | Burrows et al. (2022); Mondini et al. (2021) — **cited via** the Engineering Geology (2023) landslide-dating paper, not read at source. Flagged as second-hand rather than presented as verified |

Verified at source: the Notti et al. thresholds were read from the paper
itself, including the exact wording "the optimal threshold should be in the
range of −0.20 to −0.15" and its application as "NDVIvar ≤ −0.15 joined to
slope > 15∘".

### 5.2 Three signals, and why agreement is required

Each of the three signals the brief names has a failure mode on its own:

| Signal | Fails when |
|---|---|
| NDVI drop | the ground was already bare, or vegetation changed seasonally |
| Brightness / SWIR increase | illumination changed between dates, or fresh snow fell |
| SAR backscatter change | the viewing geometry or surface moisture changed |

`min_agreeing_signals` (default **2 of 3**) is therefore not a tuning
parameter but the mechanism that makes the three complementary. A signal whose
inputs were not supplied is treated as **absent**, never as disagreeing, so a
pair with no SAR scene still works on the two optical signals.

One consequence is deliberate and worth stating: where fewer signals are
available than the requirement demands, the result is **undecidable**, not "no
change". Those pixels are excluded from `valid` rather than reported as stable,
because otherwise a data gap would masquerade as evidence of no landslide.

### 5.3 SAR change is used by magnitude, not sign

A landslide does not move backscatter in a consistent direction: it rises on
some parts of a failure and falls on others. Thresholding the *signed* change
would therefore systematically miss half of each landslide. The implementation
thresholds `|σ⁰_post − σ⁰_pre|`.

**A limitation that cannot be engineered away here.** The literature's stronger
SAR indicator for landslides is interferometric **coherence loss**, not
amplitude change. `COPERNICUS/S1_GRD` — the collection this project uses, fixed
in Phase 1 — carries **amplitude only**; coherence requires SLC data and an
interferometric pair. So the SAR signal in this phase is the weaker of the two
available in principle. Recorded rather than worked around; adding SLC
processing would be a substantial change of scope.

### 5.4 Snow is the dominant confounder, and is screened per pixel

Fresh snow between the two dates crushes NDVI and raises brightness — exactly a
landslide's optical signature. This is not a hypothetical risk here: Phase 3
measured 42% of the default AOI as SCL snow/ice, and Phase 4 found snow to be
the single largest source of false water.

Notti et al. (2023) avoid the problem by **selecting** imagery from "the season
with the highest NDVI … no snow coverage, and a short shadow". A monitoring
prototype cannot choose its dates that freely — a landslide dam must be
assessed when it happens, not when the imagery is convenient. So snow is
screened **per pixel on both dates** with the test of Hall et al. (1995), and a
pixel that is snow on *either* date is excluded as unattributable. Excluding it
is the honest outcome: with snow on one date, the change is genuinely
unknowable, and that is different from knowing there was no change.

Terrain shadow on either date is excluded for the same reason, following §2.4.

### 5.5 Where no threshold is published, one is derived — not invented

Only the NDVI threshold has a published value. For the brightness and SAR
signals no validated threshold was found, so rather than inventing numbers the
default method is a **robust z-score** over the scene's own change
distribution: median plus *z* × (MAD × 1.4826).

The median absolute deviation is used rather than a standard deviation because
speckle and the long tail of genuine change both drag a mean. The test suite
pins this: contaminating a standard normal sample with 3% extreme outliers
moves the classical mean + 3σ threshold above 50, while the robust threshold
stays below 10.

`fixed` alternatives exist for both signals, and both refuse to load without an
explicit value — the same rule as the Phase 3 SAR threshold.

### 5.6 Gating before belief

In order: cloud/defective on either date → snow on either date → terrain shadow
on either date → slope below `min_slope_deg` (15°, cited). Only then are the
signals compared. Polygons are additionally filtered on **median** slope
(≥ 17°, cited), because a polygon straddling flat ground is unlikely to be a
landslide even where some of its pixels are steep.

### 5.7 Known debt

`detection.landslide_change` imports `spectral_index` from
`detection.water`, which is where the first normalised-difference index
happened to need it. It is a generic helper and belongs in a shared module; it
is imported rather than duplicated, and the move is deferred to avoid churning
a reviewed phase.

### 5.9 Finding: the cited slope gate removes the dam

Phase 5's pixel-level gate, `min_slope_deg = 15`, comes from Notti et al.
(2023), who pair it with their NDVI threshold. It is correct for what they
map: shallow landslide **source areas**, which are steep by definition.

A landslide **deposit** that blocks a river is not. It lies on the valley
floor, which is flat by definition — that is what makes it a dam.

Run end to end, the consequence is concrete and quiet. The gate carves the
channel-crossing part out of the debris, so one landslide becomes two
connected components either side of the river, Phase 5 reports two polygons,
and Phase 7 then raises **two duplicate dam candidates for a single event**.
Nothing errors; the output is simply wrong in a way that looks plausible.

Neither value is wrong in itself — they answer different questions. The
default stays at the cited 15°, because that is what the source supports and
Phase 5's own deliverable is a landslide inventory. But **for landslide-dam
detection the gate must be lowered**, and
`tests/test_pipeline_end_to_end.py` does exactly that, with the reasoning in
its fixture. A deployment aimed at river blockage should set
`min_slope_deg` and `min_median_slope_deg` near zero and rely on Phase 7's
stream-proximity requirement to reject hillside debris instead.

### 5.10 Phase 5 on a real event — Baige, Jinsha River, 2018

The sections above were written against synthetic arrays. This one is the
first run of Phase 5 on real imagery of a documented landslide dam, and it
changed the module.

**The event.** The Baige landslide dammed the Jinsha River in Jiangda County,
Tibet, twice: 2018-10-10 and again 2018-11-03. The published coordinate is
98.70499 E, 31.08234 N — which turns out to be the landslide **source area**
on the right bank, not the blockage point (§5.13). Sources and the volume
conflict between them are recorded in `docs/validation.md` §2.2. The site
overlay is `config/sites/baige_2018.yaml`.

**Only the second dam is attempted.** No Sentinel-2 scene in the acquisition
window passes the cloud filter *before* 2018-10-10, so the first dam has no
optical pre-event baseline. This is recorded in the run output rather than
worked around; a missing baseline is a gap, not something to interpolate.

**The scene pair matters more than the thresholds.** The first run used the
widest available pair, 2018-11-02 → 2018-11-22, and reported 0.6355 km² of
change over 125 polygons. Twenty days at this latitude in November is enough
for the seasonal snow line to descend: 29,785 px screened as snow on the post
date against 555 on the pre date, and the residual snow edge dominated the
map. Re-running on the tightest pair that still straddles the event,
2018-11-02 → 2018-11-09, cut snow exclusion to 4,491 px and the change map to
0.2652 km². Both runs are kept in `outputs/`; the tight pair is the result.

**SAR is from a single relative orbit.** 2018-10-27 → 2018-11-08, relative
orbit 99, ASCENDING. Mixing orbits would compare different viewing geometries
over 30°-plus terrain, so Phase 1 records orbit metadata and Phase 5 refuses
the pair unless it matches.

### 5.11 Finding: a landslide dam makes the river change too, and the river is not debris

Phase 5 flags a pixel when two of three signals agree. New open water
satisfies two of them unaided: NDVI collapses because water absorbs NIR, and
the SAR change is large because water is specular. A change map at a
landslide-dam site therefore contains the **impounded lake** as well as the
landslide.

Measured on the first Baige run, 28.7% of the change map was newly detected
water, and the single largest polygon was 51.3% new water. The module was
reporting the lake as landslide.

The first fix excluded pixels that became water — `new_water` — and was
insufficient. The reach immediately upstream of a dam is *already* river: it
is water on both dates, so it is never "new", yet it deepens and widens into a
lake and trips both signals anyway. At Baige that reach ran NDVI −0.510 →
−0.965 and VV −10.6 → −22.8 dB and survived the filter cleanly.

The gate is therefore `exclude_water_on_post_date`: a landslide deposit cannot
be under water on the date it is observed, whatever it was before. 8,718 px
were excluded on that basis. The config key and its reasoning are in
`config/config.yaml` and `config/schema.py`.

**What this does not fix.** With post-date water excluded, the largest
remaining polygon — 13,200 m², 3.6 km from the dam, on 4° slope — runs the
*mirror* signature: NDVI −0.401 → −0.021 and VV −13.8 → **−6.4** dB, a 7.4 dB
*rise*. That is a channel that drained. Downstream of a blockage the river bed
is exposed, and dry gravel is both brighter and rougher than the water it
replaced, so brightness-increase and SAR-change agree and the pixel is
flagged.

This one is not screened out, deliberately. A landslide deposit that dams a
river *sits on the former channel* — excluding pre-date water would delete the
dam itself. Distinguishing "river bed exposed by a blockage" from "river bed
buried by debris" is not a spectral question: both are bright bare material
where water used to be. It is a question of position relative to the channel
and of which side of the obstruction the pixel lies on, which is Phase 7's
job. Phase 7 already uses downstream water loss as obstruction evidence, so
these pixels are evidence *of* the dam even though they are not debris.

Phase 5's output at a dam site must therefore be read as **"the surface
changed here in a landslide-like way"**, not as a debris inventory.

### 5.12 What the run found, and the honest size of it

With the tight optical pair, post-date water excluded, and the dam-tuned slope
gate of §5.9 (>1°):

| | cited gate (>15°) | dam-tuned gate (>1°) |
|---|---|---|
| changed pixels | 2,301 | 2,652 |
| change area | 0.2301 km² | 0.2652 km² |
| polygons | 45 | 50 |
| largest polygon | 8,300 m² | 13,200 m² |

Against the published coordinate, for the dam-tuned run:

| distance from published coordinate | polygons | area |
|---|---|---|
| ≤ 250 m | 2 | 2,200 m² |
| ≤ 500 m | 4 | 15,200 m² |
| ≤ 1000 m | 8 | 20,200 m² |
| ≤ 2000 m | 12 | 27,000 m² |

Nearest polygon: 1,000 m² at **132 m** from the published coordinate. Total
detected change 117,300 m², of which **13.0%** lies within 500 m of it.

**This is a detection, not a good one.** The method puts change within 132 m
of a landslide it was given no prior about, which is the gate check. But 87% of the
flagged area is elsewhere in the AOI — drained channel, residual snow edge,
and whatever else moved in a seven-day window — and the published deposit is
not the largest thing in the map. The polygons near the dam are small and
fragmented, which is what §5.9 predicts: the slope gate and the water gate
both cut into a deposit that lies flat on a valley floor next to water.

No per-pixel ground truth for the Baige deposit was available here, so **no
IoU, precision or recall is reported.** Distance-to-published-point and area
fractions are what the available evidence supports, and nothing stronger
should be read into them.

### 5.13 Finding: the published coordinate is the landslide, not the dam

The coordinate carried from the literature into the site overlay was treated
throughout as the dam's position. The DEM says otherwise: it sits at
**3,373.9 m on a 52.9° slope**, **626 m** horizontally from the nearest water
and **471 m above** the Jinsha surface (median 2,870.3 m). That is a valley
side, not a channel — the published location is the landslide **source area**
on the right bank, consistent with sources that describe a right-bank failure
and publish a landslide location.

Three things follow, and they cut in different directions:

- The 132 m agreement is **agreement with the source area**, which is exactly
  what a landslide change detector should find. The result stands under a
  corrected label, and it is arguably a cleaner result than the original
  reading: the detector found the scar on steep ground, where the cited 15°
  gate is valid by construction.
- It does **not** rescue the gate. The deposit on the valley floor is still
  flat and still cut by `min_slope_deg`, exactly as §5.9 describes. The two
  findings are about two different parts of one landslide.
- **Phase 7 cannot use this coordinate.** Blockage detection needs a point in
  the channel. It must be derived from the imagery — the boundary between
  water gained upstream and water lost downstream — not read from the overlay.

The upstream/downstream check was therefore made between the two water sets
rather than against the coordinate: gained water has a median DEM elevation of
2,913.8 m against 2,867.0 m for lost water, so the gain lies **46.8 m higher,
upstream** of the loss. That ordering is the obstruction signature, recovered
without any prior about where the blockage is.

A general lesson for the site overlays: a published event coordinate is a
location *for the event*, and which part of the event it names is usually
unstated. Any coordinate used as a channel position must be checked against
the DEM first.

### 5.8 What is *not* claimed

- **One real event has been processed, without ground truth.** Baige 2018
  (§5.10–5.13) puts detected change 132 m from the published landslide
  coordinate — which is the source area, not the dam (§5.13) — but
  87% of the flagged area is elsewhere and no per-pixel reference exists, so
  **no IoU, precision or recall is claimed.** Every number in the test suite
  still comes from synthetic arrays constructed so the answer is known.
- The default thresholds are a cited **starting point**. Notti et al. stress
  their NDVI threshold "does not have a fixed value" and is set by an operator
  after visual assessment; it must be calibrated per AOI before any result is
  trusted.
- A change map is **not** a landslide inventory. It marks where the surface
  changed in a landslide-like way, on a slope, excluding snow and shadow.
  Confirming that a change *is* a landslide — and that it blocks a river — is
  Phase 7's job, and the brief forbids calling a blockage without obstruction
  evidence.

## Phase 6 — Segmentation models

**Status: architecture and evaluation complete and tested; no model has been
trained.** Training needs labelled data, which needs hand-labelling in QGIS,
and a Colab GPU session. Both are the repository owner's to do. The brief's
gate — "per-class metrics plus water-vs-shadow confusion reported for both
models" — is therefore **not met**: there are no models to report on.

What exists is everything that does not require data: the Attention U-Net, a
controlled baseline, and the metrics that will judge them.

### 6.1 The Attention U-Net

`models/attention_unet.py` implements Oktay et al. (2018). A plain U-Net
concatenates each encoder skip straight into the decoder, carrying *all* the
detail the encoder saw at that scale — which in this imagery includes a great
deal of steep, bright, high-frequency terrain that has nothing to do with
water. An attention gate inserts a learned, spatially varying filter on that
skip:

```
q     = psi( relu( W_g·g + W_x·x ) )
alpha = sigmoid(q)
x_hat = alpha · x
```

where `g` is the decoder's coarser gating signal and `x` the skip. The decoder
in effect asks "given what I understand at this coarser scale, which parts of
the fine detail matter?" The gate is **additive**, which is the paper's choice.

Why it suits this problem specifically: water and terrain shadow are locally
near-identical — both dark, both smooth — and are separated mainly by
*context*, which is exactly what a coarser gating signal carries. Whether that
helps **here** is an empirical question the project is required to answer, not
an assumption.

Implementation choices worth stating:

- **Channel count is configurable.** The input is a configurable channel stack
  (Section 7.5), not three-band RGB; the default is 16.
- **Bilinear upsampling by default.** Transposed convolutions produce
  checkerboard artefacts, which on a thin lake shoreline are not cosmetic.
- **Attention coefficients can be returned**, so what the model attends to can
  be inspected rather than taken on trust. A test asserts they are
  single-channel and lie in (0, 1).
- Odd input sizes are padded through the decoder, so a 50×38 patch survives.

### 6.2 The baseline is the same network with the gates removed

`plain_unet()` returns an `AttentionUNet` built with `attention=False`.

This is deliberate. Section 7.5 requires the two models to be compared, and a
baseline taken from `segmentation_models_pytorch` would differ from the
attention model in depth, widths, normalisation, initialisation and upsampling
as well as in the gates — confounding the thing being measured with everything
else. Built this way the two differ in **exactly one** respect, so the
comparison is a controlled ablation. A test asserts identical depth and
widths, and that the gates cost parameters.

The brief's suggested `segmentation_models_pytorch` baseline remains available
and is the right thing to add alongside; it answers a different question
("how does this compare to a standard implementation?") from the ablation.

### 6.3 Evaluation refuses overall accuracy

`models/evaluate.py` computes per-class IoU, Dice, precision, recall and F1,
plus the confusion matrix. It has **no** `accuracy` attribute.

That is not an oversight. Over the default AOI water is about 4% of valid
pixels and terrain shadow about 9%; a model predicting "land" everywhere
scores roughly 87% accuracy while finding not one lake. Reporting that beside
the real metrics would invite precisely the wrong conclusion. `overall_accuracy()`
exists as a separate function, documented as misleading here, so that anyone
reporting it has to reach for it deliberately.

Two further decisions:

- **A class absent from the reference is reported, not hidden**, and is
  **excluded from the macro averages**. A class that does not occur cannot be
  got right or wrong; scoring it 0 would move the average for a reason
  unrelated to performance, and scoring it 1 would flatter the model.
- **Ignored pixels are counted.** Unlabelled, cloudy and out-of-range pixels
  are excluded and reported, never folded into a class they do not belong to.

### 6.4 Water-versus-shadow is pulled out on its own

Section 7.5 requires this confusion to be reported explicitly, and
`water_shadow_confusion()` extracts that 2×2 block and reports it in both
directions, as counts and as rates.

The reason is demonstrated by a test rather than argued. In a scene where
**every single shadow pixel is called water** — a total failure of the one
distinction this project exists to make — the summary numbers stay middling
rather than alarming:

| Quantity | Value |
|---|---|
| Shadow pixels called water | **100%** |
| Terrain-shadow IoU | **0.00** |
| Macro IoU | 0.50 |
| Overall accuracy | **0.90** |

A reader glancing at the macro average, still more at the accuracy, would not
see the failure. The explicit pair does.

### 6.5 The comparison is per class

`compare()` returns the two models' metrics **class by class**, not as a
single headline. The difference between them is expected in the small classes
— water and shadow — which a macro average flattens by construction.

### 6.6 What is *not* done

- **No training data.** No labelling has been carried out; `docs/labelling.md`
  is a specification, and the public-dataset mappings (Sen1Floods11,
  Landslide4Sense) are explicitly deferred until the real data is inspected.
- **No training script or Colab notebook yet.** `models/train.py`,
  `models/dataset.py`, `models/predict.py` and `notebooks/colab_train.ipynb`
  remain to be written. They are useful only once labels exist.
- **No geographic split implementation.** The rule is documented (no random
  pixel or patch splits); the code is not written.
- **No model has been trained, so the required comparison does not exist.**
  Everything in 6.1–6.5 is machinery awaiting data.
- PyTorch here is **CPU-only** (2.14.1+cpu). That is correct for local
  shape and gradient tests; training belongs on Colab, per the brief.

## Phase 7 — River blockage detection

**Status: module complete and unit-tested; the real-data gate is not yet run.**
The gate ("candidate found at a confirmed validation event") needs imagery of
one of the events confirmed in `validation.md` §2. What *has* been checked
against real data is the negative control, which is the more important half —
see §7.4.

### 7.1 The conjunction is the module

Brief, Section 7.6: a candidate is created when a new landslide polygon
intersects or comes within a configurable distance of the stream network
**and** there is evidence of obstruction — channel narrowing, loss of
downstream water continuity, and/or new upstream water.

A landslide beside a river is a landslide beside a river. It is not a dam.
Nepal's steep valleys put failures next to channels constantly, so proximity
is abundant and nearly always means nothing; a detector that fired on
proximity would produce a stream of false dams and be switched off within a
week.

`min_evidence_types` is therefore floored at 1 by the schema — the conjunction
cannot be disabled through configuration — and a test asserts that a landslide
placed directly across a channel produces **no candidate** when the river
flows exactly as before.

The module also never asserts that a dam has formed. The type is "Potential
Landslide Dam", the score is a confidence in the *evidence*, and every
candidate lists the factors behind it.

### 7.2 Upstream and downstream without a channel graph

Obstruction evidence is directional: water gained *above* a blockage, lost
*below* it. Direction comes from the Phase 2 D8 flow accumulation, which rises
monotonically downstream — so stream pixels near the blockage with lower
accumulation are upstream and those with higher accumulation are downstream.

This avoids building and traversing a channel graph, and it degrades
honestly: without flow accumulation the two directional signals are reported
**absent with a reason**, not guessed. A test reverses the accumulation raster
and confirms the upstream signal switches off, proving the direction is read
from the data rather than from an assumption about which way the grid runs.

### 7.3 Finding: the narrowing test can be defeated by its own search radius

The channel-narrowing signal compares water in a zone around the blockage
before and after. The first implementation used a 100 m zone, and every
narrowing test failed on a scene where a dam had plainly formed.

The cause: the zone grows in **all** directions, so a generous radius reaches
back into the water impounded upstream. The test then counts *more* water
after the blockage than before and reports no narrowing — at the exact moment
a dam exists. The signal inverts precisely when it matters.

`channel_zone_m` is now 30 m by default and documented as the cross-section
examined at the blockage, which must stay well inside `evidence_search_m`.
The config comment records the trap so the value is not "tidied" upward later.

### 7.4 Negative controls on real data

Run over the real Tsho Rolpa stack, using the Phase 2 stream network
(24,037 px) and D8 accumulation:

| Scenario | Candidates |
|---|---|
| No landslides — the true state of this AOI | **0** |
| A synthetic 144-pixel landslide placed directly on the real channel, river unchanged | **0** |

The second is required system test 4 on real terrain: a landslide sitting on
a river, with no obstruction evidence, is not a dam.

A negative control is weaker evidence than a positive detection, and no
positive detection on real imagery has been made. But a false-positive rate of
zero on a real 50 km² valley is the result that would have been easiest to get
wrong, and it is the one a monitoring system is judged on in normal operation —
most days, at most sites, the correct answer is "nothing here".

### 7.5 Confidence, and what it is not

Confidence is the weighted sum of present factors over the **total** weight,
proximity included. Because proximity carries 1.0 of 8.0, a candidate resting
on the precondition alone could never approach 1.0 even if the evidence floor
were removed.

The weights are convention — no published weighting exists for this
combination — and new upstream water carries the most because it is the most
direct evidence that flow is being held back rather than merely disturbed. As
in Phase 11, the defence is traceability: every candidate lists each factor's
measurement, threshold, verdict and contribution.

### 7.6 Implementation note: no scipy

Connected components and morphology are implemented in pure numpy
(`_components`, and `dilate_square` from Phase 2) rather than taken from
`scipy.ndimage`. scipy's compiled extensions are intermittently blocked on
this project's machine (`validation.md` §8), and a detector that cannot run is
worse than one that measures distance in whole pixels. The flood fill is
iterative, so a large component cannot exhaust the stack.

### 7.7 What is *not* claimed

- **No real blockage has been detected.** Only negative controls have been run
  on real data; the positive gate awaits imagery of a confirmed event.
- Distance to the stream is measured in **whole pixels** (10 m steps), a
  consequence of using dilation rather than a distance transform.
- The stream network is DEM-derived and is itself only accurate to a few
  pixels in steep terrain, which is why `max_distance_to_stream_m` defaults to
  50 m rather than demanding strict intersection.
- "New landslide" must come from Phase 5's change detection. Nothing here
  verifies that the supplied mask is new rather than a pre-existing scar, and
  a single-date classification passed in its place would silently produce
  candidates at old landslides.

### 7.8 Phase 7 on a real event — Baige, 2018

Run on the exact change map documented at the Phase 5 gate (the dam-tuned run,
2,652 px), with the stream network derived from the Baige DEM and water masks
from Phase 3. The published coordinate was **not** passed to the detector; it
is used only afterwards to measure where the candidates landed.

#### 7.9 Finding: Phase 7 bypassed Phase 5's own minimum area

The first run produced **153 candidates for one dam**. Of those, **76 were a
single 10 m pixel** and 18 scored confidence 1.000.

The cause is a seam between two phases. Phase 5 applies
`polygons.min_area_m2` (1,000 m²) to its *polygons*, but Phase 7 consumes the
raw boolean change mask, so every fragment Phase 5 would itself have discarded
reached the blockage logic. And because the obstruction evidence is measured
over a 500 m reach rather than per-polygon, a one-pixel speck beside a blocked
river **inherits the real dam's evidence** — new upstream water, downstream
loss, channel narrowing — and scores full confidence on it.

`detection.blockage.min_landslide_area_m2` closes it, defaulting to Phase 5's
own floor: anything smaller is below the system's threshold for calling
something a landslide at all. A deployment should raise it toward the channel
width, since a deposit must span the river to dam it. With the default the run
gives **14 candidates**.

The general lesson is that a filter applied to one phase's *reported* output is
not applied to the array the next phase reads. Each phase has to enforce its
own preconditions.

#### 7.10 The result

14 candidates. Classifying them by DEM elevation at the centroid (in the
channel = within 40 m of the pre-event water surface, 2,870 m) and by whether
water was impounded:

| | candidates | reading |
|---|---|---|
| in channel, new upstream water | **3** (ND-005, ND-004, ND-007) | dam-like |
| in channel, nothing impounded | 6 | drained reach downstream |
| off channel | 5 | hillside debris |

**ND-005 is the detection.** Confidence 1.000, centroid at **2,871 m — the
pre-event water surface to within 1 m**, 770 m from the published source area
(which is itself 626 m from the channel, so this is the right distance), and
all four evidence types present: channel narrowing 42 → 0 water px, downstream
water loss 16,100 m², new upstream water 24,400 m².

#### 7.11 Finding: the confidence score ranks a drained reach above a real dam

The six drained-reach candidates all score **0.625**. ND-004, which is
genuinely in the channel with water impounded behind it, scores **0.500**.

The arithmetic is plain. A drained reach collects `intersects_stream` (1.0) +
`channel_narrowing` (2.0) + `downstream_water_loss` (2.0) = 5 of 8. A dam
showing only impoundment collects `intersects_stream` (1.0) +
`new_upstream_water` (3.0) = 4 of 8. So two signals that a *blockage has
already drained* outrank the one signal that water is being *held back now*.

This is not a weighting that can be nudged. `new_upstream_water` is the only
factor that distinguishes a forming dam from a drained channel, and summing it
with factors that a drained channel also satisfies dilutes exactly the
information that matters. The brief's Section 7.6 wording is "and/or", so
requiring upstream water would change the stated semantics, and that is not a
change to make unilaterally — it is recorded as an open item.

What the run shows is that **the factor list, not the score, carries the
discriminating information** — which is the reason the brief requires every
candidate to publish its factors. The score alone is misleading here.

#### 7.12 What is *not* claimed, after the real run

- **No ground truth.** No reference dam outline exists, so there is no
  precision or recall. ND-005's agreement is a distance and an elevation, not
  an accuracy.
- **14 candidates for one event is still over-detection.** Nine of the eleven
  non-dam-like candidates are explainable (drained reach, hillside debris),
  but the system reports them as `Potential Landslide Dam` without
  distinguishing them. The elevation and upstream-water test that separates
  them in this write-up is **analysis, not code**.
- **One event, one date pair.** Tibet, not Nepal.


#### 7.13 Correction: the in-channel test used the wrong elevation

§7.10 classified ND-001 as "off channel" because its *landslide polygon's
centroid* sits 78 m above the river. Phase 8 (§8.9) then showed ND-001 is the
main-stem candidate holding the impoundment: the stream pixels it actually
touches lie at 2,906–2,915 m, and carry 332,506 cells of accumulation. The
centroid of a landslide on a valley side is on the valley side by
construction; whether the *blockage* is in the channel is a property of the
site pixels, not of the deposit's middle.

So the "3 dam-like" count in §7.10 is wrong in its membership. The method
that produced it — elevation at the polygon centroid — should not be reused.
The candidate list itself is unchanged; only this write-up's reading of it.

#### 7.14 Merging candidates along a reach

One landslide dam is routinely detected as several components: §5.9's slope
gate carves the channel-crossing part out of a deposit lying on a flat valley
floor, and cloud and snow fragment it further. Because the obstruction
evidence is measured over a **reach**, every fragment sees the same impounded
water and reports it as independent confirmation.

On Baige this produced seven candidates in two groups, claiming
116,800–154,800 m² of gained water upstream — the same water, counted seven
times — so ranking by impounded water chose an arbitrary fragment, and the
drainage and water evidence appeared to disagree.

`merge_along_stream_m` groups components obstructing the same reach, measuring
distance **along the stream network** so opposite banks of a gorge group while
separate tributaries do not. It defaults to `evidence_search_m`: two blockages
closer than the radius over which evidence is gathered cannot be told apart by
that evidence. Zero does not disable it — components reaching the same stream
pixels are one obstruction regardless, which is the slope-gate case.

Effect on Baige: **32 candidates become 2**, the survivor carries 333,301 of
the AOI's 334,834 maximum drainage cells, and the main-stem disagreement
resolves. The consequences for the warning level are in `docs/validation.md`
§26, and they are large.

## Phase 8 — Barrier lake detection and tracking

**Status: module complete and unit-tested; the real-data gate is not yet run.**
The gate ("lake upstream of the candidate identified and tracked") needs
imagery of a confirmed event, which needs Earth Engine access.

Brief, Section 7.7: a water body **upstream** of a blockage candidate, on the
same stream, that is **new or expanding** relative to the pre-event baseline;
tracked through time with stable IDs, handling merging, splitting and
disappearance.

### 8.1 Finding: a barrier lake is connected to the river it dams

The first implementation asked whether a *water body* lay upstream of the
blockage. Every test of that rule passed except the ones that mattered: a lake
placed plainly **downstream** was still reported as a barrier lake.

The reason is structural, not a coding slip. A barrier lake is joined to the
river it impounds, and in a water mask that river continues through and past
the blockage. The lake and the whole channel are therefore **one connected
component**, spanning both sides of the dam. Asking "is this component
upstream?" has no useful answer — it is both.

What distinguishes a barrier lake is not where the water *is* but **where the
water arrived**. The rule is now: the new water (post minus pre) within the
upstream region must exceed the threshold *and* exceed the new water gained
downstream. Area and baseline are then measured over the impounded reach
alone, so the reported lake is the water held back rather than the entire
river.

A test reverses the flow-accumulation raster and confirms the same scene stops
qualifying, proving the judgement rests on measured flow direction rather than
on which way the grid happens to run.

### 8.2 Finding: two wide zones cancel each other

Impounded water fills a valley floor, so the upstream region has to extend
well beyond the channel — `lake_width_m`, 300 m by default. The obvious
implementation dilates the upstream and downstream channel pixels separately
by that width and subtracts one from the other.

That fails, and fails silently. Two 300 m dilations of channel reaches either
side of a blockage **overlap heavily around the blockage itself**, so
`upstream & ~downstream` erases most of the upstream region — including the
impoundment immediately behind the dam, which is exactly where the water is.
In testing this turned every positive case negative.

`_partition_by_proximity` grows both regions **together**, one pixel per step,
so each pixel joins whichever side of the blockage is nearer and pixels
reached by both in the same step join neither. The result is a genuine
partition: disjoint by construction, with a contested midline. Four tests pin
its behaviour directly.

### 8.3 A lake that cannot be seen has not disappeared

This is the module's central rule and the reason its defaults are cautious.

A barrier lake vanishing between two scenes is the most alarming signal this
system can produce — it reads as *the dam has breached*. Cloud over the lake
produces precisely that appearance, and cloud over a Himalayan valley is the
normal condition for much of the year.

So an unmatched lake is only reported as **disappeared** when at least
`min_observable_fraction` (50%) of its last known footprint was observable on
the new date. Below that it is `not_observed`: it keeps its identity, its
series records a gap, and it can be picked up again later as the same lake.
Where no observability mask is supplied at all, the module takes the cautious
reading and reports `not_observed` rather than assuming the lake is gone.

This is the distinction Phase 9 draws between a gap and a measurement, applied
where getting it wrong is most costly. A `not_observed` date enters the area
series as `None`, which `analysis.change` treats as a gap and never
interpolates.

### 8.4 Identity through merging and splitting

Lakes are matched between dates by overlap, as a fraction of the smaller mask
(`match_min_overlap_fraction`, 0.30).

- **Continuation** — one previous lake, one current lake: the identity carries
  over.
- **Merge** — several previous lakes, one current lake: the survivor keeps the
  identity of the **largest** contributor and records what it absorbed; the
  absorbed lakes are deactivated.
- **Split** — one previous lake, several current lakes: the **largest**
  fragment keeps the identity and the others become new lakes recording their
  parent.

Identity follows mass in both directions. That is the only choice that keeps a
growing impoundment's history intact when its rising shoreline swallows a
neighbouring pond — the alternative, assigning identity by order or by first
match, would silently transfer a long area series onto a small pond and
restart the lake that actually matters.

### 8.5 What is *not* claimed

- **No real barrier lake has been detected or tracked.** Everything here is
  tested on hand-built scenes. The gate awaits imagery.
- Upstream is derived from D8 flow accumulation. Without it the module returns
  **nothing** rather than guessing — a lake downstream of a blockage is not a
  barrier lake, and the error would be unsafe in the reassuring direction.
- `lake_width_m` bounds how far impounded water may spread from the channel. A
  lake wider than this would be truncated, and the configured 300 m is a
  convention for the valley scales this prototype works at.
- The tracker matches by **overlap only**. Two lakes that swap positions
  entirely between dates, or a lake that moves further than its own width,
  would not be matched. At the cadence Sentinel provides this is not a
  realistic failure, but it is an assumption rather than a guarantee.

### 8.6 Phase 8 on a real event — Baige, 2018

Run off the Phase 7 output, using each candidate's own blockage site, and
tracked across all four Sentinel-2 dates on disk (2018-11-02, 11-09, 11-19,
11-22).

**A first run was published and then withdrawn.** It reported a 160,000 m²
lake behind ND-007, an identity that churned through eight lake IDs in four
dates, and a 150× sensitivity to `upstream_search_m`. All three were artefacts
of the defect in §8.7. They are kept in the history of this document only as
this note; none of those numbers should be quoted.

### 8.7 Finding: "upstream" was not "on the same stream"

Section 7.7 defines a barrier lake as upstream of the candidate **on the same
stream**. The module honoured only the first half. It took every stream pixel
inside a square box of side 2 × `upstream_search_m` whose flow accumulation was
below the site's, and called that the upstream reach. In a 4 km box around a
main-stem blockage, every small tributary has a low accumulation value, so the
"upstream" zone was a web of unrelated tributaries — and which of them held
water changed from date to date.

Measured on Baige: the reach reported as impounded spanned rows 154–289 on
2018-11-09 and rows 424–598 on 2018-11-19 — a different part of the valley.
The two dates' lakes overlapped by **exactly 0 pixels** while 40% of the water
persisted, so no lake could keep an identity.

The fix, `_trace_along_stream`, grows the reach outward from the blockage one
pixel at a time, staying on stream pixels on the correct side of the site's
accumulation. A tributary that does not connect to the blockage through such
pixels is never reached, and `upstream_search_m` now bounds distance **along
the channel** rather than a box radius.

### 8.8 Finding: the median of a blockage that straddles a confluence

The upstream reference was the **median** accumulation over the blockage site.
Landslides commonly dam a main stem just below a tributary mouth, so the site
spans both. The ND-007 site ran from 20,817 to 56,484 cells; its median of
20,856 was set by the tributary pixels and put the main stem — carrying the
impoundment — on the *downstream* side. With tracing alone, every water
component was then rejected as "growth not upstream".

The reference is now the site's **maximum**: accumulation rises monotonically
downstream, so the blockage's maximum marks its outlet, and everything above
the obstruction lies below it on every contributing branch. The maximum is
safe only because of §8.7 — a parallel tributary that joins *below* the
blockage also has a lower value, but cannot be reached by walking upstream
from the site.

Five tests pin the two fixes: water on a stream that does not reach the
blockage is not reported as impounded; the real impoundment is still found;
and a blockage spanning a confluence still finds the main-stem lake.

### 8.9 The corrected result

With the reaches traced, the candidate that impounds the water is **ND-001**,
not ND-007:

| candidate | site accumulation (max) | gained water in its upstream reach | lake |
|---|---|---|---|
| **ND-001** | **332,506** | **215,400 m²** | **602,200 m²** |
| ND-004 | 174,278 | 227,200 m² | 369,900 m² |
| ND-005 | 135,855 | 57,600 m² | 42,200 m² |
| ND-007 | 56,484 | 400 m² | none |

ND-001's site carries 332,506 cells against the AOI's main-stem maximum of
334,834: it is on the Jinsha itself. ND-004 shares much of the same reach,
which is why its gained-water figure overlaps ND-001's — the two are not
independent detections, and Phase 7 open item 1 (merging candidates along a
reach) applies directly.

The lake behind ND-001 on 2018-11-09: **602,200 m²**, baseline 386,800 m²,
**215,400 m² new, +55.7%**, DEM median 2,887 m over the lake.

**Tracking now holds one identity across four dates:**

| date | observable | lake BL-001 |
|---|---|---|
| 2018-11-02 | 100.0% | — (pre-event) |
| 2018-11-09 | 59.8% | 602,200 m² (appeared) |
| 2018-11-19 | 60.9% | 421,900 m² (continued) |
| 2018-11-22 | 100.0% | 431,500 m² (continued) |

**One lake ID instead of eight.** The fall after 11-09 was checked against
cloud before reading anything into it: the 11-09 footprint is 100% observable
on both later dates, and about 30% of it is dry (69.5% wet on 11-19, 70.9% on
11-22). The decrease is therefore measured, not a gap. It is *consistent with*
the engineered discharge channel the sources date to 2018-11-13 (validation
§2.2), which falls between those dates — but no independent evidence here
ties the two, and it is not claimed as a detection of the discharge.

**Search-radius sensitivity, re-derived:** 500 m → 260,700 m²;
1,000 m → 361,700 m²; 2,000 m → 602,200 m²; 3,000 m → 771,800 m²; 5,000 m →
771,800 m². A **3×** range, against the 150× the defect produced, and the
growth with distance is the shape a lake backing up a valley should have. The
largest lake now touches the AOI edge (40 px), so the area is truncated by the
3 km AOI and is a **lower bound**.

### 8.10 What is *not* claimed, after the real run

- **No lake area is validated.** There is no reference outline, the AOI cuts
  the lake off, and the figure still depends on `upstream_search_m`. No
  comparison with the published 105–775 × 10⁶ m³ is possible or attempted.
- **The discharge is not detected**, only a fall in area consistent with it.
- **`lake_width_m` can still reach parallel tributaries.** The zone is grown
  300 m either side of the traced channel, so water on a tributary closer than
  that can still be swept in. Narrower than the box it replaced, not immune.
- **Two candidates share one reach** (ND-001, ND-004) and are reported
  separately.
- **One event, four dates, Tibet.**

## Phase 9 — Temporal change

Brief, Section 7.8: a time series of lake area with absolute change, percent
change and rate of change; a trend of Increasing / Decreasing / Stable /
Unknown with configurable thresholds and a minimum number of valid
observations; and **cloudy or missing dates recorded as gaps, never
interpolated**.

### 9.1 Citation register

| Quantity | Source |
|---|---|
| Robust slope: the median of all pairwise slopes | Sen, P. K. (1968). "Estimates of the regression coefficient based on Kendall's tau." *JASA* **63**(324), 1379–1389. Usually called Theil–Sen, after Theil (1950) and Sen (1968) |

Everything else in this phase — the stable band, the minimum observation
count, the staleness limit — is convention, marked as such in `config.yaml`,
and should be tuned per site.

### 9.2 A gap is recorded, never filled

An observation that could not be made is carried through the series as a
**gap**: it keeps its date and its reason, is counted, and is reported — but it
never contributes a value to the fit. `AreaObservation` refuses to be
constructed as valid without an area, so a gap cannot be created by accident.

Interpolating across a gap would manufacture a measurement on a date nobody
looked at, and the fabricated point would sit precisely where a reader most
wants evidence. The test that pins this compares a clean series against the
same series with a gap row inserted: the rate, the endpoints and the valid
count must all be identical, because the gap carries no measurement.

### 9.3 Too little data is Unknown, never Stable

`Unknown` is returned, with a reason, when:

- there are fewer than `min_valid_observations` valid observations (3 by
  default — two points can always be joined by a line);
- every valid observation falls on one date, so there is no time span;
- the latest valid observation is older than `max_age_days` (60 by default).
  A month-old "Stable" is not a current assessment, and reporting it as one
  would be the temporal form of the false reassurance that shaped §11.3.

An `Unknown` result carries **no** rate, absolute change or percent change —
all `None`, never zero — so it cannot be passed downstream as "no growth". A
test asserts that an `Unknown` trend leaves Phase 11's `lake_growth_rate`
factor *unavailable* rather than scoring it as benign.

Percent change is `None` when the first area was zero, since a percentage of
nothing is undefined; the absolute change is still reported.

### 9.4 Finding: two real dates would have reported a dramatic, false decline

Both Sentinel-2 dates held for Tsho Rolpa were processed through the Phase 3
optical rule:

| Date | Largest water body | Unusable pixels |
|---|---|---|
| 2023-10-19 | 1.6005 km² | 7.00% |
| 2023-10-24 | 1.2977 km² | 13.11% |

That is **−302,800 m², a 19% loss in five days**. For a glacial lake, that is
not physically plausible, and the system reports **Unknown** — three valid
observations are required and only two exist.

Had `min_valid_observations` been 2, the series would have produced
"Decreasing" at roughly −60,000 m²/day. Fed into Phase 11, a rate that size
saturates the growth factor outright. The guard is not a formality; it stopped
a confident, wrong answer on the only real series this project currently has.

**Where the missing area actually went**, pixel by pixel:

| Fate of the "lost" water pixels | Share |
|---|---|
| Unobservable on date 2 (cloud, cloud shadow, defective) | **50.1%** |
| Observable but not classified as water | 49.9% |

and the largest SCL class among the second group is **class 2, "dark area
pixels"** (4206 of 9440 lost pixels) — which §2.5 established is dominated by
*terrain shadow* in this terrain, not by cloud.

So the apparent drainage is half obscuration and substantially half shadow.
Two consequences:

1. **A time series must be built from the Phase 4 fused mask, not the Phase 3
   optical rule.** The areas above use the Phase 3 mask, which is deliberately
   shadow-naive. Shadow-driven shoreline loss moving between dates is exactly
   what Phase 4 exists to suppress, and a fused series should be materially
   more stable. The per-date fusion needs each date's own sun angles, so this
   is work for when the series is built for real.
2. **Cloud fraction must travel with every area.** A 13% cloudy scene can lose
   a fifth of a lake without any gap being declared, because the scene passed
   the scene-level filter. `AreaObservation` carries `cloud_fraction` for this
   reason, and a sharp area change against a rising cloud fraction should be
   treated as suspect rather than as signal.

### 9.5 Why the trend threshold is relative by default

An absolute threshold in m²/day means entirely different things for a
0.01 km² pond and a 1.6 km² lake, and the AOI is user-defined. The default
`trend_metric: relative` scales the stable band by the mean area
(0.001/day — roughly 3% a month). The rate in m²/day is reported either way,
since the brief asks for it specifically.

A test demonstrates the difference: the same 1000 m²/day is `Increasing` for a
10,000 m² pond and `Stable` for a 5 km² lake.

### 9.6 Why the slope is Theil–Sen

The default rate is the median of the slopes between every pair of valid
observations (Sen 1968), not a least-squares fit or an endpoint difference.
A single mis-segmented date — a cloud edge counted as water, a shadowed shore
lost — moves a median far less than it moves either alternative. §9.4 shows
that is not hypothetical here.

The test makes it concrete: corrupting the final point of a clean series
leaves the Theil–Sen slope near its true value of 2.0 while the endpoint
slope becomes 178.0.

No significance test (Mann–Kendall or otherwise) is applied. With three to
five observations such a test is badly underpowered, and reporting a p-value
from it would lend the trend an authority the sample size does not support.

### 9.7 An integration note on thin evidence

Running Phase 9's output into Phase 11 surfaced a behaviour worth recording:
when only one factor is available, the renormalised score **equals that
factor's score**, so a single steep-slope input can produce `HIGH RISK
INDICATORS` at 9% data coverage. The assessment is correctly flagged
`insufficient_data`, and the escalation is deliberately *not* suppressed —
muting an alarm is the worse failure (§11.3). But a level driven by one factor
is a weak statement, and the coverage figure beside it is the thing to read.

### 9.8 What is *not* claimed

- **No real trend has been measured.** The only real series available is two
  dates, which correctly yields `Unknown`. Everything about the trend
  classification is tested on hand-built series.
- The stable band, minimum count and staleness limit are **convention**.
- Phase 9 does not acquire imagery. Building a genuine series needs Earth
  Engine access and a date range, and — per §9.4 — the Phase 4 fused mask
  rather than the Phase 3 optical one.

### 9.9 Phase 9 on a real lake — BL-001, Baige 2018

The first trend measured on real imagery. It was only possible once Phase 8
held a stable identity (§8.7–8.8); before that the lake was a different object
on every date.

#### 9.10 A partial measurement is not a smaller lake

Two of the four dates are substantially clouded. If a date on which cloud hid
part of the valley is compared with a clear one, the difference in *visibility*
becomes a difference in *area*, and the module manufactures a trend out of
weather.

So each date is first tested for whether the lake's possible extent was
observable. That extent is the traced upstream zone (§8.7) restricted to
ground low enough to be flooded — at or below 3,601 m, the highest water seen
anywhere in the zone on any date. Hillside above that cannot be lake, so cloud
over it says nothing. The resulting floodable zone is 49,133 px of the
56,385 px zone, and a date counts only if at least
`barrier_lake.min_observable_fraction` of it is visible.

| date | floodable zone observable | lake | status |
|---|---|---|---|
| 2018-11-02 | 100.0% | — | pre-event (dam formed 11-03) |
| 2018-11-09 | 65.2% | 602,200 m² | measurement, **lower bound** |
| 2018-11-19 | 69.2% | 421,900 m² | measurement, **lower bound** |
| 2018-11-22 | 100.0% | 431,500 m² | measurement |

#### 9.11 The result, and why the bias runs the safe way

**Decreasing: −170,700 m² (−28.3%) over 13 days, −13,131 m²/day** by
Theil–Sen, from 3 valid observations and 0 gaps. That rate is 27× the
configured stability band.

Two of the three dates are lower bounds, which would normally make a trend
suspect. Here it does not weaken the conclusion, because of the direction. The
first date, 602,200 m², is the understated one (35% of the zone unseen) and
the last, 431,500 m², is complete. A larger true value at the start makes the
decline **larger**, never smaller. So −170,700 m² is a conservative bound on
the fall.

The series is not monotone, and with three points Theil–Sen's median is simply
the middle of three pairwise slopes:

| pair | slope |
|---|---|
| 11-09 → 11-19 | −18,030 m²/day |
| 11-09 → 11-22 | **−13,131 m²/day** (the median) |
| 11-19 → 11-22 | **+3,200 m²/day** |

Three valid observations is exactly `min_valid_observations`, so this is the
shortest series the module will accept, and a median of three slopes is barely
robust. The steepest decline spans 2018-11-13, the date sources give for the
engineered discharge channel (validation §2.2) — consistent, but a single
coincident interval is not evidence, and no detection of the discharge is
claimed.

## Phase 10 — Depth and volume

Brief, Section 8, which is the strictest part of the specification: depth is
**never** estimated from image colour, every value is traceable to exactly one
branch, the branch is stored beside the value, and anything not traceable to a
branch is returned as `unavailable` with a reason rather than as a number.

### 10.1 The three branches, as implemented

| Branch | Condition | Output |
|---|---|---|
| **A** | the lake formed *after* the DEM was acquired, so the DEM shows the pre-lake valley floor | `depth = WSE − DEM` per pixel, clipped at 0; `volume = Σ(depth × pixel area)`; `value_type = estimated`, with uncertainty bounds |
| **B** | the lake already existed, so the DEM recorded the **water surface** | `unavailable`, reason *DEM records water surface; no bathymetry* |
| **C** | insufficient data — no reliable shoreline, an unusable observation, or evidence that cannot settle A vs B | `unavailable`, with the specific reason |

For branches B and C every numeric depth and volume field is `None`, never
`0.0`. A test asserts this by identity, because a zero volume would read as
"the lake holds no water" — a measurement — rather than "we do not know".

### 10.2 Finding: the branch cannot be decided from dates alone

The obvious implementation compares the lake's first observation against the
DEM epoch. That is necessary but **not sufficient**, and at this project's own
default site it gives the wrong answer.

Tsho Rolpa was first observed *by this project* in the 2023 imagery, long after
the GLO-30 epoch (2011-01-05 to 2014-09-08, measured in
`data/raw/dem/dem_epoch.json`). A date-only rule therefore selects Branch A and
produces a volume. But the lake has existed for decades: the DEM recorded its
*surface*, and its bed is unknown. The date comparison was answering "when did
we first look?" rather than "did the lake exist when the DEM was made?".

So the DEM is tested **directly**, and that evidence outranks the dates. Two
signatures of a recorded water surface, both measured over Tsho Rolpa:

1. **Flatness.** Copernicus GLO-30 flattens water bodies to a constant
   elevation. The DEM inside the lake is **4545.5 m with a standard deviation
   of 0.00 m across all 15 501 pixels** — bit-identical. No valley floor is
   ever that flat.
2. **A zero height-error mask.** The GLO-30 HEM band is **0.00 m everywhere
   inside** the lake. That is not a claim of perfect accuracy; it means no
   measurement was made there, which is itself evidence for Branch B.

A third test, the overlap with the DEM product's own water-body mask, is also
available and is checked.

`tests/test_depth_volume.py` pins the specific failure: a test asserts that
`lake_postdates_dem` is `True` for Tsho Rolpa *and* that the chosen branch is
still B.

### 10.3 Finding: on a Branch B lake, the Branch A formula is buffer-dependent

This is the concrete harm the branch rule prevents, measured rather than
asserted. Applying the Branch A arithmetic to Tsho Rolpa — where it must not be
applied — gives:

| Shoreline ring | WSE (median) | Shoreline IQR | Implied mean depth | Implied volume |
|---|---|---|---|---|
| 10 m | 4554.69 m | 10.19 m | 9.19 m | **14.3 × 10⁶ m³** |
| 30 m | 4559.50 m | 14.67 m | 14.00 m | **21.7 × 10⁶ m³** |
| 50 m | 4565.42 m | 23.48 m | 19.92 m | **30.9 × 10⁶ m³** |

The volume varies by a factor of **2.2** on nothing but the choice of ring
width, and every one of those numbers looks entirely plausible for a lake of
this size. None is traceable to a measurement of the bed, because no
measurement of the bed exists. This is exactly what Section 8 is written to
stop, and the system emits none of them.

The same table also shows why the shoreline buffer is narrow by default
(10 m, one pixel): on a steep shoreline the median of the ring is biased
**upward**, because every sample in the ring sits upslope of the waterline,
and the bias grows with ring width (+10.7 m from 10 m to 50 m here). The brief
prescribes the median, so the median is the default; `p25` and `min` are
offered for sensitivity testing rather than substituted silently.

### 10.4 Water surface elevation and its uncertainty

As Section 8 requires: the WSE is the median DEM elevation in a ring just
outside the water polygon, and its spread is stored as the uncertainty
(interquartile range by default; `std` and `mad` are selectable). Fewer than
`min_samples` valid shoreline samples is Branch C, not a WSE computed from
whatever is available.

**Branch A uncertainty bounds** combine the two error sources the brief names:

- `volume_low` = Σ clip((WSE − spread) − (DEM + error), 0)
- `volume_high` = Σ clip((WSE + spread) − (DEM − error), 0)

Both terms are pushed the same way in each bound, so this is a **conservative
envelope, not a statistical confidence interval**, and it is described as such.
The DEM error is the GLO-30 HEM band by default — the product's own per-pixel
estimate — or a configured constant.

### 10.5 Branch B empirical volume: refused, not implemented

The brief permits an empirical area–volume relationship for Branch B **only
with approval and a cited formula**, reported as `empirical` with wide
uncertainty bounds. No formula has been approved for this project.

`branch_b_empirical_formula` therefore exists in the configuration but raises
`NotImplementedError` when set to anything, naming what would be required. A
flag that fails loudly is better than an absent one: it puts the decision point
where someone would look for it, instead of leaving a silent gap that invites a
quietly added formula later.

### 10.6 Gate status and what is *not* claimed

**Required system test 8 passes on real data.** Tsho Rolpa returns Branch B
with `unavailable`, and the test asserts that no depth or volume number is
produced.

- **Branch A has not been exercised on real imagery.** Its arithmetic is
  verified against hand-computable synthetic valleys, but no real lake that
  postdates the GLO-30 epoch has been processed. The confirmed Rasuwa 2026
  event is expected to be the first genuine Branch A case, and that awaits
  Earth Engine access.
- **No cross-check against ICESat-2 ATL13 or SWOT has been done.** Section 5
  marks it optional and it needs a NASA Earthdata login. Until then the WSE
  rests on the DEM alone, which is the same surface Branch B distrusts — so
  for Branch A lakes an independent WSE would materially strengthen the
  result.
- **A Branch A volume is `estimated`, never `observed`.** The distinction is
  enforced by the `value_type` field and asserted in the tests.
- The flatness threshold (0.5 m) is calibrated against *this DEM product's*
  behaviour. A DEM that does not flatten water, or one resampled before it
  reaches this module, would need it revisited.

### 10.9 Phase 10 on a real lake — BL-001, Baige 2018, and why its numbers are withheld

The first real test of Branch A. The DEM epoch ends 2014-09-11 and the lake
formed 2018-11-03, so the dates say Branch A, and the shipped logic agrees:

| | value |
|---|---|
| branch | **A** (`estimated`) |
| mean depth | 57.34 m |
| max depth | 145.90 m |
| volume | 34.5 × 10⁶ m³ |
| DEM sd inside the lake | 32.50 m (not flat, so no Branch B signal) |
| GLO-30 water mask over the lake | 2.0% (below the 50% Branch B trigger) |

**These numbers are not reported as a result.** Three reasons, in order of
severity.

#### 10.10 A single water-surface elevation does not describe an impounded reach

The WSE from the shoreline ring is **2946.33 m with a spread of ±24.61 m**
over 734 samples. A water surface is level by definition, so a ±24.61 m spread
is not uncertainty about a level surface — it is evidence that the thing being
measured is not one.

Two causes compound. The reach is long, so its pre-dam floor drops
continuously along it, and the shoreline ring samples ground at every elevation
the valley passes through. And this module's own docstring already records that
the prescribed median is **biased upward on a steep shoreline**, because every
ring sample sits upslope of the waterline; in a gorge with 40°+ walls that bias
is tens of metres, not metres. A WSE 76 m above the pre-dam river surface
(2,870 m) then propagates into every depth.

Section 8 prescribes "the median DEM elevation along the lake shoreline". That
is followed exactly. The finding is that the prescription is sound for a
compact lake in a basin and breaks down for a long impoundment in a steep
valley, which is the case this project exists for.

#### 10.11 Finding: the lake is half Branch A and half Branch B, and the branch is per-lake

Of the lake's 602,200 m², **386,800 m² (64%) was the Jinsha itself** before the
dam — ground the DEM recorded as a *water surface*, whose bed is unknown
(Branch B) — and only **215,400 m² is newly flooded**, where the DEM holds the
pre-lake surface and Branch A is valid.

Section 8's branches are per-lake, so the module must pick one, and it picks A
for all of it. On the 64% that was river, `WSE − DEM` measures the **rise in
water level**, not the depth; the water the river already held below its
2011–2014 surface is missing. The volume is therefore a lower bound on that
part and a true depth on the rest, summed together and labelled as one
`estimated` figure.

Applying Branch A to the newly flooded ground alone gives **6.34 × 10⁶ m³**,
which is traceable to Section 8 without reservation. It is not offered as the
lake's volume: the AOI truncates the lake (§22), and the pre-dam channel's own
contents remain unmeasurable.

#### 10.12 Finding: the height-error mask is collected and then ignored

`decide_branch` records `zero_height_error_fraction` as evidence and **no
decision rule ever reads it** (`analysis/depth_volume.py`). On this lake it is
**62.8%** — against the 64.2% of the lake that was pre-existing river. A GLO-30
height-error of exactly zero means no height was measured there, which over
water is the DEM telling us it recorded a surface rather than a bed.

So the product ships a **per-pixel** Branch A/B discriminator, it is already
being read into the evidence dictionary, and it is discarded. Using it would
address §10.11 directly, by splitting the lake rather than forcing one branch
over a mixed body. Implementing that changes the depth methodology, which
Section 2 reserves for approval, so it is recorded here and not done.

### 10.13 Finding: the Baige chain was run without the shadow-rejection fusion

Phases 5, 7, 8, 9 and 10 on Baige all took water from the Phase 3 rule-based
optical mask. **None used the Phase 4 fusion** — the project's core
contribution.

#### 10.13.1 A first comparison that was not like for like

The omission was first measured over the whole array, and reported that the
fusion inflated water from 0.8718 km² to 3.1041 km² with 80.4% of it more than
120 m above the river, up to 4,602 m — apparently summit snow. **That
comparison was invalid and its conclusion is withdrawn.**

**40.1% of this scene is optical nodata** at the scene edge. The Phase 3 mask
is empty there by construction, because `optical_water_mask` has nothing to
work with. The fusion is not: a pixel is `valid` where **any one** evidence
term applies, and over nodata the DEM-derived and SAR terms all still apply.
So the fusion fills the nodata region from SAR and slope, and subtracting an
empty mask from a filled one measures the nodata, not the fusion.

Measured properly: **88.9% of the pixels the fusion added are optically
unusable.** Of the added pixels, `water_index` and `nir` were available on only
11.1%, while `sar_backscatter`, `slope`, `illumination` and
`terrain_shadow_mask` were available on 100%. Their median NIR is 0.000 and
their median MNDWI is NaN — they are not snow being mistaken for water, they
are *nothing* being read as water. Only 1.6% of them are flagged by the
project's own snow screen.

#### 10.13.2 Finding: the fusion asserts water with no optical observation at all

That is the real defect. Over nodata the surviving evidence is SAR at
−14.4 dB (water-like, since the threshold is −8.65 dB) and a slope of 0.6°
(flat, so water-like), on flat high ground at a median 3,822 m. The result is
`p_water = 0.719` and a water verdict.

`FULLY_DETERMINATE_TERMS` includes `sar_backscatter`, so SAR alone is treated
as sufficient by design. But all three of Section 7.3's rules begin with "dark
**optical** pixel", and its third rule — SAR water-like inside the SAR
layover/shadow mask → *uncertain*, defer to optical — shows the intent that
SAR unsupported by optical evidence is not a verdict. **Section 7.3 has no rule
for "no optical observation at all", and the module's default fills that gap by
trusting SAR.** At 3,800 m, dry smooth snow and ice are also dark to SAR, so
there is no basis in the data for preferring water.

Changing when the fusion asserts water is a change to a reviewed phase's
semantics, which Section 2 reserves for approval, so it is **not changed
here**. Marking such pixels `uncertain` is the author's recommendation.

#### 10.13.3 What the fusion actually does, compared properly

Re-run over optically usable pixels only, with the snow screen applied as an
**invalid observation** rather than voted on — because MNDWI is identical to
NDSI, so no weighting of the index term can separate snow from water — and with
the four-date persistence term the first call omitted:

| date | optically usable | Phase 3 | Phase 4 | removed | added | net |
|---|---|---|---|---|---|---|
| 2018-11-02 | 99.8% | 8,045 px | 7,850 px | 807 | 612 | −195 |
| 2018-11-09 | 58.6% | 8,718 px | 7,663 px | 1,792 | 737 | −1,055 |

The removed pixels carry the signature the fusion exists to find: median slope
**33.8°** and **44.4°**, with 34.7% and 29.3% in terrain shadow. Water does not
sit on a 44° slope. This is the core contribution working on real imagery.

#### 10.13.4 And it does change the result

**The lake on fused water is 478,300 m², against 602,200 m² on unfused water —
20.6% smaller**, with 105,100 m² new rather than 215,400 m².

So the earlier statement that the omission "did not corrupt" §21–§23 was **too
strong and is withdrawn**. The *direction* of every finding holds — there is a
blockage, there is an impoundment behind it on the main stem, it is expanding
against the pre-event baseline, and it declines after 11-13 — but the
magnitudes move by about a fifth, and the depth and volume figures in §24,
already withheld, rest on the larger mask.

Every quantity reported for Baige in §21–§24 should therefore be read as
derived from the **unfused** Phase 3 mask, and as approximately 20% high on
lake area.

### 10.14 Finding: `cos_incidence` could not run at AOI scale, silently

`cos_incidence` built a three-channel normal array and used
`np.linalg.norm` with a matrix product. On this project's Windows machine that
product dies above roughly 300×300×3 — **no traceback, no message, exit code
0**. Every terrain-shadow and Phase 4 call at AOI scale was being killed
without a sign, which is how the omission in §10.13 went unnoticed.

It is now written elementwise. The two forms agree to 3.3 × 10⁻¹⁶, and the
elementwise one needs no BLAS and allocates no three-channel copy. It was the
only such call in the project's own code.

**Phase 4's gate result was re-checked against this**, because its 87.5%
false-water reduction was computed over a 799×797 grid, far above the failing
size. The stored illumination matches the fixed implementation to
**2.2 × 10⁻¹⁶**, and all three shadow masks agree on **100.0000% of 636,803
pixels**, so that run used a valid layer and its figures are unchanged. The
reason is the failure mode: the blocked call kills the process rather than
returning wrong numbers, so a run that completed cannot have hit it, and the
block is intermittent. See `docs/validation.md` §24, Finding 5a.

## Phase 11 — Risk indicators and warnings

Brief, Section 9: a transparent weighted score from lake growth rate, volume
(where available), new landslide activity, blockage confidence and slope, with
rainfall optional; all weights and thresholds in config; and **every warning
lists the factors behind it**.

### 11.1 These are indicators, not predictions

The brief's level wording is deliberately hedged and is reproduced exactly:

| | Level |
|---|---|
| 🟢 | NORMAL |
| 🟡 | MONITOR |
| 🟠 | HIGH RISK INDICATORS |
| 🔴 | CRITICAL INDICATORS — verification recommended |

A test asserts the four strings verbatim, and a second test asserts that no
level contains "will fail", "imminent", "failure expected" or "collapse". The
system never states that a dam will fail, or when.

Every assessment carries the mandatory disclaimer, taken from
`project.disclaimer`, which `config/schema.py` refuses to load without the
phrase "Not an official warning". A test checks the disclaimer is present even
on a NORMAL assessment, since that is the one most likely to be quoted
casually.

### 11.2 The rule that shaped the design: unavailable is not reassurance

Most factors will be missing much of the time. Volume is `unavailable` for
every Branch B lake (Section 8) — including this project's own default site.
Blockage confidence does not exist until a blockage is detected. Rainfall is
not wired in at all.

Scoring a missing factor as **zero** would make an unmeasured site look safe.
So an unavailable factor is excluded from **both** the numerator and the
denominator: the score is the weighted mean over what could actually be
measured, and a missing factor neither raises nor lowers it. The share of
total weight that was measurable is reported as `data_coverage`, and
`insufficient_data` is set below `min_data_coverage` (0.5 by default).

The test that pins this compares two assessments identical except that one has
volume **measured as 0** and the other has volume **unavailable**. The
unavailable case must score *higher*, because a measured zero is good news and
a missing measurement is not.

For a Branch B lake the reason travels with the gap, so the warning reads
*"lake_volume: unavailable (DEM records water surface; no bathymetry)"* rather
than merely omitting it.

### 11.3 Finding: the green circle was the dangerous part

An early version produced this for a site where only slope could be measured:

```
🟢 NORMAL
Indicator score: 0.10 of 1.00 (data coverage 9%)
INSUFFICIENT DATA: ...
```

The text is honest. The **symbol is not** — and a dashboard or a report
summary may render only the symbol. A green dot derived from 9% of the
evidence is exactly the false reassurance this module exists to avoid.

`RiskAssessment.symbol` therefore returns ⚪ instead of 🟢 when a **NORMAL**
level rests on insufficient data. The level *text* is unchanged, because the
brief fixes the four levels; only the visual cue is withheld.

The substitution applies **only to NORMAL**. Withholding the symbol on a HIGH
or CRITICAL level would mute a real alarm, which is the opposite and worse
mistake — a test asserts that a CRITICAL assessment built on thin evidence
keeps its red circle.

### 11.4 The weights are convention, and are reported as such

No published weighting exists for this combination of factors. The defaults
encode an ordering rather than a calibration:

| Factor | Weight | Why it sits there |
|---|---|---|
| blockage confidence | 3.0 | whether a blockage exists at all conditions everything else |
| lake growth rate | 3.0 | the most direct sign an impoundment is still filling |
| lake volume | 2.0 | how much water is impounded, where Section 8 permits a number |
| new landslide activity | 2.0 | fresh material arriving at the blockage |
| slope | 1.0 | background potential for further failure |
| rainfall | 0.0 | optional in the brief; disabled until a source is wired in |

Each scale is a `[scores 0, scores 1]` pair, clamped outside, and every one
should be revisited per catchment. Because the weights are conventional, the
system's defence is **traceability rather than authority**: each assessment
lists every factor's value, score, weight and individual contribution, sorted
by influence, so any level can be traced to what produced it. Rainfall at
weight 0 is tested to be incapable of moving the score, so a disabled factor
cannot influence an outcome silently.

### 11.5 The published alternative, and why it is not used

Ermini & Casagli (2003) define a **Dimensionless Blockage Index** for landslide
dam stability, with dams generally stable below **2.75** and unstable above
**3.08** (those thresholds are confirmed; the exact expression was not verified
against the original paper and is therefore not reproduced here or
implemented).

It is not used as the score, for two reasons:

1. **It needs dam height and volume.** Branch B of Section 8 frequently makes
   both unmeasurable — at Tsho Rolpa the DEM recorded the water surface, so
   there is no dam geometry to feed it. A 2026 field study likewise excluded
   DBI because its required parameters are not consistently available.
2. **It rates dam stability**, a narrower question than the indicator set the
   brief specifies, which includes lake growth and new landslide activity.

Recorded here rather than silently ignored. If dam geometry becomes
measurable at a Branch A site, adding DBI as a *parallel, cited* indicator
alongside the weighted score would be worthwhile — it would need the original
paper for the formula.

### 11.6 What is *not* claimed

- **The score is not a probability.** It is a weighted mean of conventional
  factor scores on an arbitrary 0–1 range. It has not been calibrated against
  any outcome, and no outcome dataset exists for this prototype.
- **The level thresholds (0.25 / 0.50 / 0.75) are convention**, not derived
  from observed dam failures.
- **No validation against real events has been done.** Phase 11 is tested on
  hand-chosen inputs; the factors it consumes come from Phases 5, 7, 8, 9 and
  10, and three of those are not yet built.
- **Rainfall is absent, not zero-risk.** Its weight is 0 so it cannot affect
  the score, and it is listed under "Not measured" in every warning.

### 11.9 Phase 11 on real data — ND-001 / BL-001, Baige 2018

Every input is a measured Baige result: blockage confidence 0.500 from Phase 7,
new landslide area 1,900 m² from Phase 5, median slope 51.6° from the DEM, lake
growth rate from Phase 9. Volume is **not supplied** — Phase 10 has not run on
this site — and rainfall carries weight 0 with no source wired. Data coverage
is 81.8%, above the 50% floor, so the level is not withheld.

| phase of the lake | rate | score | level |
|---|---|---|---|
| filling, 11-02 → 11-09 | +86,029 m²/day | 0.6196 | **🟠 HIGH RISK INDICATORS** |
| declining, as Phase 9 measured it | −13,131 m²/day | 0.2862 | 🟡 MONITOR |

**The filling phase is flagged, which is the result that matters.** A real
landslide dam impounding a major river produced HIGH RISK INDICATORS from
measured inputs, with every contributing factor listed. The filling rate is a
two-point reconstruction (602,200 m² over 7 days, from a pre-event date with no
lake) rather than a Phase 9 trend, and is labelled as such.

#### 11.10 Finding: a draining lake and a static lake score identically

`lake_growth_rate` has the heaviest weight (3.0) and a scale of
`[0, 2000] m²/day`. A negative rate clamps to the bottom, so the decline scores
**0.000** — the same as a lake that is not changing at all. The factor simply
stops contributing.

For Baige the fall was engineered, so a lower level is defensible. But **a
breach produces the same signature**: a barrier lake that has just emptied
catastrophically shows a large negative area rate, and the heaviest factor in
the score reads it as nothing to report. The trend label does say
`Decreasing`, and the dashboard shows it, but the number driving the level
cannot tell a controlled drawdown from an outburst that has already happened.

This is faithful to the brief, which names "lake area growth rate" as the
factor, and it is not changed here: distinguishing the two cases needs either a
signed treatment of the rate or a separate downstream-flood signal, and both
change what the score means. It is recorded as an open item for decision.

Two further caveats on this score. It inherits the Phase 7 mis-ranking
(§7.11), since `blockage_confidence` is the 0.500 that ranked ND-001 below six
drained-reach candidates. And `lake_volume` is absent at weight 2.0, which is
reported as unavailable with its reason rather than scored as zero — the
distinction §11.4 exists to preserve.

## End-to-end integration

Every phase above is tested in isolation. `tests/test_pipeline_end_to_end.py`
wires them together in the order a real run uses:

```
landslide change -> blockage -> barrier lake -> tracking
                 -> trend -> depth/volume -> risk -> storage
```

The scene is a synthetic V-shaped valley built from an analytic surface
(`elevation = 4600 - 0.8*row + 1.5*|col - channel|`), with debris stamped
across the channel and water impounded behind it. The geometry is chosen so
the expected answers are known: the valley's capacity can be integrated by
hand and compared against what Phase 10 reports.

### E.1 What the chain produces

| Stage | Result |
|---|---|
| Phase 5 | 90 changed pixels, one landslide polygon |
| Phase 7 | one candidate, `ND-001`, with obstruction evidence |
| Phase 8 | barrier lake 34,600 m², expanding +130.7% (19,600 m² of it new) |
| Phase 9 | trend **Increasing**, +773.3 m²/day over 30 days, 0 gaps |
| Phase 10 | **Branch A**: mean depth 6.69 m, max 18.00 m, volume **0.173 × 10⁶ m³** [0.133–0.213] |
| Phase 11 | **MONITOR**, score 0.40, data coverage **100%** |
| Storage | one site, one landslide event, four observations, one estimate, one assessment |

This is the first and only exercise of **Branch A** anywhere in the project.
Every real lake met so far has been Branch B, because the Copernicus DEM
recorded its surface; here the DEM holds a genuine pre-lake valley floor, so a
volume is both permitted and meaningful. The test checks it against the
analytically integrated capacity of the V rather than against itself, and
asserts the estimate sits slightly *above* that figure — which it must, since
the water surface elevation is read from a shoreline that lies a little above
the fill level.

It is also the first time Phase 11 has run at **100% data coverage**. Until
the chain existed, three of its five factors were permanently unavailable.

### E.2 Two defects found only by integration

Both passed every unit test and failed quietly end to end.

1. **The interface Phase 8 needed did not exist.** `BlockageCandidate`
   carried a centroid but not the stream pixels the landslide reaches, and
   `find_barrier_lakes` needs exactly those to decide what is upstream. The
   two phases could not be chained at all. Candidates now carry `site_mask`
   and `landslide_mask`.

2. **A uniform scene crashed the change detector.** Phase 5's default
   brightness and SAR thresholds are derived from the scene's own spread, and
   `robust_change_threshold` raises when the median absolute deviation is
   zero. That exception propagated out of `detect_change` and killed the run.
   Everywhere else this project reports "unavailable with a reason" and
   carries on; now so does this. The signal is recorded unavailable, counts
   neither for nor against agreement, and the remaining signals continue.

   Real imagery is never noiseless, so this would not have appeared on real
   data — but a small or heavily masked AOI could reach the same state, and a
   monitoring pipeline that dies on a quiet scene is not acceptable.

### E.3 Degradation is tested too

Three tests check the chain stays honest as data thins:

- cloud over the lake yields `not_observed`, which becomes a gap in the series
  and an `Unknown` trend — **never a breach signal**;
- a landslide beside an unchanged river produces no blockage, and therefore no
  barrier-lake search;
- with every upstream phase silent, Phase 11 returns a flagged
  `insufficient_data` assessment carrying the disclaimer, not a quiet NORMAL.

A separate test confirms the chain cannot route around Section 8: a Branch B
lake whose record is doctored with a volume is refused by the database.

### E.4 What this does and does not establish

It establishes that the **interfaces** are sound and that a complete event
flows through the system producing coherent, traceable output.

It does **not** establish that any phase is accurate. The scene is synthetic
and built to be detectable. Real imagery has cloud, shadow, snow, speckle and
terrain that the analytic valley has none of, and the three phases with
deferred real-data gates (5, 7, 8) remain unvalidated against it.

## Appendix A — Configuration audit: every key must have a reader

`config/schema.py` states that sections are introduced at the phase that
first *consumes* them, "so that every key in config.yaml has a reader and no
dead configuration accumulates". That invariant was asserted but never
checked. Walking all **182 schema leaf fields** and searching the production
code for each found **ten keys with no reader at all**.

A key nobody reads is worse than clutter. It looks like a control, it is
documented like a control, and turning it does nothing — which is a silent
failure of exactly the kind this project tries to design out.

| Key | What it claimed to do | Reality |
|---|---|---|
| `gee.max_request_pixels` | refuse a request "so a mistyped AOI cannot try to pull a full Sentinel scene onto a laptop" | **no reader — the guard did not exist** |
| `preprocessing.cloud.cloud_score_band` | choose `cs` or `cs_cdf` | callers picked a band by hand; setting it changed nothing |
| `preprocessing.terrain.shadow_ray_step_px` | ray sampling interval | the function defaulted it; every caller took the default |
| `preprocessing.terrain.shadow_max_distance_m` | horizon search distance | as above |
| `preprocessing.terrain.quicklook_azimuth_deg` | quick-look sun | no consumer |
| `preprocessing.terrain.quicklook_altitude_deg` | quick-look sun | no consumer |
| `preprocessing.sar.geometry_dilate_px` | grow the layover/shadow mask | the function defaulted it |
| `detection.landslide_change.gating.snow_ndsi_min` | Hall et al. NDSI ≥ 0.4 | `detect_change` takes pre-built masks; the number never reached the test |
| `detection.landslide_change.gating.snow_nir_min_reflectance` | Hall et al. NIR > 0.11 | as above |
| `paths.figures` | output directory | unused |

**Nine are now wired**, each through a small configuration-reading wrapper
beside the function it feeds, and each pinned by a test that asserts the
configured value actually reaches the computation:

- `acquisition.gee_client.export_image` now enforces the pixel guard, which is
  a genuinely different limit from `max_export_bytes` — pixel count is what
  `getDownloadURL` itself caps, so a single-band request can sit under the
  byte limit and still be refused by the server.
- `preprocessing.cloud_mask.select_cloud_score` picks the configured band and
  **raises naming it** if it was not exported, rather than falling back to
  whichever band happens to be present.
- `preprocessing.terrain.terrain_shadow_for_scene` and `quicklook_hillshade`.
  The sun angles stay *arguments* rather than configuration: they belong to
  the scene, and a per-scene shadow mask computed from a configured angle
  would be wrong for every scene but one.
- `preprocessing.sar.layover_shadow_for_scene`, which also looks the
  toward-sensor azimuth up from the orbit pass, so a caller cannot pair an
  ascending scene with descending geometry by accident.
- `detection.landslide_change.snow_mask_from_config`.

`paths.figures` is left unwired and is simply unused; `paths.processed` and
`paths.training` are referenced only by tests. These three are a directory
manifest rather than behaviour, and forcing a reader for them would be
ceremony.

The audit script is not kept in the repository — it is a few dozen lines of
reflection over `Config.model_fields` and a regex search, and re-running it
after adding a config section is the point, not preserving the script.

## Storage layer — database (brief, Section 10)

Not a numbered phase in Section 12, but required by Section 10 and built after
Phase 11 because Phases 10 and 11 already emit records shaped for its tables.

### D.1 SQLite, WKT geometry, swappable

SQLite with geometry stored as WKT, per Section 4. "Swappable" is made
concrete by a `MonitoringStore` protocol: nothing outside `database/db.py`
issues SQL, so a GeoPackage or PostGIS backend implements the same methods
without touching callers.

All six tables the brief names as a minimum are present: `sites`,
`observations`, `depth_volume_estimates`, `landslide_events`,
`risk_assessments`, `runs`.

### D.2 The database refuses values the system promised not to produce

Two integrity rules are enforced as SQL `CHECK` constraints rather than left
to callers, so that a bug upstream cannot persist a value the rest of the
project has committed to never emitting.

**The Section 10 vocabulary.** Every stored value carries a `value_type` drawn
from `observed`, `classified`, `estimated`, `empirical`, `derived` or
`unavailable`. Anything else is rejected by the database, not merely by the
Python wrapper — a test inserts a bad value type through raw SQL to prove the
constraint, not the wrapper, is doing the work.

**Section 8's rule that an unavailable depth is not a number.** A
`depth_volume_estimates` row whose `value_type` is `unavailable` must hold NULL
in every depth and volume column, and only Branch A may be `estimated`:

```sql
CHECK (value_type <> 'unavailable'
       OR (mean_depth_m IS NULL AND max_depth_m IS NULL
           AND volume_m3 IS NULL AND volume_low_m3 IS NULL
           AND volume_high_m3 IS NULL)),
CHECK (branch = 'A' OR value_type IN ('unavailable', 'empirical'))
```

This is defence in depth against a specific, measured failure. §10.3 showed
that applying the Branch A formula to a Branch B lake yields 14.3, 21.7 or
30.9 million m³ depending only on a buffer width. A test attempts to store
exactly that 14.3 million m³ figure against a Branch B row, and the database
refuses it.

Foreign keys are switched on explicitly — SQLite leaves them off by default,
so a dangling `site_id` would otherwise be accepted silently.

### D.3 Finding: a stored level is not the same thing as a warning

Running the full chain end to end on Tsho Rolpa produced a correct result that
was nonetheless misleading **once stored**:

```
level            NORMAL
score            0.0
```

In memory that assessment carried `insufficient_data = True` and
`data_coverage = 0.09`, and its symbol was ⚪ rather than 🟢. None of that
reached the database, because the brief's minimum columns for
`risk_assessments` are id, site_id, assessed_at, factors_json, score, level
and config_version. Anyone querying the table directly — which is what a
dashboard or a report generator will do — would read a plain `NORMAL`.

Section 10 says *minimum* tables, so the table was extended with
`data_coverage` and `insufficient_data`, both constrained, and
`RiskAssessment.as_record()` now emits them. The stored row for that same
assessment reads:

```
level             NORMAL
data_coverage     0.0909
insufficient_data 1
```

The caveat now travels with the verdict. This is the same error as §11.3 in a
different medium, and it was only visible by running the whole chain rather
than testing the layers separately.

### D.4 Provenance

`runs` records `started_at`, `config_hash`, `code_version`, `aoi`, `status` and
`log_path`, and every other table carries a `run_id`, so any stored value is
traceable to the configuration and code that produced it.

`code_version` is read from `.git/HEAD` directly — following branch refs and
`packed-refs` — rather than by invoking git. Outside a git working tree it is
`None`: the run is still recorded, with the code version honestly unknown
rather than faked. This repository is not currently a git tree, so that is the
path exercised in practice.

### D.5 What is *not* claimed

- **Gaps are gaps.** A date with no usable observation simply has no row.
  Nothing in this layer interpolates, and a test asserts that two observations
  a month apart come back as two rows, not a filled series.
- `landslide_events.site_id` is nullable: a detected landslide need not belong
  to a site yet, since the blockage logic that creates sites is Phase 7.
- The `level` column is unconstrained text. The four level strings are fixed
  in `analysis.risk`, and duplicating them in SQL would create two places for
  them to drift apart.
- No migration mechanism exists. `initialise()` is `CREATE TABLE IF NOT
  EXISTS`, so a schema change against an existing database needs a manual
  migration. Acceptable for a prototype, and recorded rather than assumed.

## Phase 12 — Streamlit dashboard

**Gate passed.** `streamlit run app/dashboard.py` serves the app, and the
script renders with no exception, all eleven Section 14 questions on the page.

### 12.1 The answers are not built by the user interface

`app/site_view.py` assembles the Section 14 answers as plain dataclasses, with
no Streamlit, Folium or Plotly import. `app/dashboard.py` only arranges them.

The separation is not tidiness. The answers are where this project's integrity
rules meet a user interface, and interfaces are where such rules quietly die:

- `unavailable` must not render as an empty cell — a blank reads as *nothing
  to report*, which is a different claim from *we could not measure this*;
- a gap must not be bridged by a line;
- a NORMAL level built on a tenth of the evidence must not render as a green
  tick.

Keeping the answers in plain data means each of those is a unit test rather
than something to be checked by eye in a browser.

### 12.2 Every question is answered, including with nothing to say

Section 14 lists eleven questions. All eleven are answered for every site,
whatever is missing — a site with no assessment still answers "Contributing
factors" with `Unavailable` and a reason. An early version dropped that
question when there was no risk row, which would leave a reader unable to tell
whether the factors were unmeasured or simply not displayed. A test counts the
rendered questions and requires exactly eleven.

Each answer carries its `value_type` from the Section 10 vocabulary, so the
page can show which values are observed, classified, estimated or unavailable,
as Section 14 requires.

### 12.3 A gap breaks the line

A line chart joins consecutive points. Plotting a lake-area series with the
cloudy dates simply omitted therefore draws a straight segment across the gap
— a drawn interpolation, in the very place a reader is most likely to read
growth from, and exactly what Section 7.8 forbids.

`app/charts.series_with_gaps` carries gaps through as `None` and the trace
sets `connectgaps=False`. Two tests pin it: one on the prepared data, one on
the rendered figure object. The chart's subtitle states the gap count and that
they are not interpolated.

### 12.4 Colour, and why the validator's FAIL is accepted here

Indicator levels use the **status** palette (good / warning / serious /
critical), which is reserved and never reused for a data series. Run against
the light surface, the palette validator reports:

| Check | Result |
|---|---|
| Lightness band | FAIL — warning sits outside it |
| CVD separation | PASS — worst adjacent ΔE 11.3 |
| Normal-vision floor | FAIL — warning↔serious ΔE 13.6, below the 15 floor |
| Contrast vs surface | WARN — warning 1.79:1, serious 2.57:1 |

These are documented properties of a *status* palette rather than defects to
fix — the validator's own scope line says "categorical palettes only", and the
palette reference states that warning and serious are sub-3:1 on light **by
design**, with the icon-plus-label pairing as the mitigation.

That mitigation is implemented, and the normal-vision figure is the reason it
is not optional: **MONITOR and HIGH RISK are the adjacent pair measuring
ΔE 13.6**, and those are precisely the two levels a reader must not confuse.
So every level is rendered with its symbol *and* its text — in the legend, in
each map marker's tooltip, in the popup, and in the site heading. Colour never
carries the distinction alone anywhere in this dashboard.

Neither chart ships a categorical palette: the area series is a single series
(named by its title, so no legend), and the factor chart is one measure across
categories, which is also one colour.

### 12.5 Withholding green, again

`status_colour` and `marker_style` repeat the rule from `analysis.risk`: a
NORMAL level resting on insufficient data is drawn **grey**, not green, and
labelled "(insufficient data)". A HIGH or CRITICAL level keeps its colour
whatever the coverage, because muting a real alarm is the worse failure.

The rule now exists in three places — the assessment's symbol, the map marker
and the chart colour — because each is a surface someone might see alone.

### 12.6 The disclaimer travels with the content

It appears in the sidebar, above the site detail, and **inside every map
popup**. A popup can be screenshotted and shared by itself, so a footer-only
disclaimer would be cropped away by the most likely means of sharing.

### 12.7 What is *not* claimed

- **The dashboard displays; it does not compute.** Everything it shows comes
  from the database, and its correctness is the correctness of the phases that
  wrote it.
- **It has been rendered, not used.** The gate check runs the script through
  Streamlit's own `AppTest` harness and asserts what reaches the page. Nobody
  has clicked through it on real data, and no before/after imagery comparison
  is wired in yet — the brief asks for one, and it needs raster tiles the
  pipeline does not yet export.
- The demo database holds **one** site, so multi-site behaviour (map centring
  across sites, the level counts) is exercised only by unit tests.

## Phase 13 — Reporting and validation write-up

**Gate passed.** `outputs/reports/TR-001_report.pdf` is a 3-page PDF whose
content is verified by parsing the PDF itself, and `docs/validation.md` §18 is
the end-to-end validation write-up.

### 13.1 One set of answers, two renderers

Report content comes from `app.site_view.build_site_view` -- the same function
the dashboard uses. A report and a dashboard that answered the same question
differently would be worse than either alone, so there is one implementation
and two renderers. A test asserts every question in the view reaches the HTML.

### 13.2 Finding: WeasyPrint cannot run on Windows without GTK

The brief names `jinja2` + `weasyprint`. WeasyPrint **installs** cleanly with
pip and then **cannot import**: it binds to GTK/Pango native libraries Windows
does not ship, failing with `cannot load library 'libgobject-2.0-0'`.

This is distinct from the Smart App Control problem recorded elsewhere -- it is
the documented Windows situation for WeasyPrint, and the remedy (installing
the GTK runtime system-wide) belongs to the machine's owner rather than to a
build script.

PDF generation is therefore **engine-agnostic**: WeasyPrint is preferred when
it imports, and otherwise the HTML is printed by headless Chromium (Edge or
Chrome, both already present), which needs no installation. The engine used is
recorded on the result, so a report can say how it was made.

The HTML is always produced by Jinja2 alone. Where no PDF engine exists at
all, `generate_site_report` returns the HTML with the reason attached rather
than raising -- a monitoring run should not fail because a rendering library
is absent, and a test stubs out both engines to prove the HTML survives.

**A trap worth recording:** headless Chromium resolves a *relative*
`--print-to-pdf` path against its own working directory, and reports only
"cannot find the path specified". The path must be absolute.

### 13.3 What the report must carry

Beyond the Section 14 answers and their value types:

- the disclaimer **twice over** -- in the body and in the page footer of every
  page, because a single page may be printed or shared alone;
- each unavailable value's **reason**, so a Branch B lake reads "no
  bathymetry" rather than a blank;
- gaps labelled as gaps in the observation table, with "never interpolated"
  stated;
- the provenance block: configuration hash and code version, the latter
  honestly "unknown (not a git working tree)" here;
- a short "how to read this report" explaining the value-type vocabulary and
  restating that levels are indicators, not predictions.

Green is withheld from a thinly-evidenced NORMAL here as it is in the
assessment, the map and the chart -- a report is one more surface read alone.

### 13.4 What is *not* claimed

- **The PDF is produced by Chromium, not WeasyPrint**, so its output differs
  slightly from what the brief's stack would render.
- **No figures are embedded.** The report carries tables and text; maps and
  charts need raster export the pipeline does not yet do.
- **Per-site only.** There is no multi-site or summary report.
