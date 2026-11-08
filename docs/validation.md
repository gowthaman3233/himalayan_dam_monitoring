# Validation

**Status: Phase 0.** No detection results exist yet, so this file currently
records only the validation *plan* and the state of event selection. Phase 13
fills in the end-to-end write-up.

Nothing in this file may contain an invented event, date or coordinate. An entry
without a source is not an entry.

---

## 1. Confirmed validation sites

### Tsho Rolpa — water-vs-shadow test case

| Field | Value |
|---|---|
| Location | 27° 52′ N, 86° 28′ E (27.867° N, 86.467° E), Rolwaling Valley, Dolakha District, Nepal |
| Elevation | 4546 m a.s.l. (Kayastha & Maskey 2024); 4580 m (Shrestha & Nakagawa 2014) |
| Surface area | 1.537 km² (Shrestha & Nakagawa 2014); ≈1.65 km² in 2021 (Kayastha & Maskey 2024) |
| Sources | Kayastha, R. B. & Maskey, S. (2024), *Proc. IAHS* **387**, 59–63, <https://doi.org/10.5194/piahs-387-59-2024>. Shrestha, B. B. & Nakagawa, H. (2014), *Natural Hazards* **71**(2). |
| Role | A known, large water body enclosed by steep shadow-casting terrain. Tests that water in shadow is **kept** (brief, Section 13, test 3). |
| Depth/volume branch | **B** — the lake long predates the GLO-30 DEM epoch (≈2011–2015), so the DEM recorded its water surface, not its bed. Depth and volume must be reported `unavailable`. This makes it the natural test for Section 13, test 8. |

This is the default AOI in `config/config.yaml`. Full citation detail is in
[`methods.md`](methods.md), §0.1.

### Jure landslide, Sunkoshi River — Landsat + DEM path

| Field | Value |
|---|---|
| Date | August 2014 |
| Role | A well-documented landslide dam in Nepal (brief, Section 6). |
| Constraint | **Predates Sentinel-2** (mid-2015), so it is a test case for the Landsat + DEM pipeline path, **not** for S1/S2 fusion. |
| Open item | Sentinel-1 coverage for the event date must be **checked**, not assumed. Sentinel-1A was operational in 2014 but the acquisition plan over Nepal at that time needs verifying against the catalog. |
| Coordinates | **Not yet recorded.** To be taken from a cited source before use. |

No coordinates are written here until they come from a paper or agency report.

---

## 2. Post-2017 river-blockage events — confirmed 2026-10-26

The brief (Section 6) asks for 1–3 documented post-2017 landslide-dam events
with Sentinel-1/2 coverage, each with a source, date and approximate location,
**submitted for confirmation before use**.

**Status: two events proposed and confirmed by the repository owner on
2026-10-26.** A third candidate was presented and held in reserve. None was
adopted unilaterally and no coordinate below is invented — where a source
publishes no coordinate, that is stated rather than filled in.

The two were chosen because they do **different** jobs. Baige supplies
*measurable ground truth*; Rasuwa supplies *operational relevance* in Nepal.
Neither alone would validate the method.

### 2.1 Event A — Lhende River barrier lake, Rasuwa, Nepal (2026-08-26)

| Field | Value |
|---|---|
| Date | 2026-08-26 (sources agree on 26 Aug; one trekking site gives 16 Aug and is not relied on) |
| Location | Lhende (Lehende) river, Rasuwa district, Nepal–China border; lake reported ≈18 km upstream of the Rasuwagadhi crossing, near the confluence of the Chhochen Khola and Purepu Tsangpo |
| Coordinates | **not published by any source found.** To be determined from imagery once acquired, and recorded with the method used |
| Trigger | Ice-rock avalanche / glacier collapse, ≈100 × 10⁶ m³ of rock and ice detaching at ≈5,200 m (Stimson Center) |
| Reported lake | ≈**0.11 km²** (Nepal NDRRMA, from satellite imagery); 1.5–2 × 10⁶ m³ with ≈3 × 10⁶ m³ more inflow expected over three days (China Ministry of Water Resources) |
| Imagery used by responders | Planet Labs and Landsat (NDRRMA); no Sentinel-based published analysis yet |
| Sensors available to us | Sentinel-1 and Sentinel-2 both cover the site; the event is recent enough that a clean pre/post pair exists |

**Sources.** Al Jazeera, 28 Aug 2026, *Why Nepal faces another flood threat from
a new lake on China border*; Stimson Center, *A Cascading Disaster on the
China–Nepal Border: What to Know About the August 2026 Rasuwa Flood, 72 Hours
Later*; Kathmandu Post, 26 Aug 2026, *Scientists suspect ice avalanche triggered
Bhotekoshi flood*; NDRRMA warnings as reported in the above.

**Known weaknesses, recorded before use:**

1. **The trigger is an ice-rock avalanche, not a landslide.** The blocking
   material contains ice. That matters twice over: ice is spectrally unlike
   rock debris (Phase 6 class 2 vs class 4), and an ice-cored blockage is not
   volumetrically stable, which bears on Section 8.
2. **The sources disagree on whether the river was actually blocked.** The
   Stimson Center states that the damming effect was limited and the flow
   largely continuous, against the blockage-and-burst account elsewhere. This
   is retained deliberately: the brief (Section 7.6) forbids declaring a
   blockage without obstruction evidence, so an ambiguous case tests whether
   the system stays appropriately restrained. **A confident "dam detected"
   here would be a failure, not a success.**
3. **No peer-reviewed source exists yet** — the event is two months old.
   Sourcing is agency plus reputable press, which is weaker than Baige's.
4. **The lake may lie on the Chinese side of the border**, so the AOI will
   cross it.
5. A **separate** Lhende flood occurred in 2025 and was attributed by Nepal's
   Department of Hydrology and Meteorology to a glacial lake outburst, analysed
   with Sentinel imagery. The two must not be conflated when choosing the
   pre-event baseline.

### 2.2 Event B — Baige landslide dam, Jinsha River, Tibet (2018-10-10 and 2018-11-03)

| Field | Value |
|---|---|
| Dates | Two successive dammings: 2018-10-10 (some sources 10 Oct, some 11 Oct) and 2018-11-03 at ≈17:40 |
| Location | Right bank of the Jinsha River, Jiangda County, Tibet Autonomous Region, on the Tibet–Sichuan border |
| Coordinates | **31°04′56.41″N, 98°42′17.98″E**, as published |
| Landslide volume | ≈22 × 10⁶ m³ (one source) to ≈27.5 × 10⁶ m³ (another) — sources disagree |
| Second lake | ≈105 × 10⁶ m³ impounded; other sources give 500 × 10⁶ m³ and 775 × 10⁶ m³ storage capacity. **The disagreement is recorded, not averaged away** |
| Outcome | First lake discharged naturally 2018-10-12 at 17:30; second discharged through an engineered channel on 2018-11-13 |
| Sentinel coverage | Established in the literature — existing studies combine Sentinel-2, Sentinel-1 and a DEM on this event, and Sentinel-2 was used to track pre-failure slope movement from Nov 2015 to Aug 2018 |

**Sources.** *Study on successive landslide damming events of Jinsha River in
Baige village on October 11 and November 3, 2018*, Journal of Engineering
Geology; *Hydro-sediment-morphodynamic processes of the Baige landslide-induced
barrier lake, Jinsha River, China*, Journal of Hydrology; *Mapping outburst
floods using a collaborative learning method based on temporally dense optical
and SAR data: a case study with the Baige landslide dam on the Jinsha River,
Tibet*; *Using a single remote-sensing image to calculate the height of a
landslide dam and the maximum volume of a lake*, NHESS 22, 2081–2098, 2022;
*Emergency response to Baige Landslide Dam on the Jinsha River in China*, CFBR.

**Known weaknesses, recorded before use:**

1. **It is not in Nepal.** The brief names Nepal as the primary study area.
   Baige is included for its measurable ground truth, not as a Nepali case, and
   nothing in the code assumes a site (`utils.crs` derives the UTM zone from
   the AOI centroid, which here is zone 47N, not Nepal's 44N/45N — which also
   makes it a genuine test that no Nepal assumption has crept in).
2. **Published figures conflict**, especially lake volume (105 vs 500 vs
   775 × 10⁶ m³). Any comparison must quote the range, never a single number.
3. **Two events five weeks apart.** The pre/post pair must be chosen
   deliberately, or the October dam will contaminate the November baseline.

### 2.3 Held in reserve — Myagdi River, Bansbot, Nepal (≈2025-07-09)

A landslide from the Bansbot cliff, Dhaulagiri Rural Municipality–4, Myagdi
district, blocked the Myagdi River and formed what reports call an artificial
lake. **Not adopted**, for two reasons: sourcing is **news only** (Khabarhub,
myRepublica, nepalkhabar — no agency or peer-reviewed report found), with no
coordinates and no dimensions ("detailed information about the size and
potential threat of the lake will only be available once the team reaches the
site"); and early July is peak monsoon, so Sentinel-2 will be largely cloud.

It remains useful for **required test 9** (cloudy-only date range → graceful
"no valid observation"), which needs no confirmed measurements.

---

## 3. Required system tests

The nine scenario tests from the brief, Section 13. Tests 1–7 are to use real
imagery from documented locations wherever possible; synthetic arrays are
permitted only for unit-level logic and are marked `@pytest.mark.synthetic`.

| # | Scenario | Expected outcome | Phase | Status |
|---|---|---|---|---|
| 1 | Normal mountain terrain | No water, no candidate | 3, 7 | unit-level pass (synthetic, Phases 3 and 4); still needs a real snow-free, water-free AOI |
| 2 | Deep shadowed valley, no lake | Classified shadow, **not** water | 4 | ✅ **pass** — unit-level, plus on real imagery <2% of steep shadowed terrain is called water |
| 3 | Known existing lake in a shadowed valley | Water detected | 3, 4 | ✅ **pass** — Tsho Rolpa detected at 1.614 km² after fusion, 96.4% of the known-water reference retained while 87.5% of false water is removed |
| 4 | Landslide near a river | Landslide detected, **no** blockage without obstruction evidence | 5, 7 | ✅ **pass** — synthetic, and on the real Tsho Rolpa channel: a landslide placed on the stream with the river unchanged yields 0 candidates |
| 5 | Landslide crossing a river with obstruction evidence | Potential landslide dam | 7 | **synthetic pass** — candidate ND-001 with all three obstruction signals; real-data gate awaits imagery |
| 6 | Water accumulating upstream of the blockage | Potential barrier lake | 8 | **synthetic pass** — impounded water upstream of ND-001 is identified and tracked; real-data gate awaits imagery |
| 7 | Expanding lake | Trend Increasing, higher monitoring concern | 9, 11 | ✅ **pass** — an expanding series classifies as Increasing and raises the Phase 11 score; synthetic series, as no real multi-date series exists yet |
| 8 | Lake present in the DEM epoch | Depth **unavailable** (Branch B), never a number | 10 | ✅ **pass on real data** — Tsho Rolpa returns Branch B; the DEM inside the lake is flat to **0.00 m** over 15 501 px, proving it recorded the water surface |
| 9 | Cloudy-only date range | Graceful "no valid observation", no crash | 2, 9 | ✅ **pass** — six cloudy dates give trend Unknown with 0 valid / 6 gaps and no numbers, no crash |

Tests 2, 3 and 8 have a confirmed real site (Tsho Rolpa). Tests 4–7 now have
confirmed events too (§2: Baige 2018 and Rasuwa 2026), so they are unblocked
as of 2026-10-26 and are scheduled for Phases 5, 7 and 8. Test 9 can use the
Myagdi candidate held in reserve.

---

## 4. Phase 0 verification record

What was actually checked at Phase 0, as opposed to asserted:

Test run: **85 passed, 8 skipped, 0 warnings** (the 8 skips are the Earth Engine
tests, which skip with the registration instructions when no session exists).

| Check | Method | Result |
|---|---|---|
| Configuration validates; unknown keys rejected | `tests/test_config.py` | ✅ pass |
| Disclaimer cannot be weakened or dropped | `tests/test_config.py` | ✅ pass — schema refuses the config |
| Default AOI carries a resolvable citation | `tests/test_config.py` | ✅ pass |
| Config hash stable, order-independent, value-sensitive | `tests/test_config.py` | ✅ pass |
| UTM zone derived from the centroid, not assumed | `tests/test_crs.py` | ✅ pass — incl. zone 44/45 boundary at 84° E |
| Nepal resolves to EPSG:32644 / 32645; Tsho Rolpa to 32645 | `tests/test_crs.py` | ✅ pass |
| Geographic CRS refused for area computation | `tests/test_crs.py` | ✅ pass — `ensure_projected` raises on EPSG:4326 |
| Run-scoped logging; no duplicate handlers | `tests/test_logging.py` | ✅ pass |
| GeoJSON AOI parsing (geometry / Feature / FeatureCollection) | `tests/test_io.py` | ✅ pass |
| Earth Engine collection IDs and band names match the live catalog | `pytest -m gee -s` → `outputs/gee_catalog_probe.json` | ✅ pass — all 6 IDs resolve; see `methods.md` §0.4 |
| AOI geometry area matches the configured buffer | `tests/test_gee_smoke.py` | ✅ pass — 49.665 km² vs π·4² = 50.265 km² expected (1.2%) |
| Required S2 bands present (B2, B3, B4, B8, B11, B12, SCL) | `tests/test_gee_smoke.py` | ✅ pass |
| Required S1 bands present (VV, VH, angle) | `tests/test_gee_smoke.py` | ✅ pass |
| S2 per-scene solar angles available for terrain-shadow masking | `tests/test_gee_smoke.py` | ✅ pass — zenith 35.077°, azimuth 152.565° (2023-10-04) |
| S1 ascending/descending orbits separable | `tests/test_gee_smoke.py` | ✅ pass — both present; relative orbits 12, 85, 121 |

**Gate result: both halves pass.** Earth Engine project `himalayan-510514`,
credentials present. Combined run: **93 tests, 93 passing** (85 offline + 8 live).

### Data coverage measured over the default AOI

Window 2023-10-01 → 2023-11-30, AOI 49.665 km²:

| Collection | Images | Notes |
|---|---|---|
| Sentinel-2 L2A | 12 | MGRS tile `45RVL` |
| Cloud Score+ | 12 | 1:1 with S2 |
| Sentinel-1 GRD | 15 | ASCENDING + DESCENDING, IW |
| Landsat 8 L2 | 4 | |
| Landsat 9 L2 | 3 | |

Both Sentinel-1 orbit directions are available over this AOI, which the
shadow-rejection work in Phase 4 depends on.

---

## 5. Phase 1 verification record

Test run: **137 passed, 0 failed** (129 offline + 8 live Earth Engine).

| Check | Method | Result |
|---|---|---|
| Exported GeoTIFFs are readable rasters | rasterio read-back of all 7 exports | ✅ pass — 797×799 px, 10.0 m pixels, EPSG:32645 |
| UTM zone derived, not assumed | `resolve_export_crs` | ✅ pass — `auto` → EPSG:32645 |
| Metadata carries all of Section 5 | sidecar + embedded GeoTIFF tags | ✅ pass — sensor, dates, orbit/tile, level, collection |
| S1 ascending and descending kept separate | export layout + filenames | ✅ pass — `ASC012` / `DESC121` in separate directories |
| S1 incidence angle retained | band check | ✅ pass — ASC 32.5–33.3°, DESC 39.9–40.6° |
| DEM tile versions de-duplicated | `tile_version_policy` | ✅ pass — 361 entries → 9 |
| DEM epoch measured, not assumed | `acquisition_epoch` | ✅ pass — 2011-01-05 → 2014-09-08 |
| Branch A/B boundary resolves conservatively | unit tests | ✅ pass — hinge date itself yields **B** |
| Cloudy window degrades gracefully | unit tests + live run | ✅ pass — 4 of 12 S2 scenes rejected, logged not hidden |
| Sensor-epoch guards fail before any network call | unit tests | ✅ pass — S2 refuses Aug 2014 |

### Georeferencing validation (independent corroboration)

Three independent estimates of the Tsho Rolpa water surface:

| Source | Lake area |
|---|---|
| Shrestha & Nakagawa (2014), published | 1.537 km² |
| Copernicus DEM `WBM` band (2011–2014 radar) | 1.550 km² |
| Sentinel-2 `SCL` class 6 (2023-10-24 optical) | 1.502 km² |

Spread ≈3%. This validates the AOI coordinates, the derived UTM zone, the pixel
size and the georeferencing **together**. It is explicitly *not* a water-
detection result — both masks are the providers' own classifiers, and this
project's water detection is Phase 3.

### Relevant to the core contribution

On the 2023-10-24 Sentinel-2 scene, SCL class 2 (`dark area / shadow`) covers
**9.76 km², 15.3%** of the exported raster. That is the scale of the terrain-
shadow problem Phase 4 exists to solve, measured on real data over the study
area.

---

## 6. Phase 2 verification record

Test run: **234 passed, 0 failed** (226 offline + 8 live Earth Engine).

| Check | Method | Result |
|---|---|---|
| Cast-shadow length matches geometry | analytic `h / tan(e)` at 4 sun elevations | ✅ pass — within one 10 m cell |
| Cast shadow vs independent implementation | `ee.Terrain.hillShadow`, same DEM/grid/angles | ✅ **92.3% pixel agreement** |
| Shadow geometry conventions | shadow fraction by aspect under a SSE sun | ✅ pass — NW 57.6% > N 39.7% > … > SE 0.4% |
| Slope/aspect correctness | constant-gradient ramps, 5°–60° | ✅ pass — exact to 1e-6 |
| Self-shadow vs cast shadow separated | component layers returned | ✅ pass — cast is 66.4% of shadowed area |
| Terrain shadow never masked as cloud | schema refuses SCL 2 as cloud | ✅ pass — enforced, not conventional |
| Cloud shadow separate from terrain shadow | overlap report | ✅ pass — 14.41% of scene is shadowed **and** usable |
| S1 double-dB conversion prevented | `to_decibels` guard | ✅ pass — raises on dB input |
| Layover/shadow conditions | idealised slopes vs the inequalities | ✅ pass |
| Both orbit passes reduce unusable area | ASC vs DESC vs both | ✅ pass — 31.6%/27.2% → **15.7%** combined |
| Categorical layers never interpolated | stack resampling rules | ✅ pass |
| WhiteboxTools runs under Smart App Control | v2.4.0 binary download + execute | ✅ pass |

**Gate result: the specified gate passes.** "Shadow masks visually match the
hillshade for known dates" — see `outputs/figures/phase2_shadow_gate.png`, where
cast shadow falls precisely on the shaded flanks, confirmed numerically against
`ee.Terrain.hillShadow`.

---

## 7. Phase 3 verification record

Test run: **295 offline passed, 0 failed**; 69 of them new in Phase 3. The 8
live Earth Engine tests skipped (not authenticated in this session) and are
unchanged since Phase 1. Real-data checks run against the Phase 2 stack of Tsho
Rolpa (S2 tile 45RVL 2023-10-19, S1 ASC012/DESC121, GLO-30), 797 × 799 at 10 m
in EPSG:32645.

| Check | Method | Result |
|---|---|---|
| Known glacial lake detected | optical rule on real imagery | ✅ pass — largest body **1.578 km²** |
| Area plausible vs published | Shrestha & Nakagawa (2014): 1.537 km² | ✅ pass — **+2.7%** |
| Area plausible vs independent observation | GLO-30 DEM-epoch water-body mask: 1.550 km² | ✅ pass — **+1.8%**, 95.6% recall, 93.9% of the body inside it |
| Lake position | body centroid vs cited coordinates | ✅ pass — 86.4769 E, 27.8606 N, ~1.2 km from a point cited to arcminute precision |
| Lake elevation | mean DEM elevation inside the body | ✅ pass — **4547 m** vs 4546–4580 m published |
| Snow not counted as water | SCL class 11 fraction inside the mask | ✅ pass — 67% → **4.5%** after the cited NIR screen |
| Otsu implementation correct | cross-check vs `skimage.filters.threshold_otsu` | ✅ pass — within one bin width |
| Bimodality guard rejects a single mode | EM fit on a synthetic Gaussian | ✅ pass — 0.99 < 2.0 (hard-split would give 2.67) |
| Separation statistic unbiased | EM fit on a generated Δμ = 4.0 | ✅ pass — recovered as 4.0002 |
| Tiling fixes threshold placement | synthetic 0.39% water fraction | ✅ pass — global Otsu selects 43.5%, tiled 0.39% |
| No threshold invented without support | unimodal input, no configured fallback | ✅ pass — `unavailable` with a reason, mask empty **and invalid** |
| Cloud pixels are invalid, not dry | cloud placed over synthetic water | ✅ pass — not water *and* not observed |
| Areas never computed in degrees | geographic CRS passed to `water_bodies` | ✅ pass — refused |
| Polygon geometry exact | 10 × 10 px square at 10 m | ✅ pass — 10 000 m², 400 m perimeter |
| Island not counted as water | polygon with an interior ring | ✅ pass — area excludes the hole |

**Gate result: the specified gate passes.** "Known glacial lakes detected; areas
plausible" — Tsho Rolpa is detected at 1.578 km² against a published 1.537 km²
and an independent DEM-epoch 1.550 km², and its elevation and position match the
cited source. See `outputs/figures/phase3_water.png`,
`outputs/phase3_water_report.json` and `outputs/maps/phase3_water_bodies.geojson`.

---

## 8. Phase 4 verification record

Test run: **339 offline passed, 0 failed**; 44 of them new in Phase 4. The 8
live Earth Engine tests skipped (not authenticated in this session).

Real-data checks run over the Phase 2 stack of Tsho Rolpa, with Sentinel-2
2023-10-19 and 2023-10-24, Sentinel-1 DESC121 and GLO-30.

| Check | Method | Result |
|---|---|---|
| Section 7.3 rule 1 — shadow + SAR not water-like | synthetic pixel | ✅ pass — classified terrain shadow |
| Section 7.3 rule 2 — shadow + SAR water-like | synthetic pixel | ✅ pass — classified water; differs from rule 1 **only** in the SAR evidence |
| Section 7.3 rule 3 — SAR inside layover/shadow | synthetic pixel | ✅ pass — SAR term withdrawn, flagged `sar_deferred_to_optical`, optical decides |
| **False water reduction (the gate)** | vs the Phase 3 index-only mask | ✅ **87.5% removed** (162 199 of 185 417 px) |
| Reduction is not bought by deleting lakes | GLO-30 DEM-epoch water mask | ✅ **96.4% retained**, vs 97.9% for the baseline |
| Removals are justified | composition of removed pixels | ✅ 76.4% snow, 82.5% slope > 10°, only **0.2%** inside the known-water reference |
| Steep shadowed terrain is not water | real imagery, slope > 30° and in shadow | ✅ pass — **<2%** called water |
| Known lake survives | largest body after fusion | ✅ **1.614 km²** vs published 1.537, DEM-epoch 1.550 |
| Probabilities are a proper distribution | sum over the three classes | ✅ pass — 1.0 everywhere valid, NaN only where invalid |
| Every verdict is traceable | `FusionResult.explain()` | ✅ pass — each pixel lists every factor's signed contribution |
| No evidence → not land | fully clouded synthetic input | ✅ pass — `CLASS_UNCLASSIFIED`, not land |
| Slope available under cloud | synthetic | ✅ pass — the DEM does not stop working when the sky is cloudy |
| Conclusion is robust to the convention weights | 16 variants, each weight halved and doubled | ✅ removed 80.1–89.0%, retained 95.8–96.8% |

**Gate result: the specified gate passes.** "False-water reduction quantified
on shadowed valleys" — 87.5% of the index-only mask removed while retaining
96.4% of the independently observed lake surface, with the composition of what
was removed reported. See `outputs/figures/phase4_shadow_rejection.png`,
`outputs/phase4_shadow_rejection_report.json` and
`data/processed/phase4_probabilities.tif`.

---

## 9. Phase 6 verification record

Test run: **673 offline passed, 0 failed**; 33 of them new.

**The Phase 6 gate is NOT met**, and cannot be until labelled data exists. The
gate asks for per-class metrics and the water-vs-shadow confusion *for both
models*; no model has been trained. What follows verifies the machinery only.

| Check | Method | Result |
|---|---|---|
| Output shape matches the input grid | random tensors | ✅ pass |
| The channel stack is configurable | 6 and 16 channels | ✅ pass — not fixed at 3 |
| A wrong channel count is refused clearly | 3 into a 6-channel model | ✅ pass |
| Odd input sizes survive the decoder | 50×38 patch | ✅ pass |
| Gradients reach the first layer | backward from the output | ✅ pass — finite and non-zero |
| Attention coefficients are probabilities | all gates | ✅ pass — single-channel, in (0, 1) |
| **A gate can suppress a skip** | psi driven negative | ✅ pass — alpha → 0, skip removed |
| The gate accepts a coarser gating signal | 8×8 gate, 16×16 skip | ✅ pass — interpolated |
| **The baseline differs only in the gates** | same class, `attention=False` | ✅ pass — identical depth and widths |
| The gates cost parameters | parameter counts | ✅ pass |
| Both models train one step | 5 Adam steps on a fixed batch | ✅ pass — loss decreases |
| Per-class IoU/Dice/P/R/F1 are arithmetic | hand-computed scene | ✅ pass |
| An absent class is reported, not hidden | class 4 missing | ✅ pass — excluded from macro averages |
| Ignored pixels are excluded and counted | `IGNORE_INDEX` | ✅ pass |
| **The evaluation has no `accuracy` attribute** | Section 7.5 | ✅ pass — must be requested deliberately |
| **Water-vs-shadow is reported both ways** | counts and rates | ✅ pass |
| A macro average hides a total failure | every shadow pixel called water | ✅ pass — shadow IoU 0.00, macro IoU 0.50, **accuracy 0.90** |
| Models compare per class | `compare()` | ✅ pass |

### Open items at the Phase 6 gate

1. **No model has been trained, so the brief's required result does not
   exist.** The plain-U-Net vs Attention-U-Net comparison is the deliverable,
   and it needs labels and a GPU session.

2. **No labelling has been done.** `docs/labelling.md` is a specification. The
   public-dataset mappings are deliberately deferred until the real data is
   inspected rather than guessed in advance.

3. **`models/dataset.py`, `train.py`, `predict.py`, `unet.py` and the Colab
   notebook are now written** (§27), against the label schemas verified from
   the official dataset repositories. A patch builder remains, because its
   shape depends on how the hand labels come back.

4. **The geographic split is now implemented** in
   `models.dataset.assign_splits`, with block-level partitioning and a
   boundary buffer; see §27 and `docs/labelling.md`.

5. **PyTorch is CPU-only here** (2.14.1+cpu), which is right for shape and
   gradient tests. It installed without incident — Smart App Control did not
   block it.

---

## 10. Phase 7 verification record

Test run: **537 offline passed, 0 failed**; 25 of them new in Phase 7.

| Check | Method | Result |
|---|---|---|
| **Proximity alone is never a dam** | landslide across a channel, river unchanged | ✅ pass — 0 candidates |
| ...and on real terrain | 144-px landslide on the real Tsho Rolpa channel | ✅ pass — 0 candidates |
| No landslides → no candidates | real AOI, true state | ✅ pass — 0 candidates |
| The conjunction cannot be configured away | `min_evidence_types = 0` | ✅ pass — schema refuses |
| No water masks → no candidate | obstruction unmeasurable | ✅ pass |
| Obstruction present → candidate | synthetic dam, all three signals | ✅ pass — ND-001 |
| New upstream water detected | directional signal | ✅ pass |
| Downstream water loss detected | directional signal | ✅ pass |
| Channel narrowing detected | cross-section at the blockage | ✅ pass |
| More evidence → higher confidence | three signals vs one | ✅ pass |
| **Direction is read from the data** | flow accumulation reversed | ✅ pass — upstream signal switches off |
| No accumulation → absent, not guessed | directional signals | ✅ pass — reported absent with a reason |
| Dam code format | Section 7.6 | ✅ pass — `ND-001`, prefix configurable |
| The type never asserts a dam exists | site type string | ✅ pass — "Potential Landslide Dam" |
| Every candidate lists its factors | Section 9 principle | ✅ pass |
| Proximity is labelled a precondition | factor metadata | ✅ pass — excluded from the obstruction signals |
| Confidence feeds the risk assessment | into Phase 11 | ✅ pass — `blockage_confidence` now available |

**Gate status: the positive gate is NOT yet run.** "Candidate found at a
confirmed validation event" needs imagery. The negative controls above pass on
real data, which is the half that governs normal operation.

### Open items at the Phase 7 gate

1. **No real blockage has been detected.** Only negative controls have been
   run on real terrain. The positive gate awaits Earth Engine access and the
   Baige or Rasuwa imagery.

2. **Nothing verifies that a supplied landslide mask is actually new.** Phase
   5 is the only legitimate source; a single-date classification passed in its
   place would silently produce candidates at pre-existing scars. The brief
   (Section 7.4) is explicit that novelty comes from change detection, and
   this module trusts its caller on that point.

3. **Distance is measured in whole pixels** (10 m steps), because dilation is
   used rather than a distance transform — a deliberate trade to avoid scipy,
   whose compiled extensions are intermittently blocked here.

4. **The narrowing zone is radius-sensitive.** `channel_zone_m` must stay well
   inside `evidence_search_m`; set too wide it reaches into the impounded
   water and inverts, reporting no narrowing exactly when a dam has formed.
   Recorded in `methods.md` 7.3 so the default is not raised casually.

---

## 11. Phase 8 verification record

Test run: **564 offline passed, 0 failed**; 27 of them new in Phase 8.

| Check | Method | Result |
|---|---|---|
| Water impounded upstream is a barrier lake | required scenario 6 | ✅ pass |
| **A lake downstream is not a barrier lake** | lake below the blockage | ✅ pass — rejected |
| **Direction is read from the data** | flow accumulation reversed | ✅ pass — the same scene stops qualifying |
| Unchanged pre-existing water is not a barrier lake | Section 7.7's new-or-expanding test | ✅ pass |
| An expanding pre-existing lake qualifies | +78% over baseline | ✅ pass |
| A one-pixel change does not qualify | below the expansion threshold | ✅ pass |
| No flow accumulation → nothing returned | upstream cannot be guessed | ✅ pass |
| A lake keeps its ID across dates | two observations | ✅ pass — BL-001 |
| **Merge keeps the larger lake's identity** | big + small → one | ✅ pass — small absorbed and recorded |
| **Split keeps identity on the larger fragment** | one → big + small | ✅ pass — fragment records its parent |
| **Cloud over the lake is NOT a disappearance** | footprint fully obscured | ✅ pass — `not_observed`, identity kept |
| A visible empty footprint IS a disappearance | fully observable, no water | ✅ pass |
| Partial visibility below the floor → not observed | 20% observable | ✅ pass |
| No observability mask → the cautious reading | absence with no mask | ✅ pass — `not_observed` |
| An unseen lake is picked up again as itself | observed / unseen / observed | ✅ pass — one lake, not two |
| A `not_observed` date is a gap in the series | into `analysis.change` | ✅ pass — `None`, never interpolated |
| The proximity partition is disjoint | joint growth from two seeds | ✅ pass — no overlap, contested midline joins neither |
| A tracked series feeds the trend analysis | four growing dates | ✅ pass — Increasing |

**Gate status: NOT yet run.** "Lake upstream of the candidate identified and
tracked" needs imagery of a confirmed event.

### Open items at the Phase 8 gate

1. **No real barrier lake has been detected or tracked.** All of the above is
   synthetic.

2. **Two design errors were found only by testing, and both failed toward a
   false positive or a false negative rather than an obvious crash.** A
   barrier lake is connected to the river it dams, so component-level
   "upstream" tests qualify downstream lakes (`methods.md` 8.1); and two wide
   dilations either side of a blockage overlap enough to cancel, erasing the
   impoundment (`methods.md` 8.2). Both are recorded because the same traps
   would recur in any reimplementation.

3. **The tracker matches by overlap only.** A lake moving further than its own
   width between dates would not be matched. Not realistic at Sentinel
   cadence, but an assumption rather than a guarantee.

4. **`lake_width_m` truncates a wider lake.** 300 m is a convention for the
   valley scales targeted here and should be raised for broad valleys.

---

## 12. Phase 9 verification record

Test run: **512 offline passed, 0 failed**; 30 of them new in Phase 9.

| Check | Method | Result |
|---|---|---|
| **A gap is never interpolated** | clean series vs the same series with a gap row | ✅ pass — identical rate, endpoints and valid count |
| Gaps are counted and keep their reason | mixed series | ✅ pass — reported in `as_dict()` |
| A valid observation cannot lack an area | constructor guard | ✅ pass — refused |
| Expanding lake → Increasing | required scenario 7 | ✅ pass |
| Shrinking lake → Decreasing | synthetic series | ✅ pass |
| Unchanging lake → Stable | synthetic series | ✅ pass |
| **Too few observations → Unknown, not Stable** | 2 valid against a minimum of 3 | ✅ pass — "too little data is not evidence of stability" |
| **Cloudy-only window → Unknown, no crash** | required scenario 9, six gaps | ✅ pass — 0 valid, 6 gaps, no numbers |
| A stale series → Unknown, not Stable | last observation 90 days old | ✅ pass |
| Unknown carries no numbers | rate, absolute and percent change | ✅ pass — all `None` |
| Percent change from zero → `None` | first area 0 | ✅ pass — not infinity |
| Theil–Sen resists a corrupted endpoint | one point set to 900 | ✅ pass — slope stays ≈2.0 where the endpoint method gives 178.0 |
| Relative threshold scales with lake size | pond vs lake at the same m²/day | ✅ pass — Increasing vs Stable |
| An Unknown trend leaves the risk factor unavailable | into Phase 11 | ✅ pass — not scored as zero growth |

**Gate result: the specified gate passes.** "Time series with gaps handled
honestly" — gaps are recorded with reasons, excluded from the fit, proven not
to change the result, and an absence of data yields Unknown rather than
Stable.

### Open items at the Phase 9 gate

1. **No real trend has been measured, and the real data showed why that
   matters.** The two Sentinel-2 dates give 1.6005 km² then 1.2977 km² — a
   19% apparent loss in five days, which is not physically plausible. Pixel by
   pixel, **50.1%** of the lost water was unobservable on date 2 and the
   largest class among the rest is SCL 2 ("dark area pixels"), i.e. terrain
   shadow. The system reports **Unknown** and is right to. With
   `min_valid_observations` set to 2 it would have reported a confident
   "Decreasing" at about −60,000 m²/day. Detail in `methods.md` 9.4.

2. **A real series must be built from the Phase 4 fused mask**, not the Phase
   3 optical rule used for the measurement above, since shadow-driven
   shoreline loss between dates is exactly what Phase 4 suppresses. This needs
   per-date sun angles and Earth Engine access.

3. **Cloud fraction must be read alongside every area.** A 13%-cloudy scene
   passed the scene-level filter and still lost a fifth of the lake without
   any gap being declared. `AreaObservation` carries `cloud_fraction` for this
   reason, but nothing yet *acts* on it — a sharp area change against a rising
   cloud fraction should be treated as suspect.

4. **No significance test is applied.** With three to five observations
   Mann–Kendall is badly underpowered, and a p-value would imply authority the
   sample size does not support.

---

## 13. Phase 10 verification record

Test run: Phase 10's checks are part of the **640 offline passed, 0 failed**
suite; 31 tests cover the branch logic, 4 of them against real imagery.

| Check | Method | Result |
|---|---|---|
| **Required test 8 — a lake in the DEM epoch** | Tsho Rolpa, real DEM | ✅ **pass** — Branch B, `unavailable`, no number emitted |
| The DEM is provably flattened over the lake | standard deviation inside the lake | ✅ pass — **0.00 m** across 15 501 px |
| A zero height-error mask corroborates it | GLO-30 HEM inside the lake | ✅ pass — 0.00 m everywhere, i.e. no measurement made |
| **Dates alone would have chosen the wrong branch** | first-observed 2023 vs epoch end 2014 | ✅ pass — date rule says A, the DEM evidence correctly overrides to B |
| The Branch A formula here is buffer-dependent | 10 / 30 / 50 m shoreline rings | ✅ pass — 14.3 / 21.7 / 30.9 × 10⁶ m³, a 2.2× swing; none emitted |
| Branch A arithmetic is correct | hand-computable synthetic valley | ✅ pass |
| Uncertainty bounds bracket the estimate | DEM error + WSE spread | ✅ pass |
| Branches B and C emit no numbers | every depth/volume field | ✅ pass — `None`, never `0.0` |
| An empirical formula is refused | `branch_b_empirical_formula` set | ✅ pass — raises, naming what approval would require |

**Gate result: the specified gate passes.** "Branch logic tested; no
untraceable values" — and required system test 8 passes on real data.

### Open items at the Phase 10 gate

1. **Branch A has only ever run on synthetic data.** Every real lake met so
   far is Branch B. The end-to-end integration scene is its sole exercise.

2. **No ICESat-2 / SWOT cross-check.** Optional per the brief, needs a NASA
   Earthdata login. Until then the water surface elevation rests on the same
   DEM that Branch B distrusts.

3. **The flatness threshold is calibrated to this DEM product.** A DEM that
   does not flatten water, or one resampled before reaching the module, would
   need it revisited.

---

## 14. Phase 11 verification record

Test run: **441 offline passed, 0 failed**; 36 of them new in Phase 11. No
imagery is involved — this phase is scoring and reporting rules, tested on
hand-chosen inputs.

| Check | Method | Result |
|---|---|---|
| Every warning lists its factors | Section 9 requirement | ✅ pass — value, score, weight and contribution per factor, sorted by influence |
| Every warning carries the disclaimer | including at NORMAL | ✅ pass — asserted against `REQUIRED_DISCLAIMER_PHRASE` |
| Level wording is the brief's own | verbatim string comparison | ✅ pass |
| No level predicts failure | forbidden-word scan over all four levels | ✅ pass — no "will fail", "imminent", "failure expected", "collapse" |
| **Unavailable is not scored as zero** | volume measured-0 vs volume unavailable | ✅ pass — the unavailable case scores **higher**, as it must |
| Branch B reason travels with the gap | Section 8 reason text in the warning | ✅ pass — "DEM records water surface; no bathymetry" appears in the warning |
| Thin evidence is flagged | `data_coverage` below the floor | ✅ pass — `insufficient_data`, and "not evidence of safety" in the text |
| **Green is withheld on thin evidence** | symbol for a NORMAL at 9% coverage | ✅ pass — ⚪ not 🟢 |
| A real alarm is never muted | symbol for a CRITICAL at low coverage | ✅ pass — 🔴 retained |
| A disabled factor cannot move the score | rainfall at weight 0, 0 mm vs 500 mm | ✅ pass — identical scores |
| Growing lake raises concern | required scenario 7, scoring half | ✅ pass |
| Record maps to the database | `risk_assessments` columns (Section 10) | ✅ pass — round-trips through `factors_json` |

**Gate result: the specified gate passes.** "Factors listed per warning;
disclaimer present" — both are asserted by tests, including on the NORMAL
level where a disclaimer is most likely to be dropped.

---

## 15. Phase 12 verification record

Test run: **619 offline passed, 0 failed**; 37 of them new in Phase 12,
including four that render the real Streamlit script.

| Check | Method | Result |
|---|---|---|
| **The app runs** | `streamlit run app/dashboard.py` | ✅ HTTP 200, `/_stcore/health` ok, no errors logged |
| **The script renders without raising** | Streamlit `AppTest` | ✅ pass — no exception |
| All eleven Section 14 questions reach the page | count rendered questions | ✅ pass — exactly 11 |
| Every question answered even with no data | empty site view | ✅ pass — none blank |
| A Branch B depth shows its reason | Section 8 text on screen | ✅ pass — "no bathymetry" |
| A Branch A volume shows its bounds and caveat | rendered answer | ✅ pass |
| An Unknown trend shows why | reason on screen | ✅ pass |
| A trend states its gap count | "not interpolated" | ✅ pass |
| **A gap breaks the line** | prepared data and the figure object | ✅ pass — `None` in y, `connectgaps=False` |
| The figure reports its gap count | chart subtitle | ✅ pass |
| A single series carries no legend | dataviz rule | ✅ pass |
| Unavailable factors still appear | factor bar chart | ✅ pass — zero length, reason in the label |
| **Green is withheld on thin evidence** | `status_colour`, `marker_style` | ✅ pass — grey, labelled |
| An alarm keeps its colour | CRITICAL at low coverage | ✅ pass |
| **Every marker pairs symbol with words** | all four levels | ✅ pass — colour never alone |
| Every popup carries the disclaimer | popup HTML | ✅ pass |
| The disclaimer is on the page | rendered warnings | ✅ pass |
| A thin-evidence site is flagged on screen | TR-001 at 9% coverage | ✅ pass — "INSUFFICIENT DATA" |

**Gate result: the specified gate passes.** "Runs locally with
`streamlit run app/dashboard.py`" — verified by launching the server (HTTP 200,
healthy) and by rendering the script through `AppTest`, which is the stronger
check since Streamlit executes the script per session.

### Open items at the Phase 12 gate

1. **Rendered, not used.** Nobody has clicked through the dashboard. The gate
   check asserts what reaches the page; it does not assess whether the page is
   usable.

2. **No before/after imagery comparison.** The brief asks the dashboard for
   one. It needs raster tiles the pipeline does not yet export, so it is
   outstanding.

3. **One site in the demo database.** Multi-site behaviour — map centring,
   level counts — is covered only by unit tests.

4. **The status palette fails the categorical validator**, as documented for a
   status palette. The mitigation (symbol + text everywhere, never colour
   alone) is implemented and tested, and matters most for MONITOR vs HIGH
   RISK, the adjacent pair at normal-vision ΔE 13.6. Detail in
   `methods.md` 12.4.

5. **Streamlit installed without incident.** Smart App Control did not block
   it or `pyarrow` — worth recording, since the install was expected to be the
   risk. matplotlib's renderer and scipy remain affected.

---

## 16. Phase 13 verification record

Test run: **640 offline passed, 0 failed**; 21 of them new in Phase 13,
including two that parse the rendered PDF rather than the HTML behind it.

| Check | Method | Result |
|---|---|---|
| **A PDF report for one site** | TR-001 from the monitoring database | ✅ **pass** — 156 KB, 3 pages, via headless Edge |
| The PDF carries the disclaimer | text extracted with `pypdf` | ✅ pass — in the body *and* the page footer |
| The PDF states INSUFFICIENT DATA | TR-001 at 9% coverage | ✅ pass |
| A Branch B reason reaches the PDF | Section 8 text | ✅ pass — "no bathymetry" |
| Value types are shown | Section 14 requirement | ✅ pass — classified / unavailable labelled per row |
| Green is withheld on thin evidence | NORMAL at 9% coverage | ✅ pass — ⚪ and grey, not 🟢 |
| An alarm keeps its colour | CRITICAL at low coverage | ✅ pass |
| Gaps are labelled in the observation table | a `None` area row | ✅ pass — "gap", "never interpolated" |
| The report says levels are not predictions | body text | ✅ pass |
| Provenance is recorded | config hash, code version | ✅ pass — code version "unknown (not a git working tree)" |
| HTML is escaped | a `<script>` in a site code | ✅ pass — autoescape on |
| A missing PDF engine does not lose the report | both engines stubbed out | ✅ pass — HTML written, reason reported |
| **Report and dashboard cannot disagree** | both render `build_site_view` | ✅ pass — one implementation, two renderers |

**Gate result: the specified gate passes.** "PDF report for one site;
validation results documented" — `outputs/reports/TR-001_report.pdf` exists
and its content is verified by parsing the PDF itself, and this document is
the validation record.

### Finding: WeasyPrint cannot run on this machine, and that is not fixable here

The brief names `jinja2` + `weasyprint`. WeasyPrint **installs** cleanly with
pip and then **cannot import**: it binds to GTK/Pango native libraries that
Windows does not ship, failing with `cannot load library 'libgobject-2.0-0'`.
This is the documented Windows situation for WeasyPrint, distinct from the
Smart App Control problem recorded in §8 — installing the GTK runtime is a
system-wide change that belongs to the machine's owner, not to a build script.

So PDF generation is engine-agnostic: WeasyPrint is preferred when it imports,
and otherwise the HTML is printed by **headless Chromium** (Edge or Chrome,
both already on this machine), which needs no installation. The engine used is
recorded on the result. The HTML is always produced by Jinja2 alone, so a
report exists even with no PDF engine at all — and a test stubs both engines
out to prove the HTML survives.

One trap worth recording: headless Chromium resolves a **relative**
`--print-to-pdf` path against its own working directory and reports only
"cannot find the path specified". The path must be absolute.

### Open items at the Phase 13 gate

1. **The PDF is produced by Chromium, not WeasyPrint.** Output differs
   slightly from what the brief's stack would render, and a machine with the
   GTK runtime installed would take the WeasyPrint path instead. Both are
   supported; neither is pinned.

2. **One site, and no figures.** The report carries tables and text but no
   map or chart images — embedding them needs raster export the pipeline does
   not yet do. It is the same gap as the dashboard's missing before/after
   comparison.

3. **No multi-site or summary report.** Only per-site reports exist.

---

## 17. Storage layer verification record

Test run: **482 offline passed, 0 failed**; 41 of them new. No imagery
involved except in the end-to-end check.

| Check | Method | Result |
|---|---|---|
| All six required tables exist | Section 10 minimum | ✅ pass |
| Section 10 value-type vocabulary accepted | all six types inserted | ✅ pass |
| An unknown value type is refused **by SQL** | raw INSERT bypassing the wrapper | ✅ pass — `IntegrityError` |
| **An unavailable estimate cannot carry a volume** | store Branch B with the 14.3 M m³ figure from §10.3 | ✅ pass — refused |
| An unavailable estimate cannot carry a depth | Branch B with `mean_depth_m` | ✅ pass — refused |
| Branch B or C cannot be marked `estimated` | both attempted | ✅ pass — refused |
| Branch A may carry an estimate | full Branch A row | ✅ pass — stored |
| Foreign keys enforced | observation against a missing site | ✅ pass — refused |
| Phase 10 output stores as emitted | `as_record()` straight into the table | ✅ pass |
| Phase 11 output stores as emitted | `as_record()` straight into the table | ✅ pass |
| **A thin-evidence level keeps its caveat** | NORMAL at 9% coverage | ✅ pass — `insufficient_data = 1`, `data_coverage = 0.09` |
| Gaps stay gaps | two observations a month apart | ✅ pass — two rows, nothing interpolated |
| `first_detected` survives an update | upsert twice | ✅ pass |
| Provenance is traceable | `run_id` on stored values | ✅ pass |
| `code_version` outside a git tree | no `.git` present | ✅ pass — `None`, not faked |
| `code_version` from refs and packed-refs | synthetic `.git` layouts | ✅ pass |

**End-to-end check.** Detection → depth/volume → risk → storage was run on the
real Tsho Rolpa stack, writing `outputs/phase_db_demo.sqlite`: one run, one
site (TR-001, 1.6005 km², 4545.5 m), one observation with full provenance, one
Branch B estimate with NULL volume and its reason, and one risk assessment
flagged `insufficient_data`.

### Open items at the storage gate

1. **No migration mechanism.** `initialise()` is `CREATE TABLE IF NOT EXISTS`;
   changing the schema against an existing database needs a manual migration.

2. **Only two tables are currently written by real code.** `observations`,
   `depth_volume_estimates` and `risk_assessments` have producers;
   `landslide_events` waits on Phase 5's gate and `sites` is populated by hand
   until Phase 7 creates blockage candidates.

3. **The `level` column is unconstrained text**, deliberately — the four
   strings are fixed in `analysis.risk` and duplicating them in SQL would give
   them two places to drift.

### Open items at the Phase 11 gate

1. **The score is not a probability and the weights are not calibrated.** No
   published weighting exists for this factor set, and no outcome dataset
   exists against which to fit one. The defence is traceability, not
   authority: every level can be traced to the factor contributions that
   produced it. Detail in `methods.md` 11.4.

2. **Three of the five input factors are not yet produced.** Blockage
   confidence (Phase 7), lake growth rate (Phase 9) and new landslide area on
   real imagery (Phase 5's gate) are all still to come, so the phase has been
   exercised only on hand-chosen inputs. Its integration is untested.

3. **The published DBI index is not implemented**, deliberately — it needs dam
   height and volume that Branch B makes unmeasurable, and the exact formula
   was not verified at source. See `methods.md` 11.5.

4. **Rainfall is absent rather than zero-risk.** Weight 0 means it cannot move
   the score, and it is listed under "Not measured" in every warning. Wiring
   in a precipitation source would be a genuine improvement, not a
   formality.

### Open items at the Phase 4 gate

1. **`p_water` is not a calibrated probability.** It is a transparent evidence
   score passed through a softmax. No reliability diagram has been produced and
   none can be without labelled data, so the number must not be read as "there
   is an 80% chance this is water". Phase 6 is where labels arrive.

2. **Persistence did not do the job Section 7.3 implies.** The two available
   dates share an overpass geometry, so the terrain shadow barely moves between
   them (shaded-relief IoU **0.933**) and persistence cannot discriminate
   shadow over this window — it discriminates cloud and speckle. Demonstrating
   the intended behaviour needs dates months apart at different solar
   elevations. Detail in `methods.md` 4.5.

3. **The SAR term still rests on an unreliable threshold** (§3.5). The fusion
   contains the damage with the layover/shadow gate and a modest weight, and
   the ablation shows dropping SAR entirely changes the totals little — but
   that is containment, not repair. Radiometric terrain correction is still the
   right fix, and it is the one place where this phase's evidence is weaker
   than it looks.

4. **One site, one scene pair.** Everything above is measured at Tsho Rolpa on
   a single date pair. It is a gate check, not a validation. A second site —
   ideally one with no lake at all, for required test 1 — would test the
   method rather than its fit to this scene.

5. **Smart App Control is now actively disruptive, not merely a nuisance.**
   During this phase it intermittently blocked `scipy`, `numpy.random` and
   numpy's BLAS: one full test run took **3 h 29 min and reported 97 spurious
   failures**, and the same suite passed in 81 s once the block lifted. The
   blocks appear and clear without any change to the code. Mitigations applied:
   `preprocessing.cloud_mask.dilate` now has an exact pure-numpy fallback
   (`dilate_square`, tested against scipy), and the Phase 4 run avoids BLAS.
   **Not** mitigated: `preprocessing/terrain.py` and `preprocessing/sar.py`
   still import scipy and will crash the process outright when it is blocked.
   This is the decision the README leaves to the repository owner — disable
   Smart App Control, or move to WSL2 — and it now has a measurable cost.

### Open items at the Phase 3 gate

1. **Single-scene Sentinel-1 amplitude thresholding does not work in this
   terrain, and a geometry mask alone will not fix it.** The derived threshold
   (−10.42 dB, descending) passes the bimodality test yet selects **47.6% of the
   AOI** as water; 27.2% of the AOI is radar layover or shadow and 42.3% of the
   SAR "water" lies inside it. Re-deriving the threshold from geometrically
   reliable pixels only still gives 37.5%. The failure is therefore radiometric
   as well as geometric, and needs radiometric terrain correction or
   multi-temporal persistence. **This is a design input to Phase 4**, and the
   reason `combine` defaults to `intersection`. Full detail in `methods.md` 3.5.

2. **Caution on the headline number.** The 1.578 km² agreement is
   a plausibility check on **one date**, not an accuracy assessment: the
   published 1.537 km² predates these 2023 scenes, Tsho Rolpa has been growing,
   and the GLO-30 water-body mask is an independent observation from the
   2011–2014 DEM epoch rather than ground truth. No error bar is claimed.

3. **Required system test 1 has no real site yet.** "Normal mountain terrain →
   no water" currently passes only on synthetic arrays. It needs a documented
   snow-free, water-free Himalayan AOI to be a real test; the default AOI is
   42% snow/ice and contains a lake, so it cannot serve.

4. **The snow screen is a threshold on one band, and will have a cost.** NIR <
   0.11 reflectance is cited and measures well here, but it will also reject
   genuinely turbid or very shallow water, which is brighter in NIR than clear
   deep water. Barrier lakes dammed by fresh landslide debris are exactly the
   case where high turbidity is expected (Phases 7–8), so this threshold must be
   re-examined there rather than assumed to transfer.

5. **Matplotlib's renderer is blocked on this machine.** `savefig` crashes with
   `STATUS_DELAY_LOAD_FAILED` (0xC06D007F) under Windows Smart App Control in
   enforcement mode — the recurrence the README anticipated. Colormap lookup is
   pure numpy and still works, so Phase 3 figures are composed with PIL instead.
   Unresolved at the library level; it will affect Phases 12–13.

### Open items at the Phase 2 gate

1. **Observed brightness does not validate the shadow mask in this terrain, and
   this is a real property of the scene rather than a defect.** A stricter check
   than the gate required — does the mask predict Sentinel-2 brightness? —
   fails: `r(illumination, brightness) = -0.18`, high-pass `r ~ +0.02` at all
   scales. Shadow-algorithm error, orientation error, misregistration and
   DEM-export error were each ruled out by direct test; most decisively, the
   exported DEM matches **NASADEM at r = 0.999**, and NASADEM reproduces the
   same weak correlation. At 4150-6600 m with 20-40% snow, reflectance is
   governed by surface material and by diffuse skylight multiply scattered
   between snow surfaces, not by direct-beam geometry. Full detail in
   `methods.md` 2.4.

   **This is an input to Phase 4, not a blocker for it**: the Section 7.3 rule
   "dark optical pixel + in terrain shadow -> ..." must not use darkness as a
   proxy for being shadowed in snow-dominated scenes.

2. **Refined Lee is not implemented.** The brief allows "Refined Lee or a focal
   median"; Lee (1980) and a focal median are implemented and configurable,
   which satisfies the requirement. Refined Lee can be added if wanted.

3. **Cloud Score+ was initially suspected of being broken and is not.** Its `cs`
   values never drop below 0.71 over this AOI, which looked wrong against the
   scene's 27.68% `CLOUDY_PIXEL_PERCENTAGE` — but that property describes the
   whole 110 km MGRS tile, while the 8 km AOI genuinely is clear (SCL cloud
   5.26%). Recorded so the same false alarm is not re-raised.

### Open items at the Phase 1 gate

1. **QGIS has not been opened.** The gate says "GeoTIFFs open in QGIS". They have
   been verified to open in **rasterio** with correct CRS, transform, dtype,
   band descriptions and embedded tags, which is a strong proxy — but confirming
   in QGIS itself is a manual step for the repository owner.
2. **`altimetry.py` is not implemented.** ICESat-2 / SWOT is optional in the
   brief and belongs to Phase 10's water-surface-elevation cross-check; it is
   deliberately deferred rather than stubbed.
3. **Sentinel-1 coverage of the August 2014 Jure event is still unverified.**
   The guards refuse pre-mission windows, but the specific question in the brief
   — whether S1 covered Nepal on that date — has not been asked of the catalog.
   It belongs with the Jure work in Phase 5.

### Open items at the Phase 0 gate

1. **`COPERNICUS/DEM/GLO30` is deprecated**, superseded by
   `COPERNICUS/DEM/GLO30_2024_1`. This is not cosmetic: the deprecated
   collection exposes only a **placeholder** acquisition date (2006-01-01),
   while the replacement carries real per-tile acquisition windows. Measured
   over this AOI, the replacement gives a DEM epoch of **2011-01-05 →
   2014-09-08**, which is the hinge of the Branch A / Branch B decision in
   Section 8. Switching would turn that hinge from an assumed constant into a
   queried, per-AOI value. **A decision is required**; `config.yaml` is
   unchanged pending it. Detail and the Phase 1 mosaicking caveat are in
   `methods.md` §0.6.

2. **Windows Smart App Control is enabled in enforcement mode** on the
   development machine (`VerifiedAndReputablePolicyState = 1`). It blocked the
   newest `pandas` binaries from both conda-forge and PyPI. Worked around by
   installing `pandas==2.2.3`, a build with sufficient OS reputation. This is a
   machine-level constraint rather than a code defect, but it is recorded here
   because it is likely to recur for `whitebox` (Phase 2), `pytorch` (Phase 6)
   and `weasyprint` (Phase 13). See README, "Windows Smart App Control".

---

## 18. End-to-end integration record

Test run: **582 offline passed, 0 failed**; 15 of them the new integration
suite, plus 3 pinning the degradation fix it prompted.

A complete synthetic landslide-dam event run through every phase in order:

| Stage | Result |
|---|---|
| Phase 5 change | 90 px, 1 polygon |
| Phase 7 blockage | `ND-001` with obstruction evidence |
| Phase 8 barrier lake | 34,600 m², expanding +130.7% |
| Phase 8 tracking | one stable ID across 4 dates, no fragmentation |
| Phase 9 trend | **Increasing**, +773.3 m²/day, 0 gaps |
| Phase 10 depth/volume | **Branch A**, 0.173 × 10⁶ m³ [0.133–0.213] |
| Phase 11 risk | **MONITOR**, score 0.40, coverage **100%** |
| Storage | all five tables populated and read back |

**Two defects found, both of which passed every unit test:**

1. **Phases 7 and 8 could not be chained.** `BlockageCandidate` did not carry
   the blockage site mask that `find_barrier_lakes` requires. Fixed:
   candidates now carry `site_mask` and `landslide_mask`.

2. **A uniform scene crashed Phase 5.** The MAD-derived threshold raises when
   a scene has no spread, and the exception escaped `detect_change`. Fixed:
   such a signal is recorded unavailable with its reason and the run
   continues, consistent with the project's rule everywhere else.

**One methodological finding:** the cited slope gate (`min_slope_deg = 15`,
Notti et al. 2023) is correct for shallow-landslide *source* areas and wrong
for landslide *dams*, whose deposits lie on the flat valley floor. Left at
15° it splits a river-blocking landslide into two components and yields two
duplicate dam candidates for one event. Detail in `methods.md` 5.9.

**Milestones:** this is the first exercise of depth **Branch A** anywhere in
the project (every real lake so far has been Branch B), and the first time
Phase 11 has run at 100% data coverage.

### Open items at the integration gate

1. **Synthetic only.** The scene is built to be detectable: no cloud, shadow,
   snow, speckle, or terrain complexity. It validates the *interfaces*, not
   the accuracy of any phase.

2. **Phases 5, 7 and 8 remain unvalidated on real imagery.** Three deferred
   gates, now with their interfaces proven but their science untested.

3. **The integration config differs from the shipped default** in its slope
   gate, for the reason in item 3 above. A deployment aimed at river blockage
   needs that change made deliberately.

---

## 20. Phase 5 verification record — Baige landslide dam, 2018

> **Magnitudes superseded.** This record was produced from the unfused Phase 3 water mask. The chain was re-derived on Phase 4 fused water in §25, which is authoritative for every number below. The findings and the reasoning stand.

**Gate check (brief, Phase 5):** *change map produced for a documented event.*
**Status: passed.** Read §C.1 below before quoting any number from it.

### Event and data

| | |
|---|---|
| Event | Baige landslide dam, Jinsha River, Jiangda County, Tibet |
| Failures | 2018-10-10 (first), 2018-11-03 (second) |
| Published coordinate | 98.70499 E, 31.08234 N — the **landslide source area**, not the blockage point; see §C.0 |
| Sources | §2.2 above (volume estimates conflict between sources; both recorded) |
| Site overlay | `config/sites/baige_2018.yaml` |
| AOI | point + 3,000 m buffer ≈ 28 km² (6,000 m was tried first: 111.7 km² broke the brief's "tens of km²" budget and the 27 MB export did not finish) |
| Optical pair used | S2 47RMQ 2018-11-02 → 2018-11-09 |
| SAR pair used | S1 2018-10-27 → 2018-11-08, relative orbit 99, ASCENDING |
| DEM | Copernicus GLO-30 `GLO30_2024_1`, source epoch 2011–2014 |

**The first dam was not attempted.** No Sentinel-2 scene in the window passes
the cloud filter before 2018-10-10, so no optical pre-event baseline exists.
Recorded in the run output as a gap.

### Result

Dam-tuned slope gate (>1°, per methods §5.9), post-date water excluded:

| | value |
|---|---|
| assessable pixels | 180,835 |
| changed pixels | 2,652 |
| change area | 0.2652 km² |
| polygons | 50 |
| largest polygon | 13,200 m² |
| total polygon area | 117,300 m² |

Cited slope gate (>15°, Notti et al. 2023): 2,301 px / 0.2301 km² /
45 polygons / largest 8,300 m².

Signal availability on the dam-tuned run — NDVI drop flagged 9.5% of
assessable pixels, brightness increase 4.8%, SAR change 2.7%; 1.5% satisfied
two of three and became the change map. Exclusions: 144,193 px invalid on the
post date (cloud / scene edge), 4,491 px snow on the post date, 555 px snow on
the pre date, 8,718 px **water on the post date**, 35,013 px below the slope
minimum.

Derived thresholds for this scene pair, from the robust MAD rule (methods
§5.5): brightness increase ≥ 0.0550 (median 0.0140 + 3 × MAD σ 0.0137);
|SAR change| ≥ 4.655 dB (median −0.654, 3 × MAD σ 1.552). The NDVI threshold
is the cited fixed −0.15.

### Positional agreement with the published landslide coordinate

| distance from published coordinate | polygons | area |
|---|---|---|
| ≤ 250 m | 2 | 2,200 m² |
| ≤ 500 m | 4 | 15,200 m² |
| ≤ 1,000 m | 8 | 20,200 m² |
| ≤ 2,000 m | 12 | 27,000 m² |

Nearest polygon: **1,000 m² at 132 m.** Of the 117,300 m² total, **13.0%**
lies within 500 m of the coordinate. Read §C.0 before interpreting these:
the coordinate is the source area on the slope, so this measures agreement
with the **landslide**, not with the dam.

Artifacts: `outputs/baige_2018_phase5_tight.json` (the result),
`outputs/baige_2018_phase5.json` (the wide-pair run, kept for comparison),
`outputs/baige_2018_verification.json`,
`outputs/baige_2018_water_vs_change.json`,
`outputs/baige_2018_acquisition.json`, `outputs/baige_2018_scenes.json`,
`outputs/maps/baige_2018_landslide_change.geojson`.

### Findings that changed the system

1. **The impounded lake was being reported as landslide.** New open water
   trips two of the three signals unaided: NDVI collapses because water
   absorbs NIR, and SAR collapses because water is specular. On the first run
   28.7% of the change map was newly detected water and the largest polygon
   was 51.3% new water.
2. **Excluding only *newly* wet pixels was not enough.** The reach just
   upstream of a dam is already river, so it is never "new", yet it deepens
   and widens into a lake and trips both signals anyway: NDVI −0.510 →
   −0.965 and VV −10.6 → −22.8 dB at Baige. The gate became
   `exclude_water_on_post_date` — a deposit cannot be under water on the date
   it is observed, whatever it was before. 8,718 px were excluded on that
   basis.
3. **Scene spacing mattered more than any threshold.** The widest available
   pair (2018-11-02 → 2018-11-22) let the November snow line descend: 29,785
   px of post-date snow against 555 pre-date, and the residual snow edge
   dominated the map at 0.6355 km² over 125 polygons. The tight 7-day pair
   cut post-date snow to 4,491 px and the map to 0.2652 km².
4. **A drained channel is still flagged, and this is accepted.** The largest
   surviving polygon (13,200 m², 3.6 km from the dam, 4° slope) runs the
   *mirror* signature: NDVI −0.401 → −0.021 and VV −13.8 → **−6.4** dB, a
   7.4 dB *rise*. That is exposed river bed downstream of the blockage — dry
   gravel is both brighter and rougher than the water it replaced, so
   brightness-increase and SAR-change agree. It is not screened out because a
   deposit that dams a river *sits on the former channel*, so excluding
   pre-date water would delete the dam itself. Separating "bed exposed by a
   blockage" from "bed buried by debris" is positional, not spectral, and
   belongs to Phase 7 — which already treats downstream water loss as
   obstruction evidence, making these pixels evidence *of* the dam even though
   they are not debris.

Supporting water measurements on this pair (Phase 3 detector): water 0.8045
km² pre → 0.8718 km² post, with 0.3757 km² **gained** and 0.3084 km²
**lost**. The direction was measured, not assumed: gained water has a median
DEM elevation of 2913.8 m against 2867.0 m for lost water, so the gain sits
**46.8 m higher — upstream** of the loss, which is the impounded-above /
drained-below signature Phase 7 looks for. (Elevations are compared between
the two water sets, not against the published coordinate, which is 471 m
above the river and so cannot order them.)
Artifact: `outputs/baige_2018_water_direction.json`.

### C.0 — Finding: the published coordinate is not the dam

The coordinate 98.70499 E, 31.08234 N, carried from the literature into
`config/sites/baige_2018.yaml`, was used throughout as "the dam". Checking it
against the DEM shows it is not:

| | value |
|---|---|
| DEM elevation at the coordinate | **3,373.9 m** |
| slope at the coordinate | **52.9°** (median 41.3° within 150 m) |
| local relief within 150 m | 241 m |
| Jinsha water-surface elevation (median, pre-event) | 2,870.3 m |
| horizontal distance to the nearest water pixel | **626 m** |
| drop from the coordinate to the river | **471 m** |

A 53° slope 471 m above the water is a valley side, not a channel. The
coordinate marks the **landslide source area or body** on the right bank —
consistent with the sources, which describe the event as a right-bank
failure and publish a landslide location, not a dam-crest location. The
blockage itself is in the channel roughly 600 m away and several hundred
metres lower.

**Consequences, all of them already applied above:**

1. "Distance to the published dam" is really **distance to the published
   landslide**. The 132 m nearest polygon and the 13.0%-within-500 m figure
   measure agreement with the source area, which is what a landslide change
   detector should find — so the result stands, but under a different label.
2. It explains why the cited 15° slope gate performed as well as it did here:
   the terrain the coordinate sits on is steep, exactly the source-area
   geometry Notti et al. calibrated for. It does **not** weaken methods §5.9 —
   the deposit on the valley floor is still flat, and still cut by the gate.
3. Upstream / downstream could not be ordered against this coordinate, since
   it lies above both. The gained and lost water sets were compared against
   each other instead.
4. **Phase 7 needs a channel location, which this is not.** The blockage point
   must be derived from the data — the boundary between the gained (upstream)
   and lost (downstream) water — rather than taken from the overlay.

Artifact: `outputs/baige_2018_coordinate_check.json`.

### C.1 — What this result does and does not establish

**Does:** the method, given no prior about where the landslide is, puts
detected change 132 m from the published coordinate, using real Sentinel-1
and Sentinel-2 imagery of a documented landslide dam, with cited thresholds
and a recorded config hash. It also recovers the obstruction signature —
water gained upstream, water lost downstream — without being told where the
channel is blocked.

**Does not:**

- **No accuracy is claimed.** No per-pixel reference mask for the Baige
  deposit was available here, so **IoU, precision and recall are unmeasured.**
  Distance-to-published-point and area fractions are all the evidence
  supports.
- **87% of the flagged area is not the landslide.** It is drained channel,
  residual snow edge, and other seven-day change. The published event is
  *not* the largest polygon in the map.
- **The blockage point itself was never located**, only the source area and
  the water change either side of it. Doing so is Phase 7's job and has not
  been run.
- **The polygons at the dam are small and fragmented** — 4 polygons totalling
  15,200 m² within 500 m. This is the predicted consequence of methods
  §5.9: the slope gate and the water gate both cut into a deposit that lies
  flat on a valley floor beside water.
- **One event, one date pair, one site.** Tibet, not Nepal. Nothing here
  generalises to the Himalayan valleys the project targets.
- **The first dam is unprocessed** for want of a clear pre-event scene, so the
  better-documented of the two failures was not tested.

### Open items at the Phase 5 gate

1. **No ground truth.** Hand-digitising the Baige deposit from the 2018-11-09
   scene in QGIS would make IoU reportable and is the single highest-value
   next step for this phase.
2. **The Nepal event (Lhende / Rasuwa, §2.1) is still unprocessed** — no
   published coordinate has been confirmed, so no site overlay exists.
3. **The slope gate remains a two-value problem** (methods §5.9). The shipped
   default is the cited 15°; a blockage deployment needs it near zero. No
   single value serves both deliverables.
4. **Thresholds were not calibrated per AOI.** Notti et al. state their NDVI
   threshold "does not have a fixed value" and is set by an operator after
   visual assessment. The cited −0.15 was used as-is.
5. **Phases 7 and 8 have not been run on this data**, although it shows the
   obstruction signature they look for.
6. **The site overlay's coordinate needs relabelling in any downstream use**
   (§C.0). It is a valid landslide location and a poor dam location; Phase 7
   must derive the channel blockage point from the data instead.
7. **The gate-run scripts are not in the repository.** The acquisition, Phase 5
   run, verification, water-vs-change, flow-direction and coordinate checks
   were driven by throwaway scripts in a session scratchpad. The JSON artifacts
   they wrote are in `outputs/`, but `outputs/` is gitignored and the scripts
   are gone, so **this record is not reproducible from the repository alone.**
   The brief's folder structure has no home for run scripts; adding one is a
   structure change and needs approval.

---

## 21. Phase 7 verification record — Baige landslide dam, 2018

> **Magnitudes superseded.** This record was produced from the unfused Phase 3 water mask. The chain was re-derived on Phase 4 fused water in §25, which is authoritative for every number below. The findings and the reasoning stand.

**Gate check (brief, Phase 7):** *candidate found at a confirmed validation
event.* **Status: passed** — ND-005. Read §C.2 before quoting it.

### Inputs

| | |
|---|---|
| Landslide mask | the Phase 5 dam-tuned change map, 2,652 px, read from `data/processed/baige_arrays.npz` — not recomputed, so Phase 7 is tested on the output reviewed at §20 |
| Stream network | derived from the Baige DEM, 13,202 px, 132 km of channel, drainage density 3.68 km/km² at `stream_threshold_cells: 500` |
| Water masks | Phase 3 optical, 8,045 px pre → 8,718 px post |
| Flow accumulation | D8, used to order upstream from downstream |
| Published coordinate | **not passed to the detector**; used only afterwards to measure where candidates landed |

**Stream-network check:** 67.3% of observed pre-event water lies within 30 m of
a derived stream. The shortfall is expected — the derived line is the thalweg
while the Jinsha is wider than the 70 m corridor tested — but it is a measured
agreement, not an assumption.

### Finding: Phase 7 bypassed Phase 5's own minimum area

The first run gave **153 candidates for one dam**; **76 were a single 10 m
pixel** and 18 scored confidence 1.000.

Phase 5 applies a 1,000 m² floor to its polygons; Phase 7 reads the raw change
mask and so never applied it. Because obstruction evidence is measured over a
500 m reach rather than per-polygon, a one-pixel fragment beside a blocked
river inherits the real dam's evidence and scores on it.

Fixed by `detection.blockage.min_landslide_area_m2`, defaulting to Phase 5's
floor. Result: **153 → 14 candidates.** Four tests pin it, including one that
proves the identical pixel scores > 0.5 when the floor is dropped to zero, so
the rejection is demonstrably the area gate and not weak evidence.

### Result — 14 candidates

Classified by DEM elevation at the centroid (in channel = within 40 m of the
2,870 m pre-event water surface) and by whether water was impounded:

| reading | candidates |
|---|---|
| **dam-like** — in channel, new upstream water | **3**: ND-005, ND-004, ND-007 |
| drained reach — in channel, nothing impounded | 6: ND-009/010/011/012/013/014 |
| off channel — hillside debris | 5: ND-001/002/003/006/008 |

**ND-005 is the detection:**

| | value |
|---|---|
| confidence | **1.000** |
| centroid | 98.71291 E, 31.08365 N |
| centroid elevation | **2,871 m** — the pre-event water surface to within 1 m |
| distance to published source area | 770 m (the source area is itself 626 m from the channel) |
| distance to stream | 10 m |
| landslide area | 1,000 m² |
| channel narrowing | 42 → 0 water px in the channel zone |
| downstream water loss | 16,100 m² |
| new upstream water | 24,400 m² |
| evidence dates | 2018-11-02 → 2018-11-09 |

All four evidence types present. The nearest candidate by distance alone is
ND-006 at 703 m, but it sits 52 m above the river, so it is hillside debris
rather than a blockage — distance alone would have picked the wrong one.

### Finding: the confidence score ranks a drained reach above a real dam

The six drained-reach candidates score **0.625**. ND-004 — genuinely in the
channel with water impounded behind it — scores **0.500**.

A drained reach collects `intersects_stream` (1.0) + `channel_narrowing` (2.0)
+ `downstream_water_loss` (2.0) = 5/8. A dam showing only impoundment
collects `intersects_stream` (1.0) + `new_upstream_water` (3.0) = 4/8. Two
signals that a blockage *has already drained* outrank the one signal that
water is *being held back now*.

`new_upstream_water` is the only factor separating a forming dam from a
drained channel, and summing it with factors a drained channel also satisfies
dilutes precisely the information that matters. The brief's Section 7.6 says
"and/or", so requiring upstream water would change the stated semantics and is
**not** changed here. It is open item 2 below.

The run does confirm why the brief requires every candidate to publish its
factors: **the factor list carries the discriminating information and the score
does not.**

Artifacts: `outputs/baige_2018_phase7.json`,
`outputs/baige_2018_phase7_verification.json`,
`outputs/baige_2018_streams.json`,
`outputs/maps/baige_2018_blockage_candidates.geojson`,
`data/processed/baige_phase7.npz`, `data/processed/baige_hydro/`.

### Correction, from the Phase 8 run

The "dam-like" classification above used elevation at each **landslide
polygon's centroid**. ND-001's centroid sits 78 m above the river, so it was
called off-channel — but the stream pixels it touches lie at 2,906–2,915 m on
the Jinsha main stem (332,506 cells of accumulation), and Phase 8 shows it is
the candidate holding the impoundment (§22). A landslide on a valley side has
its centroid on the valley side by construction. The candidate list is
unchanged; the reading of it here is not reliable and should not be reused.

### C.2 — What this result does and does not establish

**Does:** given no prior about where the dam is, Phase 7 raises a
full-confidence candidate at the pre-event water surface to within 1 m,
770 m from the published landslide source area, with all four obstruction
signals present, on real Sentinel-1/Sentinel-2 imagery of a documented dam.

**Does not:**

- **No accuracy.** No reference dam outline exists, so no precision or recall.
  ND-005's agreement is a distance and an elevation.
- **14 candidates for one event is still over-detection.** Nine of the eleven
  others are explainable — six drained reach, five off-channel — but the system
  labels them all `Potential Landslide Dam` without distinguishing them.
- **The elevation and upstream-water test that separates them is analysis in
  this document, not code.** A user of the dashboard would see 14 candidates
  and the drained ones ranked above a real one.
- **One event, one date pair, Tibet.**

### Open items at the Phase 7 gate

1. **Over-detection is not solved, only reduced.** Fragments of one deposit
   along one reach should merge into a single candidate; they do not. A
   reach-based deduplication is the obvious next step and is not implemented.
2. **The weighting mis-ranks, and fixing it needs a decision.** Either
   `new_upstream_water` becomes required (which departs from the brief's
   "and/or"), or the three signals stop being summed into one scalar. Both are
   architecture changes and need approval.
3. **No in-channel test.** "Is this candidate at river level?" proved to be the
   test that separated a real dam from hillside debris 703 m away, and it
   exists only in the verification script.
4. **The stream threshold was not calibrated.** 500 cells gives 3.68 km/km²,
   which is dense; it was not varied to see how the candidate count responds.
5. **No ground truth**, as at the Phase 5 gate.

---

## 22. Phase 8 verification record — Baige barrier lake, 2018

> **Magnitudes superseded.** This record was produced from the unfused Phase 3 water mask. The chain was re-derived on Phase 4 fused water in §25, which is authoritative for every number below. The findings and the reasoning stand.

**Gate check (brief, Phase 8):** *lake upstream of the candidate identified and
tracked.* **Status: passed** — a 602,200 m² lake behind ND-001, tracked under
one identity across four dates. Read §C.3 before quoting any area.

**This record replaces an earlier version** that reported a 160,000 m² lake
behind ND-007. That result, its eight churning lake IDs, and its 150×
search-radius sensitivity were all artefacts of the defect below. Do not quote
them. The superseded artifacts are `outputs/baige_2018_phase8.json` and
`outputs/baige_2018_phase8_tracking.json`.

### Finding: "upstream" was not "on the same stream"

Section 7.7 requires the lake to be upstream **on the same stream**. The
module took every stream pixel in a 4 km square box with accumulation below
the site's — so every small tributary in the box counted as upstream, whether
or not it drained to the blockage. The reported reach jumped from rows
154–289 (11-09) to rows 424–598 (11-19); the two dates' lakes overlapped by
**exactly 0 px** while 40% of the water persisted.

Fixed by tracing the reach along the stream network from the blockage, so
`upstream_search_m` is now an along-channel distance.

### Finding: a blockage straddling a confluence

The upstream reference was the site's **median** accumulation. The ND-007
site spanned 20,817–56,484 cells; the median of 20,856 put the main stem on
the downstream side. Now the site's **maximum** — its outlet — which is safe
only because the reach is traced.

Five tests pin the two fixes.

### Which candidate holds the lake

| candidate | site accumulation (max) | gained water upstream | lake |
|---|---|---|---|
| **ND-001** | **332,506** (AOI max 334,834) | **215,400 m²** | **602,200 m²** |
| ND-004 | 174,278 | 227,200 m² | 369,900 m² |
| ND-005 | 135,855 | 57,600 m² | 42,200 m² |
| ND-007 | 56,484 | 400 m² | none |

Independent check, using no flow-accumulation reasoning: water gained
between 11-02 and 11-09 has a median DEM elevation of 2,914 m, water lost
2,867 m, so the gain is 47 m upstream of the loss.

ND-001 and ND-004 share one reach and are **not independent detections**.

### Result

Lake behind ND-001, 2018-11-09: **602,200 m²**, baseline 386,800 m²,
**215,400 m² new, +55.7%**, DEM median 2,887 m.

| date | observable (scene) | BL-001 | event |
|---|---|---|---|
| 2018-11-02 | 100.0% | — | pre-event |
| 2018-11-09 | 59.8% | 602,200 m² | appeared |
| 2018-11-19 | 60.9% | 421,900 m² | continued |
| 2018-11-22 | 100.0% | 431,500 m² | continued |

**One lake identity across four dates**, against eight before the fix.

**The fall after 11-09 is measured, not cloud.** The 11-09 footprint is 100%
observable on both later dates; 69.5% of it is wet on 11-19 and 70.9% on
11-22. The fall is *consistent with* the engineered discharge channel opened
2018-11-13 (§2.2), which lies between those dates, but nothing here ties them
and **the discharge is not claimed as detected**.

| `upstream_search_m` | largest lake | on AOI edge |
|---|---|---|
| 500 m | 260,700 m² | 40 px |
| 1,000 m | 361,700 m² | 40 px |
| **2,000 m (default)** | **602,200 m²** | 40 px |
| 3,000 m | 771,800 m² | 40 px |
| 5,000 m | 771,800 m² | 40 px |

A 3× range, and the lake touches the AOI edge: **the area is a lower bound**,
truncated by the 3 km AOI.

Artifacts: `outputs/baige_2018_phase8_corrected.json`,
`outputs/baige_2018_phase8_candidate_choice.json`,
`outputs/baige_2018_phase8_shrink_check.json`,
`outputs/baige_2018_phase8_tracking_diagnosis.json`.

### Earlier finding, still valid: a growing lake was reported as disappeared

Found during the withdrawn run and independent of it: the tracker called four
lakes *disappeared* — "the footprint held no water" — while 40.9% of the
largest was still wet, because `_unmatched` never tested for water. Fixed with
`min_residual_water_fraction` (0.10); six tests. On the corrected run no
disappearance is raised at all, since the one lake is matched on every date.

### C.3 — What this result does and does not establish

**Does:** impounded water is found behind a blockage candidate the system
raised on its own, on the main stem, +55.7% against the pre-event baseline,
and tracked under one identity across four dates, with a measured — not
cloud-induced — fall after the documented discharge date.

**Does not:**

- **No lake area is validated**: no reference outline, AOI-truncated, and
  still dependent on `upstream_search_m`. No published volume is comparable.
- **The discharge is not detected**, only a fall consistent with it.
- **`lake_width_m` (300 m) can still sweep in a parallel tributary** closer
  than that to the traced channel.
- **One event, four dates, Tibet.**

### Open items at the Phase 8 gate

1. **Done (§29).** `observations.search_distance_m` stores it and every lake
   popup on the map shows it, with the lower-bound caveat.
2. **Candidates along one reach are not merged** (ND-001 / ND-004), as at the
   Phase 7 gate.
3. **The AOI truncates the lake.** A blockage-centred AOI is the wrong shape
   for a lake that backs up a valley; an AOI following the upstream channel
   would be needed to measure it.
4. **No reference lake outline.**
5. **Phase 9 has not been run on BL-001.** With a stable identity it now can
   be; four dates is the minimum the trend module would consider.

---

## 23. Phases 9 and 11 on real data — BL-001 / ND-001, Baige 2018

> **Magnitudes superseded.** This record was produced from the unfused Phase 3 water mask. The chain was re-derived on Phase 4 fused water in §25, which is authoritative for every number below. The findings and the reasoning stand.

The detection chain now runs end to end on one real event: landslide change →
blockage candidate → barrier lake → trend → risk indicator. These two phases
had passed their gates on synthetic data only.

### Phase 9 — trend of BL-001

Possible only once Phase 8 held a stable lake identity (§22).

**Partial measurements are screened first.** A date on which cloud hid part of
the valley, compared with a clear one, turns visibility into area. Each date is
therefore tested against the lake's *floodable* extent — the traced upstream
zone restricted to ground at or below 3,601 m, the highest water seen in it on
any date — which is 49,133 px of the 56,385 px zone.

| date | floodable zone observable | lake | status |
|---|---|---|---|
| 2018-11-02 | 100.0% | — | pre-event (dam formed 11-03) |
| 2018-11-09 | 65.2% | 602,200 m² | measurement, **lower bound** |
| 2018-11-19 | 69.2% | 421,900 m² | measurement, **lower bound** |
| 2018-11-22 | 100.0% | 431,500 m² | measurement |

**Result: Decreasing — −170,700 m² (−28.3%) over 13 days, −13,131 m²/day**
(Theil–Sen, 3 valid, 0 gaps), 27× the configured stability band.

**The lower bounds do not undermine it.** The understated date (11-09, 35% of
the zone unseen) is the *first*, and the complete date (11-22) is the last, so a
larger true starting value makes the decline larger. −170,700 m² is a
conservative bound.

| pair | slope |
|---|---|
| 11-09 → 11-19 | −18,030 m²/day |
| 11-09 → 11-22 | **−13,131 m²/day** (median) |
| 11-19 → 11-22 | **+3,200 m²/day** |

The series is **not monotone**, and three valid observations is exactly
`min_valid_observations`, so a median of three pairwise slopes is the least
robust case the module accepts. The steepest interval spans 2018-11-13, the
engineered-discharge date in §2.2 — consistent, but **not claimed as a
detection** of it.

### Phase 11 — risk indicator

All inputs measured: blockage confidence 0.500 (Phase 7, ND-001), new landslide
area 1,900 m² (Phase 5), median slope 51.6° (DEM), growth rate (Phase 9).
Volume **not supplied** — Phase 10 has not run here. Rainfall weight 0, no
source. Data coverage 81.8%.

| phase of the lake | rate | score | level |
|---|---|---|---|
| filling, 11-02 → 11-09 | +86,029 m²/day | 0.6196 | **🟠 HIGH RISK INDICATORS** |
| declining (Phase 9) | −13,131 m²/day | 0.2862 | 🟡 MONITOR |

**The filling phase is flagged.** A real landslide dam impounding a major river
produced HIGH RISK INDICATORS from measured inputs with every factor listed.
The filling rate is a two-point reconstruction from a pre-event date, not a
Phase 9 trend, and is labelled so.

### Finding: a draining lake and a static lake score identically

`lake_growth_rate` carries the heaviest weight (3.0) on a scale of
`[0, 2000] m²/day`, so a negative rate clamps to **0.000** — indistinguishable
from no change.

For Baige the fall was engineered and a lower level is defensible. But **a
breach produces the same signature.** A barrier lake that has just emptied
catastrophically shows a large negative rate, and the heaviest factor reads it
as nothing to report. The `Decreasing` label is shown, but the number driving
the level cannot separate a controlled drawdown from an outburst that has
already occurred.

Not changed here: the brief names "lake area growth rate" as the factor, and
fixing this needs either a signed rate or a separate downstream-flood signal,
both of which change what the score means. Open item 2 below.

Artifacts: `outputs/baige_2018_phase9_trend.json`,
`outputs/baige_2018_phase11_risk.json`.

### C.4 — What these results do and do not establish

**Does:** a trend and a risk level are produced for a real barrier lake from
measured inputs, with gaps screened rather than absorbed, the conservative
direction of the cloud bias stated, every factor listed, unavailable factors
named with reasons, and the disclaimer attached.

**Does not:**

- **No trend is validated.** There is no independent area series for this lake
  to compare against.
- **The series is the shortest the module accepts** (3 points) and is not
  monotone; one of three pairwise slopes is positive.
- **Two of three areas are lower bounds**, and the absolute areas remain
  AOI-truncated and search-radius dependent (§22).
- **The discharge is not detected**, only an interval consistent with it.
- **The risk score inherits the Phase 7 mis-ranking** (§21): ND-001's 0.500
  confidence ranked it below six drained-reach candidates.
- **The filling-phase level is a reconstruction**, not what the shipped
  pipeline would have reported on 2018-11-09 from a Phase 9 trend — on that
  date there was only one post-event observation, and Phase 9 would correctly
  have said `Unknown`.
- **One event, four dates, Tibet.**

### Open items at the Phase 9 / 11 gates

1. **A lake observed once is `Unknown`, which is correct and also useless on
   the day it matters.** On 2018-11-09, six days after the dam formed, the
   system had one post-event area and would report no trend. The risk score
   would then run without its heaviest factor. This is honest but it is the
   operational weakness of an area-trend approach, and it is not solved by
   tuning.
2. **A negative rate scores zero on the heaviest factor** — a breach reads as
   nothing to report. Needs a decision (signed rate, or a separate signal).
3. **`min_valid_observations: 3` was not calibrated**; it is the brief's
   "minimum number of valid observations" set by convention.
4. **The floodable-zone observability screen is analysis, not code.** It is
   what made these three dates comparable, and it lives in a run script rather
   than in `analysis/change.py`.
5. **No independent area series**, as with every other quantity in this chain.

---

## 24. Phase 10 on a real lake — BL-001, Baige 2018

**Gate check (brief, Phase 10):** branch logic tested, no untraceable values.
**Status: the branch logic ran and chose A. Its numbers are withheld.** The
run's value is the four findings below, not a depth.

### What the shipped logic produced

| | value |
|---|---|
| branch | **A** (`estimated`) |
| mean depth | 57.34 m |
| max depth | 145.90 m |
| volume | 34.5 × 10⁶ m³ |
| WSE | **2946.33 m, spread ±24.61 m** (734 shoreline samples, median/IQR) |
| DEM sd inside the lake | 32.50 m — not flat, so no Branch B signal |
| GLO-30 water mask over the lake | 2.0% — below the 50% Branch B trigger |
| HEM zero inside the lake | 62.8% — **recorded as evidence and never used** |

### Finding 1: a single WSE does not describe an impounded reach

A water surface is level, so a **±24.61 m spread is not uncertainty about a
level surface — it is evidence the thing measured is not one**. The reach is
long and its pre-dam floor drops along it, and the module's own docstring
already notes the prescribed median is biased **upward** on a steep shoreline
because every ring sample sits upslope of the waterline. In a 40°+ gorge that
bias is tens of metres. The resulting WSE sits 76 m above the 2,870 m pre-dam
river surface and inflates every depth.

Section 8 is followed exactly. The finding is that its prescription suits a
compact lake in a basin and breaks down for a long impoundment in a steep
valley — the case this project exists for.

### Finding 2: the lake is 64% Branch B and 36% Branch A

| part | area | what the DEM holds |
|---|---|---|
| pre-existing Jinsha | 386,800 m² (64%) | a **water surface** — bed unknown (Branch B) |
| newly flooded | 215,400 m² (36%) | pre-lake ground (Branch A valid) |

Section 8's branches are per-lake, so one is chosen for all of it. On the 64%,
`WSE − DEM` measures the **rise in water level**, not depth, and the water the
river already held is missing — yet it is summed with true depths and labelled
one `estimated` figure.

Branch A over the newly flooded ground alone gives **6.34 × 10⁶ m³**, traceable
to Section 8 without reservation. Not offered as the lake's volume: the AOI
truncates the lake (§22) and the pre-dam channel's contents stay unmeasurable.
**No comparison with the published 105–775 × 10⁶ m³ is possible.**

### Finding 3: the height-error mask is collected and ignored

`decide_branch` records `zero_height_error_fraction` and **no rule reads it**.
Here it is **62.8%**, against 64.2% of the lake being pre-existing river. A
GLO-30 height error of exactly zero means no height was measured — over water,
the DEM saying it recorded a surface, not a bed.

The product therefore ships a **per-pixel** Branch A/B discriminator which is
already parsed into the evidence and then thrown away. Using it would address
Finding 2 directly. It changes the depth methodology, which Section 2 reserves
for approval, so it is recorded and not done.

### Finding 4: the whole Baige chain ran without the Phase 4 fusion

Phases 5, 7, 8, 9 and 10 on Baige all used the **Phase 3 rule-based optical
mask**. None used the Phase 4 shadow-rejection fusion — the core contribution.

**A first comparison, over the whole array, was invalid and is withdrawn.** It
reported the fusion inflating water from 0.8718 to 3.1041 km² with 80.4% of it
over 120 m above the river. But **40.1% of this scene is optical nodata**: the
Phase 3 mask is empty there by construction, while the fusion treats a pixel as
valid where *any one* term applies, so the DEM and SAR terms fill it. That
subtraction measured the nodata, not the fusion.

**88.9% of the pixels the fusion added are optically unusable.** On them
`water_index` and `nir` were available on 11.1%, the DEM and SAR terms on 100%;
median NIR 0.000, median MNDWI NaN, and only 1.6% flagged by the snow screen.
They are not snow mistaken for water — they are nothing read as water.

#### Finding 4a: the fusion asserts water with no optical observation at all

Over nodata the surviving evidence is SAR at −14.4 dB against a −8.65 dB
threshold, and a 0.6° slope, on flat ground at a median 3,822 m. Result:
`p_water = 0.719`, verdict water.

`FULLY_DETERMINATE_TERMS` includes `sar_backscatter`, so SAR alone suffices by
design. But every rule in Section 7.3 begins "dark **optical** pixel", and its
third rule makes unsupported SAR *uncertain* and defers to optical. **Section
7.3 has no rule for "no optical observation at all"**, and the default fills
that gap by trusting SAR — where dry snow and ice at 3,800 m are equally dark.

Not changed here: it alters a reviewed phase's semantics, which Section 2
reserves for approval. Marking those pixels `uncertain` is the recommendation.

#### Finding 4b: compared properly, the fusion works — and it moves the answer

Over optically usable pixels only, snow screened as an **invalid observation**
rather than voted on (MNDWI ≡ NDSI, so no weighting separates them), with the
four-date persistence term the first call omitted:

| date | optically usable | Phase 3 | Phase 4 | removed | added | net |
|---|---|---|---|---|---|---|
| 2018-11-02 | 99.8% | 8,045 px | 7,850 px | 807 | 612 | −195 |
| 2018-11-09 | 58.6% | 8,718 px | 7,663 px | 1,792 | 737 | −1,055 |

Removed pixels: median slope **33.8°** and **44.4°**, with 34.7% and 29.3% in
terrain shadow. Water does not sit on a 44° slope — this is the core
contribution working on real imagery.

**The lake on fused water is 478,300 m² against 602,200 m² unfused — 20.6%
smaller** (105,100 m² new, not 215,400 m²).

So the claim that the omission "did not corrupt" §21–§23 was **too strong and
is withdrawn**. Every finding's *direction* holds — a blockage, an impoundment
on the main stem behind it, expanding against baseline, declining after
11-13 — but **magnitudes move by about a fifth**. Read every Baige quantity in
§21–§24 as derived from the unfused mask and roughly 20% high on lake area.

Artifacts: `outputs/baige_2018_fused_chain.json`,
`outputs/baige_2018_fusion_diagnosis.json`. The withdrawn comparison is
`outputs/baige_2018_fusion_check.json`.

### Finding 5: `cos_incidence` could not run at AOI scale, silently

It built a three-channel normal array and used `np.linalg.norm` with a matrix
product. On this machine that product dies above roughly 300×300×3 with **no
traceback and exit code 0**. Every terrain-shadow and Phase 4 call at AOI scale
was being killed without a sign — which is how Finding 4 went unnoticed.

Rewritten elementwise: identical to 3.3 × 10⁻¹⁶, no BLAS, no three-channel
copy. It was the only such call in the project's own code.

#### Finding 5a: the Phase 4 gate result was re-checked and stands

Finding 5 raised a real doubt. Phase 4's headline claim — 87.5% of false
water removed at Tsho Rolpa, 96.4% of the reference lake retained — was
produced over a 799×797 grid, far above the ~300×300 size at which
`cos_incidence` was found to die. If its illumination layer had been invalid,
the project's central scientific result would have been too.

**It was not.** The illumination layer Phase 2 stored and Phase 4 consumed was
recomputed with the fixed elementwise implementation:

| | |
|---|---|
| max absolute difference | **2.2 × 10⁻¹⁶** |
| mean absolute difference | 3.4 × 10⁻¹⁷ |
| `terrain_shadow` agreement | **636,803 / 636,803 px (100.0000%)** |
| `self_shadow` agreement | 100.0000% |
| `cast_shadow` agreement | 100.0000% |

The reason is in the failure mode: the blocked BLAS call **kills the process**,
with no traceback and exit code 0. It never returns wrong numbers. So any run
that completed and wrote output cannot have hit it, and the block is
**intermittent** rather than permanent — consistent with the scipy and
`numpy.random` failures recorded earlier in this project.

**Phase 4's gate is not in doubt, and its figures are unchanged.** What the
bug did cost was the Baige analysis, where the failure was hit, nothing was
written, and the silence was mistaken for the fusion simply not having been
wired in (Finding 4).

Artifact: `outputs/phase4_illumination_recheck.json`.

Artifacts: `outputs/baige_2018_phase10_depth.json`,
`outputs/baige_2018_fusion_check.json`.

### Open items at the Phase 10 gate

1. **The WSE model needs to handle a sloping impoundment** before any depth
   from this site is usable — a per-reach surface, or a surface fitted along
   the channel, rather than one median. This is the blocker.
2. **The HEM per-pixel discriminator should be used** (Finding 3). Needs
   approval as a methodology change.
3. **Re-derive §21–§24 on fused water.** Done for the lake only (Finding
   4b): it is 20.6% smaller. Phases 5, 7, 9 and the risk score have **not**
   been re-run, so their published numbers remain unfused.
4. **No depth or volume is claimed for Baige**, and no published figure is
   comparable.
5. **Branch A has still never been validated against a known volume.**

---

## 25. The Baige chain re-derived on fused water

§§20–24 were all produced from the **Phase 3 rule-based optical mask**,
because the Phase 4 fusion was silently unavailable at AOI scale (§24,
Finding 5). This section re-derives the whole chain on fused water and
**supersedes the magnitudes in §§20–23**.

Water is fused per date with each scene's own sun angles, snow screened as an
**invalid observation** rather than voted on (MNDWI ≡ NDSI, so no weighting
separates snow from water), a persistence layer from all four dates, and the
result kept only where optical data exists — otherwise the fusion asserts
water from SAR alone over nodata (§24, Finding 4a).

| date | optical usable | Phase 3 | fused |
|---|---|---|---|
| 2018-11-02 | 99.8% | 8,045 px | 7,876 px |
| 2018-11-09 | 58.6% | 8,718 px | 7,671 px |
| 2018-11-19 | 58.2% | 10,982 px | 10,351 px |
| 2018-11-22 | 91.7% | 10,226 px | 9,845 px |

### What changed

| quantity | unfused (§§20–23) | **fused (authoritative)** |
|---|---|---|
| Phase 5 change, dam-tuned gate | 0.2652 km², 50 polygons | **0.3189 km², 66 polygons** |
| Phase 7 candidates | 14 | **32** |
| lake-bearing candidate | ND-001 (conf 0.500) | **ND-016 (conf 0.750)** |
| lake area, 2018-11-09 | 602,200 m² | **333,700 m² (−44.6%)** |
| trend | −170,700 m², −28.3%, −13,131 m²/day | **−14,400 m², −4.3%, −1,108 m²/day** |
| risk level | MONITOR, 0.2862 | **MONITOR, 0.3909** |

### The trend was mostly an artefact

This is the consequential change. On unfused water the lake fell 28.3% in 13
days at 27× the stability band. On fused water it falls **4.3% at 3.4×** the
band (11.1× by the absolute band, but `trend_metric` is `relative`). The
series is 333,700 → 328,900 → 319,300 m² — a mild, steady decline rather
than a collapse.

The classification is still `Decreasing`, but it is now **marginal**, and the
reading offered in §23 — a fall "consistent with the engineered discharge" of
2018-11-13 — no longer has much of a fall to explain. **That interpretation is
withdrawn.** Most of the apparent decline was false water in the unfused mask
disappearing as cloud and shadow moved between dates, not water leaving the
valley.

### Two things improved

**Observability.** The lake zone is 99.4–100% observable on every date, against
65.2% and 69.2% in §23, because the impounded reach lies in the clear part of
the scene and the earlier figure was diluted by the whole floodable zone. The
"lower bound" caveat on those areas is now minor.

**Blockage confidence.** ND-016 scores 0.750 against ND-001's 0.500, which is
why the risk score rises (0.2862 → 0.3909) even though the lake shrank: the
growth-rate factor contributes **0.000** either way, since a negative rate
clamps to the bottom of its scale (§23, and methods 11.10). The level is
MONITOR in both cases.

### Two things got worse

**Over-detection doubled.** 32 candidates for one dam, against 14. The fused
`water_post` is smaller, so `exclude_water_on_post_date` removes fewer pixels,
more change survives, and more components clear the area floor. Merging
candidates along one reach (§21 open item 1) is now the single largest source
of noise in the output.

**The lake-bearing candidate is no longer on the main stem.** ND-016 carries
180,104 cells against the AOI's main-stem maximum of 334,834. ND-001's 332,506
was a cleaner identification. ND-016 is selected here on direct evidence —
154,800 m² of gained water in its own traced upstream reach, the largest of any
candidate — but the drainage figure says it sits on a tributary or a lower
reach, and the two signals disagree. That disagreement is unresolved.

### What is *not* claimed

- **Still no ground truth.** Every caveat in §§21 C.2, 22 C.3, 23 C.4 and 24
  carries over unchanged. No IoU, precision, recall or validated area.
- **Depth remains withheld** (§24). The re-derivation does not address the WSE
  problem, which is about the shape of the impoundment, not the water mask.
- **The lake is still AOI-truncated and still `upstream_search_m`-dependent.**
- **One event, four dates, Tibet.**

Artifact: `outputs/baige_2018_rederived_on_fused_water.json`.

### Open items

1. **§§20–25 now carry superseded magnitudes** (§26 is authoritative). They are left in place with
   this cross-reference rather than rewritten, because the findings that
   produced them — the water-on-post-date gate, the minimum-area gate, the
   stream tracing, the confluence reference, the wet-footprint fix — are each
   tied to the numbers that exposed them.
2. **The main-stem disagreement is resolved**, and robustly: 10 of 10 setting
   variants name the same candidate on the main stem (above). On unfused water
   only 4 of 10 do, which is direct evidence that the fusion changes the
   answer and not just the water mask.
3. **The candidate count is still setting-dependent** (2 to 5 across the same
   variants), even though the dam's identity is not. Over-detection is reduced,
   not solved.

---

## 26. Candidate merging, and the swing in the warning level

§25 left two things unresolved: 32 candidates for one dam, and a lake-bearing
candidate whose drainage said it was not on the main stem. Both had the same
cause.

### The disagreement was fragmentation

Ranked by gained water upstream, the candidates fell into two groups:

| group | drainage (cells) | gained water upstream |
|---|---|---|
| ND-016, ND-017, ND-018, ND-014 | 172,925–180,647 | 136,500–154,800 m² |
| ND-003, ND-002, ND-001 | 331,981–333,301 | 116,800–133,000 m² |

Seven candidates, two reaches, and **largely the same impounded water counted
seven times**. "The candidate with the most gained water" was therefore
choosing an arbitrary fragment, which is why the drainage and the water
evidence disagreed — they were pointing at different fragments of one
obstruction.

### The fix

`detection.blockage.merge_along_stream_m` groups landslide components that
obstruct the same reach, with distance measured **along the stream network**
rather than across country — so deposits on opposite banks of a gorge group,
and deposits on separate tributaries do not. It defaults to
`evidence_search_m` (500 m), because two blockages closer together than the
radius over which their evidence is gathered cannot be distinguished by that
evidence.

Zero does **not** disable grouping. Components reaching the same stream pixels
obstruct the same cross-section and are one blockage at any distance — which
is exactly the slope-gate case from methods §5.9. The setting governs only how
far along the channel the grouping additionally extends. Seven tests, including
one that checks the split deposit really is two components, because a test
asserting "one candidate" proves nothing if the fixture was one object all
along.

### Result: 32 candidates become 2

| | §25 (unmerged) | **merged (authoritative)** |
|---|---|---|
| Phase 7 candidates | 32 | **2** |
| lake-bearing candidate | ND-016, 180,104 cells | **ND-001, 333,301 cells** |
| gained water upstream | 154,800 m² | **239,500 m²** |
| merged deposit area | 6,700 m² | **90,300 m²** |
| lake, 2018-11-09 | 333,700 m² | **634,900 m²** |
| trend | Decreasing, −4.3% | **Increasing, +3.0%** |
| risk | MONITOR, 0.3909 | **CRITICAL INDICATORS, 0.7979** |

**The main-stem disagreement is resolved.** ND-001 carries 333,301 drainage
cells against the AOI maximum of 334,834, so it is on the Jinsha itself, and it
also holds the most impounded water. The two signals now agree, and the second
candidate is a 1,465-cell tributary feature holding 1,700 m² — negligible.

The lake series is 634,900 → 697,000 → 654,200 m² across 11-09, 11-19 and
11-22.

### Finding: the dam's identity is robust, and the fusion is why

§26 reported that merging resolved the main-stem disagreement, with ND-001
holding both the most impounded water and the highest drainage. One run
agreeing is not the same as the agreement being stable, and the candidate that
gets reported is the one a user would act on — so the settings that decide
candidate grouping were varied and the question re-asked each time.

A candidate counts as on the main stem if it reaches 90% of the AOI's maximum
drainage (301,351 of 334,834 cells).

| variant | candidates | top by impounded water | drainage | on main stem? |
|---|---|---|---|---|
| shipped default | 2 | ND-001 | 333,301 | ✅ |
| merge 250 m | 5 | ND-001 | 333,301 | ✅ |
| merge 750 m | 2 | ND-001 | 333,301 | ✅ |
| merge 1,500 m | 2 | ND-001 | 333,301 | ✅ |
| min area 500 m² | 2 | ND-001 | 333,301 | ✅ |
| min area 2,500 m² | 4 | ND-001 | 332,506 | ✅ |
| stream reach 30 m | 4 | ND-001 | 333,284 | ✅ |
| stream reach 100 m | 2 | ND-001 | 333,333 | ✅ |
| evidence search 300 m | 2 | ND-001 | 333,301 | ✅ |
| evidence search 800 m | 5 | ND-001 | 333,301 | ✅ |

**10 of 10.** Across every variant the same candidate is identified, always on
the Jinsha itself. The agreement in §26 was not luck.

**But the same sweep on UNFUSED water gives 4 of 10**, with the top candidate
flipping between ND-001 at 332,506 cells and ND-002 at 174,278 — on a
tributary — depending on the merge distance.

That is the most direct evidence in this project that the shadow-rejection
fusion matters to the **answer**, not merely to the water mask. Removing false
water from steep shadowed slopes (median 33.8° and 44.4°, §24 Finding 4b)
changes which component accumulates the apparent impoundment, and so changes
which blockage the system names. On unfused water the identification is
setting-dependent; on fused water it is stable.

**What is still not stable is the candidate count**, which ranges 2 to 5 across
the same variants. Over-detection remains sensitive to configuration even
though the dam's identity is not.

Artifact: `outputs/baige_2018_mainstem_robustness.json`.

### Finding: the warning level is dominated by this one methodological choice

Merging moves the indicator from **MONITOR (0.3909) to CRITICAL (0.7979)**, and
two of the four factors move by an order of magnitude:

| factor | unmerged | merged | weight |
|---|---|---|---|
| `new_landslide_activity` | 6,700 m² → score 0.134 | **90,300 m² → score 1.000** | 2.0 |
| `lake_growth_rate` | −1,108 m²/day → **0.000** | **+1,485 m²/day → 0.742** | 3.0 |
| `blockage_confidence` | 0.750 | 0.750 | 3.0 |
| `slope` | 45.5° → 1.000 | 36.1° → 0.705 | 1.0 |

The deposit area rises because the merged candidate carries the whole landslide
rather than one fragment, and it then saturates its scale. The growth rate
**changes sign**, because the merged candidate's reach captures the whole
impoundment rather than part of it.

So a capability that did not exist until now decides whether this site reads
MONITOR or CRITICAL. That is not an argument against merging — the merged
answer is the better-founded one on every independent check — but it does mean
**the warning level for this site was never robust**, and no level published
before this section should be relied on.

### Finding: the trend flips sign and is marginal either way

| | rate | vs stability band |
|---|---|---|
| unmerged | −1,108 m²/day | 3.4× (Decreasing) |
| merged | +1,485 m²/day | 2.2× (Increasing) |

Both are within a factor of four of the band that would call the lake Stable,
and they point in opposite directions. **The sign of this lake's trend is not
a robust result.** It rests on three observations — the configured minimum —
of a lake whose extent depends on which candidate's reach defines it.

The §23 reading of a decline "consistent with the engineered discharge" of
2018-11-13 was already withdrawn in §25. It is now doubly withdrawn: on the
merged candidate the lake is *larger* on 11-19 than on 11-09, which is after
that date.

### Is CRITICAL the right answer?

For the real event, arguably yes. On 2018-11-09 the Baige dam was impounding
the Jinsha six days after forming, and the response involved evacuating
downstream populations. An indicator of **CRITICAL INDICATORS — verification
recommended**, from measured inputs with its four factors listed, is a
defensible output and the first in this project that would have been
operationally useful.

But it is reached with a growth rate 2.2× a convention threshold, on three
observations, from a lake whose area is AOI-truncated and search-radius
dependent, with no ground truth, at a site chosen by a merging rule written
after the fact. The level is defensible; the confidence behind it is low, and
§§21 C.2 through 24 all still apply.

Artifacts: `outputs/baige_2018_rederived_on_fused_water.json` (re-run with
merging), `outputs/baige_2018_candidate_clustering.json`.

### Finding: a saturated factor was indistinguishable from a merely high one

Open item 2 of §26 noted that `new_landslide_activity` has a scale of
`[0, 50000]` m² and that Baige's merged 90,300 m² deposit pins its top, so
any larger dam would contribute identically.

**The scale was not widened.** Setting it would need a published distribution
of landslide-dam deposit areas, and two searches did not find one that is both
accessible and specific to dam deposits rather than landslides in general.
Fan et al. (2020) compiled 410 cases and the New Zealand Landslide Dam
Database 1,036, but both are paywalled and neither's area statistics could be
read. Section 2 of the brief requires a citation for any threshold and says to
say so rather than guess, so the convention stands and is recorded as a
convention.

**What was fixed is the silence.** `scale_score` clamps, so a value past the
scale's end scores 1.00 and looks identical to one that merely reached it.
`RiskFactor` now carries `saturated`, set when a value reaches or passes the
*worse* end of its scale — whichever end that is, since a scale may run either
way. It is surfaced in three places:

* `describe()` appends `SATURATED (scale ceiling reached)`;
* `warning_text()` leads with `SCALE CEILING REACHED by <factors>`, and says
  the scales are conventions rather than calibrated measurements;
* `as_dict()` carries it, so it survives into `factors_json` in the database
  and into the report.

Verified end to end on the real site: the stored assessment for ND-001 records
`new_landslide_activity: saturated=true` at 90,300 m², and the generated PDF
carries *"scale ceiling reached — the score cannot distinguish this from a
larger value"* beside that factor. Seven tests, one of which asserts the real
Baige deposit still saturates the shipped scale and says to update the test
and this document if the scale is ever widened deliberately.

**A second finding came out of wiring it up.** The first report showed no
ceiling note even though the flag was set, because the persistence step copied
the factor list from a previous run's JSON instead of calling `assess_risk`.
A stored assessment that is copied rather than computed silently loses any
field added since it was written. The step now recomputes the assessment.

### Open items

1. **The trend's sign is not robust** (above). More observations are the only
   fix; the module correctly refuses to say more from three.
2. **`new_landslide_activity` still saturates**, and the scale is still a
   convention — no accessible published distribution of landslide-dam deposit
   areas was found (above). What changed is that the ceiling is now reported
   rather than silent, in the warning, the database and the PDF.
3. **No ground truth**, as throughout.

---

## 27. Phase 6 code record — what exists, and what the gate still needs

**The Phase 6 gate is still NOT met**, and cannot be until labelled data
exists: it asks for per-class metrics and the water-vs-shadow confusion *for
both models*, and no model has been trained. This section records what is now
in place, so the remaining work is the labelling and the GPU run rather than
the code.

### What was missing before

| file | before | now |
|---|---|---|
| `config.yaml` `models:` section | **absent** | ✅ channel stack, classes, patch geometry, splits, training |
| `models/unet.py` | absent | ✅ the brief's `smp` baseline |
| `models/dataset.py` | absent | ✅ patches, label mapping, leak-free splits |
| `models/train.py` | absent | ✅ training loop and the required comparison |
| `models/predict.py` | absent | ✅ tiled inference over a Phase 2 stack |
| `notebooks/colab_train.ipynb` | absent | ✅ 18 cells, no model logic |
| `models/build_patches.py` | absent | ✅ stack + label raster → patches |
| `models/attention_unet.py` | ✅ present | unchanged |
| `models/evaluate.py` | ✅ present | unchanged |

**There was no `models:` config section at all.** The brief requires a
configurable channel stack and 256×256 patches; `in_channels` existed only as
a constructor default, so neither was configurable and nothing read from
config. `len(models.channels)` is now the single source of truth for a model's
input width.

### Four guards built in deliberately

Each one closes a path to a confident wrong answer.

1. **`strategy` has no `random` option.** The brief forbids random patch
   splits; an unavailable option cannot be chosen by mistake. Blocks of ground
   are partitioned, never patches, and patches near a boundary are dropped
   (`docs/labelling.md`, Splits).
2. **`map_labels` refuses an unmapped source value.** Defaulting it to
   background would turn an undocumented class into training signal for
   "land", and nothing downstream could detect it.
3. **Nothing can be monitored that Section 7.5 forbids.** `monitor_metric`
   accepts macro IoU, water IoU or validation loss. Overall accuracy is not
   selectable, and the run's report contains the word only in a note
   explaining its absence. The test split is evaluated once, after training,
   and never drives early stopping.
4. **A checkpoint cannot be applied to a stack it was not trained on.**
   `load_checkpoint` compares the recorded channel names to
   `models.channels`. Same width in a different order produces a raster that
   is wrong everywhere without looking wrong.

Also: `predict_stack` returns `ignore_index`, not a class, where the stack
holds no observation — the same failure that put Phase 4 water over scene
edges (§24, Finding 4a).

### Verified end to end on synthetic patches

Both models train, the comparison is written, the water-vs-shadow block is
populated for each, and the attention gates cost 132,004 parameters over the
otherwise identical plain U-Net (7,985,193 vs 7,853,189). Inference covers a
raster that is not a multiple of the tile, returns probabilities summing to
one where classified and NaN where not.

**49 new tests** (29 dataset, 20 training/inference); **770 offline tests pass**.

### The patch builder, and what it revealed

`models/build_patches.py` completes the pipeline from a Phase 2 stack to Phase
6 patches. Its contract is a single-band label raster on exactly the stack's
grid, with `ignore_index` for unlabelled ground; it refuses a grid mismatch
rather than resampling, names a missing channel rather than zero-filling it,
and forces the label to `ignore_index` wherever the stack has no observation.

**Demonstrated on real Baige imagery.** The configured 15-channel stack was
assembled from actual data for the first time — six Sentinel-2 bands, three
indices, Sentinel-1 VV and VH, DEM, slope, illumination and the terrain-shadow
mask — at 92.0% finite coverage, and round-tripped through the dataset layer
to a `(15, 128, 128)` training tensor. The label raster used for the
demonstration was derived from this project's **own detectors**, so it is a
test of the builder and explicitly **not** training data: a model fitted to it
would only learn to reproduce the rule-based masks it came from.

#### Finding: the split buffer was applied after block assignment

The demonstration kept 2 of 41 patches with val and test empty, and a
three-site simulation gave train 6, val 0, test 0 — despite three blocks being
available to share out.

`assign_splits` partitioned blocks **before** dropping buffered patches, which
made the non-empty guarantee meaningless: a block could be assigned to `test`
and then lose every one of its patches to the buffer. Adding sites made the
outcome erratic rather than better. Fixed by buffering first and partitioning
only the blocks that still hold a patch; with three separated sites the split
is now 9 / 9 / 9. Four tests pin it, including one that confirms a single site
still cannot be split, because that is an honest failure rather than a bug.

#### Finding: one study area cannot produce a valid split

With the shipped defaults a 10 km block has a usable interior of **23.8 km²,
24% of the block**, because the buffer is a band around every edge. The Baige
AOI is about 28 km² — smaller than one block.

| separated sites | train / val / test |
|---|---|
| 1 | 9 / 0 / 0 |
| 2 | 9 / 0 / 9 |
| **3** | **9 / 9 / 9** |
| 10 | 63 / 18 / 9 |

**This changes what the labelling must be.** Labelling one valley
exhaustively produces a training set with no validation or test partition.
Labelling needs **at least 3 areas at least 10 km apart, preferably 6-10**,
and within each only patches rather than full coverage. The guidance is in
`docs/labelling.md`; artifact `outputs/phase6_labelling_footprint.json`.

### Route A: Landslide4Sense, and exactly what it can answer

The repository owner can run a Colab session but cannot hand-label. That
constraint has one hard consequence and one useful opening.

**The hard consequence.** No public dataset labels terrain shadow, so
**the water-versus-shadow confusion matrix — the brief's primary result —
cannot be produced at all** without hand labels. Nothing in this section
changes that, and no sample size substitutes for it.

**The opening.** Landslide4Sense 2022 is real, independently produced,
**CC BY 4.0** labelled data, verified on the Zenodo record itself
(10.5281/zenodo.10463239) rather than on a mirror. It can therefore answer the
brief's *other* required result: the **plain-U-Net versus Attention-U-Net
architecture comparison**, on a real labelled task.

`models/landslide4sense.py` adapts it, and `config/landslide4sense.yaml`
declares the three departures from the project defaults that using it forces.
Each is a cost, stated rather than absorbed:

| departure | why | what it costs |
|---|---|---|
| **11 channels, not 15** | the dataset has no Sentinel-1, and no illumination or terrain-shadow layer — those need per-scene sun angles it does not carry | a model trained here has never seen SAR or a shadow mask and cannot be applied to a full stack; the checkpoint records its channels and `predict.py` refuses the mismatch |
| **128 px, not 256** | their patch size | the comparison is at a different scale from this project's own patches; the two are not interchangeable |
| **event split, not geographic** | the patches carry no coordinates, so a geographic split would degenerate into the per-patch split the brief forbids | each patch is its own event, which guarantees no patch appears twice but **not** that two patches from the same landslide land in one partition — the dataset does not say which patches share a source, so a residual leak risk remains |

The four missing channels are **removed, not zero-filled**. A zero channel is
not a measurement, and filling one would teach the model that "no data" is a
valid value for real terrain — the mistake that put Phase 4 water over scene
edges (§24, Finding 4a).

**Three refusals, each tested.** The adapter refuses a channel the dataset
cannot supply; refuses a patch of the wrong size rather than resampling,
because interpolating a label raster invents boundaries that were never drawn;
and refuses an unmapped source label rather than defaulting it to background.
Sixteen tests.

**Verified end to end** on synthetic HDF5 in the dataset's documented layout:
convert → event split → train both models → per-class IoU → water/shadow
block. An absent class correctly reports `None` rather than `0.0`, which is
the difference between "the model failed at this" and "there was nothing to
learn from".

The notebook now has two routes. Route A downloads 2.5 GB from Zenodo in plain
Python with an **MD5 check against the published checksum** — training on a
corrupt download would be undetectable — and runs without anything from the
owner but a GPU. Route B waits on hand labels.

**Attribution is required by CC BY 4.0** wherever a Route A result is
reported:

> Ghorbanzadeh, O., Xu, Y., Ghamisi, P., Kopp, M. and Kreil, D. (2022),
> "Landslide4Sense: Reference Benchmark Data and Deep Learning Models for
> Landslide Detection", *IEEE Transactions on Geoscience and Remote Sensing*
> 60, 1-17.

**Sen1Floods11 remains unusable.** Its repository carries no licence text or
file, so it is still `enabled: false`. Training on data under unknown terms is
not a risk this project should take silently.

### What the gate still needs

1. **Hand-labelled Himalayan patches — the only route to the brief's
   primary result.** Neither public dataset labels terrain shadow, so
   **class 3, the project's core contribution, has no public source at all**.
   Route A can deliver the architecture comparison; it can never deliver the
   water-versus-shadow confusion. This remains the largest dependency in the
   project and no amount of public data substitutes for it.
2. **A Colab GPU run.** The notebook and the training code are ready; nothing
   in the notebook decides anything.
3. **Sen1Floods11's licence is still unestablished** and it stays disabled.
   Landslide4Sense is settled: CC BY 4.0, verified on Zenodo (Route A above),
   and usable with attribution.
4. **The labelling must span at least 3 areas 10 km apart** (above). This
   is the constraint most likely to waste effort if discovered late, and it
   is not a preference: fewer separated sites leave a partition empty.
5. **Externally sourced patches teach "background" for classes their source
   does not distinguish.** A Sen1Floods11 chip labels a landslide scar 0.
   Restricting the loss on such patches to the classes that source actually
   separates is not implemented.

---

## 28. Decisions taken on the owner's behalf

The repository owner can run a Colab session and nothing else, and asked for
the outstanding decisions to be made rather than left open. Four were pending, and
all four are settled below.

Each was a case where the measured evidence and the brief's letter pointed
different ways, so each records what the brief says, what the data showed, and
which way it was resolved. **Three were implemented; one was deliberately
left alone**, which is recorded with its reasoning rather than as an omission.

---

### 2d. `scripts/` added — the Baige claims are now reproducible

**The problem.** Sections 20-27 cite artifacts in `outputs/`, but the runs that
produced them lived in a throwaway session directory. No code in the
repository could reproduce a single Baige number. The brief's folder structure
has no place for run scripts, which is why it had not been done.

**Resolved: added**, with thirteen scripts under `scripts/baige/` and
`scripts/checks/`, each carrying a header naming the section it supports.
Paths derive from each file's own location, so a clone runs them from
anywhere — verified by running two from outside the repository and reproducing
the 10/10 main-stem result.

**It is a selected set, not an archive.** Forty-eight scripts existed. Most
were one-off documentation edits whose content is now in the documents, and
several produced results later superseded — keeping those would imply their
numbers still stand. `scripts/README.md` lists what was left out and why.

`scripts/baige/03_rederive_chain.py` is the authoritative run: sections 25 and
26 are its output.

---

### 2a. Water now requires an optical observation

**What the brief says.** Section 7.3 gives three rules, and **every one of
them begins "dark optical pixel"**. Its third makes SAR that is water-like but
sits inside the layover/shadow mask *uncertain*, deferring to optical
evidence. The section has **no rule** for the case where there is no optical
observation at all.

**What the data showed.** That case is not rare: **40.1% of the Baige
Sentinel-2 scene is optical nodata** at the scene edge. A pixel counts as
"valid" if *any* single term applies, and the DEM-derived and SAR terms apply
everywhere — so those pixels still received a verdict, decided by radar. The
fusion reported water at a median **3,822 m on flat high ground**, and
**88.9%** of everything it added over the rule-based mask had no optical
observation (§24, Finding 4a). Water, dry snow and smooth ice are all dark to
radar, so the verdict had no basis in the data.

**Resolved: implemented**, as `detection.shadow_rejection.require_optical_for_water`,
default `true`. Such a pixel is marked **uncertain** rather than classified,
which is how Section 7.3 treats SAR evidence it cannot corroborate — so this
follows the section's intent for a case it does not cover, rather than
contradicting it.

Measured on the scene that exposed the problem:

| | gate off | **gate on** |
|---|---|---|
| fused water | 31,041 px | **8,299 px** |
| added over the rule-based mask | 25,587 px | 2,845 px |
| uncertain | 4,915 px | 27,657 px |
| highest water pixel | 4,602 m | 4,402 m |

**8,299 px is exactly the figure §25 obtained** by remembering to mask the
result with `& optical_ok` by hand. The fusion now does automatically what the
caller previously had to know to do, which is the real gain: the old behaviour
was not merely wrong, it was a trap that each new caller had to be told about.

The reason mask `water_without_optical` is populated **either way**, so a run
that chooses the old behaviour can still report how much of its water rested
on radar alone. Seven tests, including one confirming that half a scene being
unusable does not cost the half that is usable.

**What this does not fix.** With the gate on, the highest water pixel is still
4,402 m. Those pixels *do* have optical evidence, so they are a different
problem — most likely snow, since MNDWI is identical to NDSI and no snow
screen was supplied to that particular call.

---

### 2c. Depth now splits a mixed lake per pixel

**What the brief says.** Section 8's branches are **per-lake**: a lake either
postdates the DEM (Branch A, depth measurable) or it does not (Branch B, bed
unknown).

**What the data showed.** A real barrier lake is neither. The Baige lake is
**64% pre-existing Jinsha channel**, which the DEM recorded as a *water
surface*, and 36% newly flooded ground, where the DEM holds the pre-lake
surface. Forced to pick one branch, the module picked A for all of it — so
over that 64% it was computing the **rise in water level** and summing it with
true depths under a single `estimated` label (§24, Finding 2).

A per-pixel discriminator already existed in the data and was being thrown
away: the GLO-30 **height-error mask**. A value of exactly zero means no
height was measured, which over water is the product stating it recorded a
surface rather than a bed. On this lake it reads **62.8% zero against 64.2%
of the lake being pre-existing river** — independent agreement to within 1.4
percentage points. `decide_branch` read it into its evidence dictionary and
no rule ever consulted it (§24, Finding 3).

**Resolved: implemented**, as
`analysis.depth_volume.branch.use_height_error_mask`, default `true`. Branch A
is computed over the measured pixels only; the rest are declared Branch B, and
the volume is reported as a **lower bound** — it omits whatever the river
already held below its DEM-epoch surface. That is traceable to Section 8 pixel
by pixel, which summing the two together was not.

A second key, `min_branch_b_fraction_to_split` (0.05), prevents splitting on a
few scattered zero-error pixels: those are mask noise, not a submerged
channel, and splitting on them would discard good data and label the result a
lower bound for no reason.

Effect on the real lake:

| | whole lake, one branch | **per-pixel split** |
|---|---|---|
| mean depth | 57.34 m | 40.50 m |
| **max depth** | **145.90 m** | **76.20 m** |
| volume | 34.5 × 10⁶ m³ | 9.07 × 10⁶ m³ |
| pixels measured | all 6,022 | 2,240 |

**The 145.90 m figure was the contamination made visible.** That pixel sat in
the old channel, where `WSE - DEM` measured the full rise from the 2011-2014
water surface rather than any depth. Halving the maximum is the split removing
a value that was never a depth.

Eight tests, including one confirming that a lake whose height-error mask is
zero *everywhere* returns Branch B unavailable — the DEM measured no bed
anywhere, so none is known — and one confirming the split is never inferred
from an absent mask.

**Baige's numbers remain withheld.** §24 gave three reasons; this resolves two
of them (the mixed branch, and the discarded mask). The third stands and is
sufficient on its own: the shoreline water-surface elevation has a
**±24.61 m spread on a surface that must be level**, because a single WSE
does not describe a long impoundment in a steep valley. That is about the
*shape* of the lake, not the water mask or the branch, and this change does
not touch it.

---

### 2b. Requiring upstream water for a dam — not changed, and why

**What the brief says.** Section 7.6: obstruction evidence is "channel
narrowing, loss of downstream water continuity, **and/or** new upstream
water". Any one suffices.

**What the data showed.** On Baige, six drained-reach candidates scored
**0.625** while ND-004 — genuinely in the channel with water impounded behind
it — scored **0.500**. A drained reach collects narrowing (2.0) plus
downstream loss (2.0) plus proximity (1.0) = 5/8; a dam showing only
impoundment collects 1.0 + 3.0 = 4/8. **Two signals that a blockage has
already drained outrank the one signal that water is being held back now**
(§21).

**Resolved: left as the brief specifies**, and here is the reasoning rather
than a shrug. The brief is *right* that a drained reach is obstruction
evidence — a dam that has burst was still a dam, and downstream water loss is
exactly how you would detect one after the fact. Requiring upstream water
would make the system blind to a blockage that has already failed, which is
not obviously safer.

What is wrong is not the detection but the **ranking**: two physically
different situations produce one scalar that cannot separate them. Fixing it
by reweighting would be arbitrary, and fixing it by requiring upstream water
would trade one blind spot for another.

So the defence the brief itself prescribes is relied on: **every candidate
publishes its factors**, and §21's finding that the score alone is misleading
here is recorded where a reader of those numbers will meet it. Candidate
merging (§26) also removed most of the duplication that made the ranking
matter — 32 candidates became 2.

**This remains the weakest of the four decisions**, and the one most worth
revisiting with more than one event to calibrate against. A principled fix
would classify the obstruction *pattern* — impounding, drained, or narrowed
only — and report that alongside the score rather than compressing it into
one number. That is a change to what Phase 7 outputs, and with one event to
judge by there is no evidence for preferring any particular design.

---

### Were the published figures invalidated by these changes?

Decisions 2a and 2c altered the fusion's semantics and the depth logic, and
§§25-26 are fusion-based results. So the authoritative chain was **re-run and
diffed against every figure those sections publish**, rather than assumed
still current.

| | published | after 2a and 2c |
|---|---|---|
| Phase 5 change | 3,189 px | 3,189 px |
| Phase 7 candidates | 2 | 2 |
| lake-bearing candidate | ND-001 | ND-001 |
| lake 11-09 / 11-19 / 11-22 | 634,900 / 697,000 / 654,200 m² | identical |
| trend | Increasing, +1,484.6 m²/day | identical |
| risk | CRITICAL, 0.7979 | identical |

**Nothing moved**, and the reason is the point. §25's run already applied
`& optical_ok` to the fused water by hand, so making the fusion enforce it
changed the numbers not at all — it moved the correctness from the caller's
memory into the code. 2c touches depth alone, which §§25-26 do not report.

A change that tightens a rule the caller was already following should produce
exactly this: no difference in the result, and one fewer thing a future caller
has to know.

## 29. The map now shows where, and the area carries its bound

Two things the owner asked about early on, and one open item they share.

**The question was "how are you going to show the warning on the map, showing
the warning location".** The honest answer at the time was that it did not:
`build_site_map` drew one coloured circle per site and nothing else. A reader
seeing CRITICAL could not see the lake being measured, the deposit that
produced the blockage, or the blockage itself — even though all three existed
as geometry inside the pipeline.

**And §22 open item 1** was that lake area must be stored with the search
distance that bounded it, or the number is uninterpretable: the same lake
measured over 500 m and 3,000 m of channel differs threefold.

Both needed the same thing — geometry in the database — so both are done here.

### Schema

`observations` gains `geometry` (WKT) and `search_distance_m`.

`CREATE TABLE IF NOT EXISTS` leaves an existing table untouched, so a database
written by an earlier version would silently lack both columns and every
insert naming them would fail — **worse than a schema change, because it only
surfaces on the next write.** `initialise()` therefore adds missing columns
via `ALTER TABLE`, which is cheap and non-destructive. Rows written before a
column existed hold NULL, which is correct: they genuinely had no value for
it. Verified on a deliberately old file.

### Five layers, toggleable

| layer | shown by default | why |
|---|---|---|
| Blockage candidate | yes | the thing being reported |
| Barrier lake | yes | the quantity the level is driven by |
| New landslide | yes | what produced it |
| Stream network | yes | the channel the blockage is judged against |
| Water before the event | **no** | reference for judging growth, not the report |

The shape palette is **deliberately distinct from the status palette**: a
shape says *what was detected*, a marker says *how concerned to be*, and
sharing one palette would imply a lake is itself a warning level. A test
asserts the two sets do not intersect.

A geometry that fails to parse is **skipped and logged, not raised**: a
dashboard that will not open because one stored shape is malformed is less
useful than one that draws the rest. A test confirms a bad geometry does not
take the map down.

### Every lake popup carries its bound

> ND-001 — 2018-11-09
> 634,900 m²
> **within 2,000 m upstream (a lower bound: a longer search gives a larger lake)**
> classified

And when the distance was **not** recorded, the popup says
*"search distance not recorded, so the area cannot be interpreted"* rather
than showing a bare number. Silence would let a reader take it at face value.

### Verified on the real site

The persistence step now re-derives the shapes from the fused inputs rather
than reading a sidecar, so what the map draws is the same object the numbers
came from. On ND-001: the lake outline (634,900 m²), the deposit
(90,300 m²) and the blockage, all in EPSG:4326, rendering alongside the
CRITICAL marker and the disclaimer.

Eleven tests. `scripts/baige/05_persist_and_report.py` reproduces it.

### What this does not do

- **It does not make the area correct.** The lake is still AOI-truncated and
  still varies 3× with the search distance; the popup now says so, which is
  the most that can honestly be done without a wider AOI.
- **Only the date the outline was derived from carries one.** Attaching one
  date's shape to another would misreport where the water was, so the other
  two observations store an area and no geometry.
- **There is still no ground truth**, so a drawn outline is a classification,
  not a measurement of the lake.

---

## 30. Phase 6 gate — the first trained models

**Gate check (brief, Phase 6):** *per-class metrics plus the water-vs-shadow
confusion reported for both models.*

**Status: partially met, and the missing part cannot be met from this data.**
The architecture comparison the brief requires now exists on real labelled
data. The water-vs-shadow confusion — the project's primary scientific result
— is reported as the gate asks, but it is **empty by construction**, because
Landslide4Sense labels neither water nor terrain shadow. Only hand-labelled
Himalayan patches can fill it.

### The result

Trained on Colab from `notebooks/colab_train.ipynb`, Route A:
Landslide4Sense 2022 (CC BY 4.0), 3,799 labelled patches at 128x128, split by
event into 2,659 train / 570 validation / 570 test, 11 channels, class weights
`[1, 1, 5, 1, 1]`, monitored on macro IoU.

| class | plain U-Net | Attention U-Net |
|---|---|---|
| background / land | 0.9855 | **0.9864** |
| water | *(no pixels)* | *(no pixels)* |
| landslide / bare debris | 0.5499 | **0.5635** |
| terrain shadow | *(no pixels)* | *(no pixels)* |
| snow / ice | *(no pixels)* | *(no pixels)* |
| **macro (present classes)** | 0.7677 | **0.7749** |

| | plain U-Net | Attention U-Net |
|---|---|---|
| parameters | 7,852,037 | 7,984,041 (**+132,004**, +1.68%) |
| best epoch | 10 | **33** |
| early-stopped | yes | **no** (ran the full 40) |
| best validation macro IoU | 0.7792 | 0.7866 |

Absent classes report `None`, not `0.0`. The difference is the difference
between "the model failed at this" and "there was nothing to learn from", and
collapsing it would make the macro average meaningless.

### What this does establish

**The Attention U-Net outperforms the plain U-Net**, by **+0.0136 landslide
IoU** (+2.5% relative) for 1.68% more parameters. Because the baseline is
`plain_unet` — the same class with the gates removed, identical in depth,
widths, normalisation and upsampling — the difference is attributable to the
attention gates and not to any other implementation detail.

The more interesting difference is the training behaviour. **The plain U-Net
stopped improving at epoch 10 and early-stopped; the Attention U-Net was still
improving at epoch 33 and never early-stopped at all.** A gain measured at a
point where one model had converged and the other had not is a weaker claim
than the single number suggests — the gap might widen with a longer schedule,
or close.

### What this does not establish

1. **One seed.** `models.split.seed` is 0 and the run was not repeated. A
   +0.0136 difference is **well within the range a different split or
   initialisation could produce**, so this does not show the gates help;
   it shows they did help once. Several seeds are needed before the
   comparison carries weight, and the project's own standards would not accept
   a single run as a finding anywhere else.
2. **The water-vs-shadow confusion is empty.** `a_as_b` and `b_as_a` are 0
   and both rates are `None` because neither class exists in the data. **The
   project's central claim — that terrain-aware fusion separates water from
   shadow — remains entirely untested by any model.**
3. **Not Himalayan, and not this project's stack.** Landslide4Sense is not
   Himalayan terrain, carries no Sentinel-1, and has no illumination or
   terrain-shadow layer, so the models trained here use **11 of the 15
   configured channels** and have never seen SAR or a shadow mask. A
   checkpoint from this run cannot be applied to a full stack, and
   `models/predict.py` refuses the mismatch.
4. **Landslide IoU near 0.55 is moderate.** It is a working model, not a good
   one. The published Landslide4Sense competition results are the proper
   comparison and were not consulted here.
5. **No Himalayan accuracy figure follows from this.** Nothing in this run
   speaks to the Baige results in §§20-26.

### Three defects this run exposed, all in this project's code

The gate took four attempts. Each failure produced a *complete-looking* result
or a misleading error, which is the common thread worth recording.

**1. The class-weight tensor was built on the CPU.** It needed two conditions
at once — `class_weights` set and a non-CPU device — and the default config
sets no weights while the tests run on CPU, so neither alone trips it. It
surfaced only on the first real GPU run.

**2. A NaN input destroyed the model, silently.** This is the one worth
remembering. A normalised difference index is NaN where its denominator
vanishes, which is **correct** for the detection pipeline — NaN means
unmeasurable and the fusion treats it as absent evidence — but a network has
no such notion.

Measured: **one NaN among 22,528 input values turned all 7,852,037 weights
NaN on the first optimiser step.** After that `argmax` over all-NaN logits
returns index 0, so the model predicts background everywhere. The run then
completed its full schedule and reported:

* bit-identical metrics from both architectures, to sixteen decimal places,
  despite 132,004 parameters between them;
* landslide IoU exactly 0.0;
* background IoU 0.9782894736842105, which is **precisely** the background
  fraction of the test split;
* best epoch 1, early-stopped.

None of that looks like a crash. It looks like a finding. The arithmetic is
what gave it away: two different architectures cannot agree to sixteen
decimal places unless both outputs are degenerate.

Fixed in `PatchDataset`: a non-finite input becomes 0.0 **and the pixel's
label becomes `ignore_index`**, so it contributes nothing to the loss —
replacing the input alone would train the model to predict a real class for
ground with no measurement. Training also now **refuses to continue on a
non-finite loss**, because running through one produces a confident null
result, which is worse than an error.

**3. No input normalisation existed.** Found while diagnosing (2) and fixed
on the way: the stack spans orders of magnitude, and on synthetic data at
realistic scales standardisation alone moved landslide IoU from 0.127 to
0.769. Statistics come from the **training split only** — computing them over
all patches would leak the test distribution — and are stored in the
checkpoint so inference applies exactly what training saw.

A fourth, smaller one: normalisation must be applied **after** nodata
detection, since standardising maps an all-zero pixel away from zero and the
scene edge would then be classified rather than marked unseen. That is the
same failure as §24, Finding 4a, in a different module.

**Why the tests missed all of this.** The fixtures drew every band from
`normal(0.2, 0.08)` — already well scaled, never non-finite, and run on CPU
with no class weights. They exercised the plumbing and none of the conditions
that matter. The replacements use realistic per-channel scales, inject NaN and
infinity, and assert that weights stay finite; one of them demonstrates the
original failure so the fix is not guarding against a guess.

### Open items at the Phase 6 gate

1. **Repeat across seeds.** Until then the attention result is one
   observation, not a finding.
2. **The water-vs-shadow confusion still needs hand labels.** No public
   dataset labels terrain shadow, so this is unobtainable any other way.
3. **Compare against the published Landslide4Sense results** to know whether
   0.55 is competent or poor.
4. **The smp baseline was not run.** `MODEL_BASELINE` is wired and
   untried, so the brief's external baseline is still absent.
5. **The Attention U-Net had not converged** at the end of the schedule.

Artifacts: `comparison.json` and
`landslide4sense_conversion.json` in the run's Drive output directory.

---

## 31. A finding that changes how Baige must be scored

Before any hand digitising, the two Sentinel-2 scenes were rendered and
**looked at** rather than only computed on. That is worth doing once per
event: it showed something the numbers had not.

### The deposit is already present on the "pre-event" date

Baige dammed the Jinsha **twice** -- 2018-10-10 and 2018-11-03 -- and the
only usable optical pair straddles the *second* failure (validation.md 20:
no scene before the first passes the cloud filter). So the 2018-11-02 scene
is **post-first-failure**, and the pale debris mass is plainly visible in it.

Measured with one rule applied identically to both dates (B11 > 0.22
reflectance and NDVI < 0.15 -- a convention for this comparison, not a
detector):

| | bare bright debris |
|---|---|
| 2018-11-02, after the first dam | 0.8698 km² |
| 2018-11-09, after the second | 0.9704 km² |
| **already debris on both dates** | **0.4902 km² (50.5% of the 11-09 mass)** |
| new on 11-09 only | 0.4802 km² |

**Half the visible deposit predates the change-detection pair.**

### Why this would have corrupted the first accuracy figure

A digitiser tracing "the landslide" on 11-09 would naturally outline the whole
pale mass, because that is what a landslide looks like. Scored against a
change map that can only contain the increment, that outline would report
**recall near 6%** -- and the detector would be blamed for failing to find
material it was never shown.

The instruction in `scripts/baige/12_score_against_truth.py` has been
corrected: **digitise only what is new on 11-09**, by comparing the two dates.

### A second observation, corroborating 21

The downstream channel is unmistakably **blue (water) on 11-02 and pink
(dry or sediment-choked) on 11-09**, directly visible in the rendering. The
drainage that 21 inferred from water-mask arithmetic is plain in the imagery.
Two independent routes to the same conclusion.

### And a caution about the change map itself

Of the 3,189 change pixels, only **610 (19.1%)** fall on debris that is new
by the rule above, and 87 (2.7%) on debris that was already there. The
remaining 78% is neither -- consistent with 20's finding that 87% of the
flagged area is not the landslide, reached here by a different method.

The rule is crude and uncited, so this is a flag rather than a measurement.
But it means the forthcoming accuracy figure for Phase 5 is likely to be
**low, and correctly so**.

### What was not done

**No polygons were generated.** Producing them from the project's own
detectors and then scoring the detectors against them would be circular.
Interpreting the imagery by eye is possible -- the features are clear -- but
that interpretation has been anchored all session by these same detector
outputs, so it is not independent in the way ground truth must be. The
digitising remains the repository owner's to do.

Artifacts: `outputs/baige_2018_deposit_epochs.json`.

---

## 32. The first accuracy figure — the Baige barrier lake

Until now **no number in this project was an accuracy.** Every figure in
§§20-31 was a plausibility check: a distance to a published point, an
elevation, an area against a published figure, or two independent signals
agreeing. This section scores one quantity against a hand-drawn reference for
the first time.

### The reference, and how independent it is

The reference is a single polygon outlining the impounded lake on 2018-11-09,
drawn in QGIS by the repository owner over the false-colour Sentinel-2 scene
(R=B11, G=B8, B=B4), stored in `data/validation/baige_lake_truth.gpkg`
(EPSG:32647).

It is a **human interpretation by one annotator, not an absolute**, and it is
not fully independent of this project's work:

* the annotator was told roughly **where to look** (a map coordinate) and
  **what water looks like in that composite** (dark navy, not cyan);
* a first attempt traced the bright cyan patch at the south edge, which is
  snow or ice, and was discarded unsaved before the layer was written;
* the outline was drawn **without sight of the detection's outline**, which is
  the independence that matters most here.

### Result, as drawn

| | value |
|---|---|
| reference lake | 578,800 m² (5,788 px) |
| detected lake | 634,900 m² (6,349 px), 9.7% larger |
| **IoU** | **0.661** |
| precision | 0.760 |
| recall | 0.834 |
| F1 | 0.796 |
| true positive / false positive / false negative | 4,828 / 1,521 / 960 px |

Scoring excludes pixels the 2018-11-09 scene could not see (about 40% of it is
nodata), dropping them from **both** masks rather than counting reference drawn
over blind ground as a miss. The reference had none there.

**This is the official first-pass figure.**

### Where the errors are

An IoU of 0.66 does not say how the two disagree, and the two possible answers
point in opposite directions, so `scripts/baige/14_diagnose_lake_errors.py`
separates them. It uses the reference to **diagnose** the detection and changes
nothing: tuning thresholds against the same reference and then reporting the
improved score on the same event would be fitting the answer.

**Missed pixels are shoreline noise.** 86% of the 960 false negatives lie
within 3 px of the detected edge, and 47% within 1 px.

**Over-flagged pixels are mostly one patch.** Only 30% of the 1,521 false
positives are within 3 px of the reference. **A single contiguous patch of
1,042 px accounts for 69% of them**, at rows 0-26 against a reference that
begins at row 25 — the northern end of the lake, running to the scene's top
edge.

| shoreline tolerance | precision | recall | IoU |
|---|---|---|---|
| 0 px (as scored) | 0.760 | 0.834 | 0.661 |
| 1 px | 0.794 | 0.912 | 0.710 |
| 2 px | 0.817 | 0.952 | 0.746 |
| 3 px | 0.832 | 0.977 | 0.770 |

Sentinel-2 pixels are 10 m and a hand-drawn outline is good to roughly one or
two of them, so forgiving a few pixels of shoreline is a statement about
measurement resolution and not a way of improving the score. It is reported
because the as-scored figure mixes two different things.

### The 1,042 px patch, and what is and is not known

The patch has the **same spectral signature as the true positives** (B11
median 69 against 86, both dark in the near-infrared), sits at a similar
elevation (2,893 m against 2,877 m), touches the reference lake's northern end,
and runs to the scene edge as the lake does. That points to **the reference
stopping about 250 m short of the top edge**, not to a detection error.

That is a reading of the evidence and not a settled fact, and the person who
should settle it is the annotator, by looking at the image. **Should the
reference be extended, the score would be:**

| | precision | recall | IoU |
|---|---|---|---|
| as drawn | 0.760 | 0.834 | 0.661 |
| *if* the patch is included in the reference | 0.925 | 0.859 | 0.803 |

**The second row is conditional and is not the result.** Revising a reference
after seeing where the detection disagrees is a recognised source of bias, and
it is the circularity this whole exercise exists to avoid. If the reference is
revised, both figures are to be reported, the revision labelled post-hoc.

### A pre-scoring expectation that was wrong

§31 and the scoring script both anticipated that the lake would show **low
recall from truncation** by the 2000 m search window and the scene edge. It
showed the opposite: **recall is the higher of the two (0.83)** and precision
the lower. The truncation worry does not apply to this comparison, because the
reference is cut by the same scene edge as the detection.

The scoring script also printed that the thresholds were "too loose". On
these results that conclusion is unsupported, since most of the false
positives are one patch with a probable non-threshold explanation, and the
message has been replaced by a pointer to the diagnostic.

### A diagnostic that was wrong, and why

The first version of the diagnostic treated water on slopes over 15° as
suspect, reasoning that a lake surface is flat. For this lake that is
**backwards**: the DEM was acquired 2011-2014, four years before the lake
formed, so the slope under it is the old valley's, and the *true* positives
have the steeper median (24.4° against 19.8°). The logic was removed. The same
mistake would be easy to make again anywhere a post-DEM feature meets a
DEM-derived layer.

### What this establishes

The water detection that feeds the barrier-lake stage agrees with a human
outline of the lake to an IoU of 0.66, rising to about 0.77 once shoreline
disagreement of up to 3 px is forgiven, with the largest single discrepancy
having a plausible reference-side explanation.

### What it does not establish

* **One event, one date, one annotator.** Nothing here speaks to Nepal, to
  other lakes, or to inter-annotator agreement, which was not measured.
* **It scores the lake outline only.** It does not validate the blockage
  candidate, the trend, the depth, the volume or the **CRITICAL** warning.
  The warning level rests on factors this comparison does not touch.
* **The landslide layer has not been drawn**, so Phase 5 remains without an
  accuracy figure, and §31 expects it to be low.
* **The reference is not fully independent** (above).
* **Lake area remains a lower bound** (§22, §29). The reference is cut by the
  same scene edge as the detection, so this comparison cannot test whether the
  full lake is larger.

Artifacts: `outputs/baige_2018_accuracy.json`,
`data/processed/baige_lake_scored.npz` (the masks, kept for the diagnostic).

---

## 33. What the Baige CRITICAL level depends on

The Baige indicator is **CRITICAL at 0.798 against a threshold of 0.75**, a
margin of **0.048**. At that margin the useful question is not whether it is
CRITICAL but **which inputs would have to be wrong, and by how much, for it
not to be**. `scripts/baige/15_risk_sensitivity.py` varies one input at a
time, holding the rest at their measured values.

This is a **sensitivity analysis, not a validation.** It shows how robust the
output is to an error in each input. It says nothing about whether any input
is correct.

### The four measured inputs

| input | measured | stays CRITICAL from | margin | |
|---|---|---|---|---|
| **blockage confidence** | 0.750 | 0.610 | 0.140 (19%) | fragile |
| **lake growth rate** | +1,484.6 m²/day | 1,200 m²/day | 284.6 (19%) | **fragile** |
| median deposit slope | 36.1° | 23.5° | 12.6° (35%) | moderate |
| new landslide area | 90,300 m² | 39,500 m² | 50,800 m² (56%) | robust |

**Two inputs carry the level, and they are the two the project trusts least.**

* **Lake growth rate.** The level needs at least +1,200 m²/day. Flat, or
  falling, it drops to **HIGH RISK at 0.551**, and the two cases score the
  same because a negative rate clamps to the bottom of its scale. The
  measured +1,485 m²/day is the median of three pairwise slopes from a series
  that rose and then fell (634,900 → 697,000 → 654,200 m²): the slopes are
  +6,210, +1,485 and −14,267 m²/day, and the median simply picks the
  end-to-end slope, a net change of +3.0%. §26 already recorded that the
  trend's sign is not robust. This quantifies the consequence: **the CRITICAL
  level stands or falls on it, with a 19% margin.**
* **Blockage confidence.** The level needs at least 0.61. The same candidate
  scored **0.500** before merging, which gives **HIGH RISK at 0.715**. And
  §21 showed this score mis-ranks a drained reach above a real dam, so the
  input itself is the one with a documented flaw.

**The two inputs that look important turn out not to be.**

* **New landslide area** only matters below about **39,500 m²**, against
  90,300 m² for the merged candidate and roughly 480,000 m² of new bare
  material by §31's crude rule. No estimate in the project is near the
  threshold. This is why digitising the landslide layer is **low priority for
  the warning**: whatever it showed, the level would not change unless the true
  deposit were less than half the smallest estimate.
* **Slope** needs to stay above 23.5° against a measured 36.1°.

### The withheld volume is a real unknown

Depth and volume are withheld for this site (§24), and an unavailable factor
is **left out rather than scored as zero risk** (methods §11.2). So the 0.798 is a
score over the 9 units of weight that could be measured, not over 11.

A volume, were one available, would add weight 2 and pull the score toward its
own value. **What-if, not an estimate:**

| if the volume were | score | level |
|---|---|---|
| 0 m³ | 0.653 | HIGH RISK |
| 3,000,000 m³ | 0.707 | HIGH RISK |
| 5,000,000 m³ | 0.744 | HIGH RISK |
| 7,500,000 m³ | 0.789 | CRITICAL |
| 10,000,000 m³ | 0.835 | CRITICAL |

The level would stay CRITICAL only for a volume of at least **about
5,400,000 m³**. Published Baige figures are 105-775 × 10⁶ m³ (§2.2), far
above that and above the scale's 10⁷ m³ ceiling, so a real measurement
would very likely keep the level where it is. But that is context from the
literature and not something this system can show, since it cannot currently
measure the volume. **The honest statement is that the level is conditional on
a quantity it has declined to estimate.**

### What this changes about priorities

| | before | after |
|---|---|---|
| landslide reference layer | next step toward accuracy | **optional**: the level does not depend on it |
| more lake observations | a data-quality nicety | **the highest-value validation**: the level rests on a 3-point growth rate with a 19% margin |
| blockage-confidence ranking | a documented flaw (§21) | a flaw **on the critical path** of the warning |
| a water-surface model for volume | a depth problem (§24) | also decides whether the level is CRITICAL or HIGH |

### What this does not say

* **It does not say the warning is wrong.** The real Baige dam was impounding
  the Jinsha and downstream evacuations took place; a high indicator is
  defensible. What it says is that **this system reaches CRITICAL narrowly, on
  two inputs it measures weakly**, and that a reader should treat the
  distinction between CRITICAL and HIGH RISK here as unresolved.
* **One-at-a-time sweeps miss interactions.** A smaller growth rate *and* a
  lower confidence together would flip the level more easily than either
  alone, so the margins above are upper bounds on the robustness.
* **The scales and weights are conventions** (methods §11.4), and every margin here
  is measured against them. A different convention moves every threshold.

Artifacts: `outputs/baige_2018_risk_sensitivity.json`,
`scripts/baige/15_risk_sensitivity.py`.

---

## 19. End-to-end validation write-up

This is the write-up the brief asks for at Phase 13: what has been
validated, what has not, and what a reader should not conclude.

### A. Where the project stands

| Phase | Deliverable | Gate |
|---|---|---|
| 0 | Repo, config, logging, GEE auth, pytest | ✅ passed |
| 1 | Acquisition (S1, S2, Landsat, DEM) | ✅ passed |
| 2 | Preprocessing, shadow masks, co-registered stack | ✅ passed |
| 3 | Rule-based water detection | ✅ passed |
| 4 | Shadow-rejection fusion | ✅ passed; **re-verified** after the `cos_incidence` bug — §24, Finding 5a |
| 5 | Bi-temporal landslide change | ✅ passed on Baige 2018 — §20; magnitudes superseded by §25 |
| 6 | U-Net / Attention U-Net | ▲ **partially met** — both models trained, Attention U-Net ahead (§30); water-vs-shadow still needs hand labels |
| 7 | River blockage candidates | ✅ passed on Baige 2018 — §21; superseded by §25, then §26 (32 candidates → 2) |
| 8 | Barrier lake detection and tracking | ✅ passed on Baige 2018 — §22; magnitudes superseded by §25 |
| 9 | Temporal change | ✅ passed; §23, §25, §26 — **the trend's sign is not robust** |
| 10 | Depth and volume | ✅ passed (synthetic); run on real lake BL-001 — **numbers withheld**, see §24 |
| 11 | Risk indicators | ✅ passed; §23, §25, §26 — **MONITOR or CRITICAL depending on candidate merging** |
| 12 | Dashboard | ✅ passed; **detected geometry now drawn** — §29 |
| 13 | Reports + this write-up | ✅ passed |
| — | Storage layer (§10) | ✅ complete |
| — | End-to-end integration | ✅ complete (synthetic) |

**770 offline tests pass** (27 s). The 8 live Earth Engine tests also pass
as of 2026-11-06 (333 s).

### B. What has genuinely been validated against real imagery

Two sites. **Tsho Rolpa** for water and shadow, and **Baige 2018** for the
whole dam chain. Magnitudes below are the authoritative fused, merged run
(§25, §26); the earlier figures in §§20-23 are superseded.

**Tsho Rolpa — water and shadow**

- The lake is found at 1.601 km² (Phase 3) and 1.578 km² after fusion,
  against a published 1.537 km² and an independent DEM-epoch mask of
  1.550 km². Mean elevation 4,547 m against a published 4,546-4,580 m.
- Shadow rejection removed 87.5% of the index-only mask's false water while
  retaining 96.4% of the independently observed lake, and was robust across
  16 weight variants (80.1-89.0%).
- Branch B correctly returned no depth for a lake the DEM recorded (required
  test 8).
- Zero blockage candidates across a real 50 km² valley, including with a
  landslide placed on the channel (required test 4).

**Baige 2018 — the full chain, end to end**

| step | result |
|---|---|
| landslide change | 0.3189 km², 66 polygons |
| blockage | **1 significant candidate** on the Jinsha main stem (333,301 of the AOI's 334,834 drainage cells), confidence 0.750 |
| barrier lake | **634,900 m²** impounded upstream, one stable identity across four dates |
| trend | Increasing, +3.0% over 13 days |
| depth / volume | **withheld** — see C |
| indicator | **🔴 CRITICAL INDICATORS — verification recommended** (0.7979), four factors listed, 81.8% data coverage |
| report | 3-page PDF, carrying the level, the factors, the lake series, the disclaimer and depth marked unavailable |

The shadow-rejection fusion was also checked on this event with a test needing
no model: **a lake surface is level**, so no genuine water pixel sits far above
the waterline. The pixels the fusion removed had median slopes of **33.8° and
44.4°**, about 30% in terrain shadow. Water does not sit on a 44° slope.

**The storage layer and the report now hold real values.** Each carries its
`value_type`, and depth is stored as a Branch C row that says it is
unavailable and why, rather than being omitted — a missing row and a row that
records a refusal mean different things to a reader.

### C. What has *not* been validated

1. **Exactly one accuracy figure exists in this project** (§32): the Baige
   lake outline, IoU 0.661 as drawn, against one annotator's reference.
   **IoU, precision and recall remain unmeasured for every other quantity** —
   the landslide change map, the blockage candidate, the trend, the depth and
   the risk level. Everything else in B is plausibility: a distance, an
   elevation, an area compared with a published figure, or an agreement
   between two independent signals.
2. **Depth and volume are withheld for the real lake** (§24). A single
   shoreline water-surface elevation does not describe a long impoundment in
   a steep valley — the spread is ±24.61 m on a surface that must be level —
   and 64% of the lake is pre-existing channel the DEM recorded as a surface
   (Branch B). A traceable Branch A lower bound over the newly flooded ground
   alone is 6.34 × 10⁶ m³, and **no published Baige volume is comparable** to
   it.
3. **The trend's sign is not robust** (§26). Unmerged it read Decreasing at
   3.4× the stability band; merged, Increasing at 2.2×. Both are within a
   factor of four of Stable, on three observations — the configured minimum.
4. **The warning level turns on one methodological choice.** Candidate
   merging moved this site from MONITOR (0.3909) to CRITICAL (0.7979), and
   merging did not exist until it was written. **No level published before
   §26 is reliable.**
   §33 quantifies how narrow it is: the level is CRITICAL by 0.048 and
   needs both a growth rate of at least 1,200 m²/day (measured 1,485, from
   three observations) and a blockage confidence of at least 0.61 (the same
   candidate scored 0.50 before merging).
5. **A trained comparison exists but on one seed, and the central claim is
   still untested.** Both models are trained and the Attention U-Net leads by
   +0.0136 landslide IoU (§30) — a gap well within what a different seed
   could produce. The **water-vs-shadow confusion is empty**, because no
   public dataset labels terrain shadow, so the project's primary scientific
   claim has never been tested by any model.
6. **One real event, in Tibet.** Nothing has been processed in Nepal, the
   brief's primary study area. The Lhende/Rasuwa event has no confirmed
   coordinate.
7. **Lake area is a lower bound within a search distance.** It is
   AOI-truncated and varies 3× with `upstream_search_m`, which is not stored
   or displayed alongside it.
8. **Over-detection is reduced, not solved.** 32 candidates became 2 by
   merging, and the second is a negligible tributary feature — but the ratio
   was 153:1 before two separate gates were added.

### D. Required system tests

| # | Scenario | Status |
|---|---|---|
| 1 | Normal terrain → no water | unit-level only; needs a real snow-free, water-free AOI |
| 2 | Shadowed valley, no lake → shadow | ✅ pass, incl. real imagery (<2% of steep shadowed terrain called water) |
| 3 | Known lake in a shadowed valley → water | ✅ pass on real imagery |
| 4 | Landslide near a river → no blockage without evidence | ✅ pass, incl. on the real channel |
| 5 | Landslide crossing a river with evidence → candidate | synthetic pass; real gate pending |
| 6 | Water upstream → barrier lake | synthetic pass; real gate pending |
| 7 | Expanding lake → Increasing, higher concern | ✅ pass (synthetic series) |
| 8 | Lake in the DEM epoch → depth unavailable | ✅ **pass on real data** |
| 9 | Cloudy-only range → graceful, no crash | ✅ pass |

Six of nine pass; three await imagery of a confirmed event.

### E. The findings that changed the system

Each was measured, not assumed, and each would have produced a plausible
wrong answer:

| # | Finding | Where |
|---|---|---|
| 1 | MNDWI **is** NDSI, so it scores snow as water — merging the lake into a 13.3 km² glacier blob | methods 3.2 |
| 2 | Single-scene SAR amplitude thresholding fails in steep terrain: 47.6% of the AOI called water | methods 3.5 |
| 3 | A hard-split separation statistic certifies *any* unimodal histogram as bimodal (2.67 > 2) | methods 3.4 |
| 4 | Flatness is a necessary condition for water, not evidence of it — the ablation caught it | methods 4.4 |
| 5 | The Branch A formula on a Branch B lake swings 2.2× with an arbitrary buffer width | methods 10.3 |
| 6 | Two real dates would have reported a confident 19% decline that is half cloud, half shadow | methods 9.4 |
| 7 | The cited slope gate (>15°) removes the dam, which sits on the flat valley floor | methods 5.9 |
| 8 | A barrier lake is connected to the river it dams, so component-level "upstream" tests fail | methods 8.1 |
| 9 | Two wide upstream/downstream zones overlap and cancel, erasing the impoundment | methods 8.2 |
| 10 | A green indicator on 9% data coverage is the most dangerous output the system can emit | methods 11.3 |
| 11 | A **growing** barrier lake was reported as *disappeared*, claiming its footprint "held no water" while 40.9% of it was still wet — the code never tested for water | methods 8.9 |
| 12 | "Upstream" ignored "on the same stream": every low-accumulation tributary in a 4 km box counted, so consecutive dates' lakes overlapped by **exactly 0 pixels** | methods 8.7 |
| 13 | The upstream reference was the blockage's **median** accumulation, which puts the main stem downstream of a dam straddling a confluence | methods 8.8 |
| 14 | Phase 7 bypassed Phase 5's own minimum area: **76 of 153 candidates were a single 10 m pixel**, and 18 scored confidence 1.000 on evidence they inherited | methods 7.9 |
| 15 | Fragments of one dam each claimed the same impounded water — **the same water counted seven times** — so ranking by it chose an arbitrary fragment | methods 7.14 |
| 16 | The published event coordinate is the landslide **source area** on a 52.9° slope, 471 m above the river, not the blockage | methods 5.13 |
| 17 | `cos_incidence` used a BLAS matrix product that dies above ~300×300×3 on this machine with **no traceback and exit code 0**, silently disabling every terrain-shadow call at AOI scale | methods 10.14 |
| 18 | The whole Baige chain therefore ran on **unfused** water; re-derived, the lake is 44.6% smaller and the trend falls from −28.3% to −4.3% | §25 |
| 19 | The split buffer was applied **after** block assignment, so a block could be given to `test` and then lose every patch to the buffer | §27 |
| 20 | A draining lake and a static lake score **identically** on the heaviest risk factor, so a breach reads as nothing to report | methods 11.10 |

### F. What a reader must not conclude

- **This system does not predict dam failure.** It reports indicators, and
  every level is hedged in the brief's own wording.
- **A level is not a probability.** The risk weights are conventional and
  uncalibrated; `p_water` is an evidence score through a softmax with no
  reliability diagram behind it.
- **Agreement with a published lake area is not accuracy.** It is a
  plausibility check at one site on one date, against a figure that predates
  the imagery.
- **Absence of a warning is not safety.** Most factors are unavailable most
  of the time, which is why coverage travels with every level and why a
  thinly-evidenced NORMAL is withheld from showing green.

### G. What would most improve confidence, in order

1. **More reference masks.** The lake now has one (§32). The landslide
   deposit does not, but §33 shows the warning level does not depend on it, so
   it is **optional**: digitising only the material new on 11-09 (§31) would
   give Phase 5 an accuracy figure and would not change the level. A second annotator on the lake would show how
   much of the 0.66 is disagreement between people rather than between a
   person and the detector. No amount of further engineering substitutes.
2. **Hand-labelled patches across at least 3 areas 10 km apart**, which
   closes the Phase 6 gate and is the only source of the terrain-shadow class
   — no public dataset labels it (§27, `docs/labelling.md`).
3. **A second and third real event, at least one in Nepal.** Everything
   measured here is one dam in Tibet, and the Lhende/Rasuwa event needs a
   confirmed coordinate.
4. **A water-surface model that handles a sloping impoundment**, which is the
   blocker for any depth or volume at a real site (§24).
5. **More observations per lake.** Three is the configured minimum and the
   trend's sign is not robust at it; the module is right to refuse to say
   more, which makes this a data problem rather than a code one. §33 shows
   why this outranks any reference mask for the warning: the CRITICAL level
   needs a growth rate of at least 1,200 m²/day, and the measured +1,485
   rests on three points, a 19% margin.
6. **An AOI that follows the channel upstream.** A blockage-centred box is
   the wrong shape for a lake that backs up a valley, and it truncates every
   area reported.
7. **Radiometric terrain correction for Sentinel-1** — still the place the
   evidence is weaker than it looks (§3.5).
8. **Resolving Smart App Control.** It has cost a 3½-hour test run with 97
   spurious failures, and it silently disabled the project's core
   contribution for the entire Baige analysis (finding 17 above).

### H. The honest one-paragraph summary

The system runs end to end on one real landslide dam and produces a defensible
CRITICAL indicator with its factors listed, having found the blockage on the
correct river without being told where to look. Every number it produces is
traceable to a cited method or a recorded convention, every refusal to
estimate is recorded as a refusal rather than an omission, and twenty
distinct ways of being confidently wrong were found and fixed by measurement
rather than inspection. **It has been checked against a hand-drawn
reference in exactly one place, the lake outline (IoU 0.66, §32); its
warning level moved two levels on a single methodological choice; its trend's
sign is not robust; and the segmentation model the project is named for has
only been trained on a dataset that cannot test its central claim, with the
Attention U-Net's advantage resting on one seed (§30).** It is a working
research prototype with
well-documented limits, not a validated instrument.
