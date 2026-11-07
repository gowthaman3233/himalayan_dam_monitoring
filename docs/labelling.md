# Labelling Guide (Phase 6)

**Status: specification; no labelling done, no training data, no model
trained.** This file records the rules so that labelling, when it starts, is
consistent and auditable; the dataset mappings and inter-labeller notes are
added once the real data is inspected.

What *does* exist is the machinery these labels will feed:
`models/attention_unet.py` (the Attention U-Net and a controlled plain-U-Net
baseline) and `models/evaluate.py` (per-class IoU/Dice/precision/recall/F1,
the confusion matrix, and the explicit water-vs-shadow block described under
"Metrics" below). See `docs/methods.md` §6.

---

## Classes

From the project brief, Section 7.5:

| ID | Class | Meaning |
|---|---|---|
| 0 | background / land | Vegetated or bare ground that is not landslide debris; built surfaces; anything not covered below. |
| 1 | water | Open water: river channel, lake, barrier lake, reservoir. |
| 2 | landslide / bare debris | Fresh landslide scar, deposit, or bare debris surface. |
| 3 | terrain shadow (material indeterminate) | Topographic shadow so deep that the surface material **cannot** be determined. |
| 4 | snow / ice | Snow cover, glacier ice, lake ice. |

---

## The labelling rule

> **Label by surface material wherever the material can be determined. Use class
> 3 only where terrain shadow makes the material indeterminate. A landslide scar
> or lake inside shadow keeps its material class if it is identifiable.**

This rule is the heart of the project, so it is worth being explicit about why.

Class 3 is **not** "pixels that are in shadow". It is "pixels whose material is
unknowable *because* they are in shadow". The two are different, and conflating
them would defeat the purpose:

- A lake in deep shadow is **class 1 (water)**, not class 3 — provided it can be
  identified as water from SAR backscatter, from the shape and context of the
  shoreline, or from a less-shadowed observation on another date. The whole point
  of Phase 4 is to recover exactly these pixels.
- A hillside in shadow whose material is still legible (vegetation texture
  visible, snow still bright) takes its **material** class.
- A hillside in shadow that is simply black, with no usable signal from any
  input channel, is **class 3**. This is an honest "we cannot tell", and the
  model is allowed to say it.

Class 3 is therefore expected to be a **minority class**, and a label set where
class 3 covers most shadowed terrain indicates that the labeller defaulted to it
instead of using the SAR and multi-temporal evidence.

### Evidence a labeller may use

Deciding the material inside shadow requires more than the RGB composite. All of
the following are legitimate:

- Sentinel-1 VV/VH backscatter (water is specularly dark; shadowed rock is not).
- The SAR layover/shadow mask — where SAR is itself unreliable, the pixel is more
  likely a genuine class 3.
- Illumination (hillshade) and the terrain-shadow mask, to confirm the pixel is
  shadowed rather than dark-surfaced.
- Another date with better sun geometry over the same ground.
- The DEM: water surfaces are flat and occupy valley floors.

### Boundaries and ambiguity

- Label the **shoreline** at the water's edge as visible at 10 m. Do not
  interpolate a smoother line than the pixels support.
- Where two classes genuinely mix within one pixel, assign the dominant
  material.
- If a patch is more than roughly half cloud, discard the patch rather than
  labelling under cloud. Cloud is not a class here; cloud masking is Phase 2's
  job, and a labelled patch must not encode cloud as terrain.
- **Cloud shadow is not terrain shadow.** Class 3 covers topographic shadow only.
  A patch with significant cloud shadow is discarded.

---

## Public datasets

Checked against the official repositories on **2026-11-07**. Both sources are
`enabled: false` in `config/config.yaml` and **nothing has been downloaded**,
for the licence reason below.

### What was verified, and what was not

| | Sen1Floods11 | Landslide4Sense 2022 |
|---|---|---|
| source | `cloudtostreet/Sen1Floods11` (GitHub) | IARAI, Zenodo record |
| label values | **−1 No Data / Not Valid, 0 Not Water, 1 Water** ✅ verified | **0 non-landslide, 1 landslide** ✅ verified |
| size | ~14 GB | ~3.1 GB |
| bands | Sentinel-1 and Sentinel-2 chips | 14: S2 B1–B12, DEM, ALOS PALSAR slope, all ≈10 m |
| patch size | chips (see repo) | **128×128** |
| format | GeoTIFF chips in GCS | **HDF5** `TrainData/img/image_N.h5`, `TrainData/mask/mask_N.h5` |
| **licence** | ⚠️ **not stated on the repository** | ✅ **CC BY 4.0**, verified on the Zenodo record itself |
| splits | per-event `train_chip` / `val_chip` counts suggest event-based; **not confirmed** | train 3,799 / val 245 / test 800 |

**Landslide4Sense is usable; Sen1Floods11 is not.**

*Landslide4Sense* is **Creative Commons Attribution 4.0 International**, read
from the Zenodo record (10.5281/zenodo.10463239) on 2026-11-07 rather than
from a mirror. Files: `TrainData.zip` 2.5 GB, `ValidData.zip` 143.4 MB,
`TestData.zip` 470.9 MB. Attribution is required:

> Ghorbanzadeh, O., Xu, Y., Ghamisi, P., Kopp, M. and Kreil, D. (2022),
> "Landslide4Sense: Reference Benchmark Data and Deep Learning Models for
> Landslide Detection", *IEEE Transactions on Geoscience and Remote Sensing*
> 60, 1-17.

*Sen1Floods11* still carries **no licence text or file** on its repository, so
it remains unusable: training on data under unknown terms is not a risk this
project should take silently. Its download bucket is also ambiguous — the
page gives both `gs://senfloods11/` and `gs://sen1floods11`.

### Three consequences that shape Phase 6

**1. Neither dataset labels terrain shadow.** Both are binary. Class 3 — the
project's core scientific contribution — has **no public source at all** and
can only come from hand labelling. This is the single largest dependency in
Phase 6, and it cannot be worked around by downloading more data.

**2. Landslide4Sense's usable set is 3,799 patches, not 4,844.** Labels are
public for the **training split only**; the 245 validation and 800 test
patches are withheld for competition ranking. Our own geographic split must
therefore be carved out of the 3,799, and the competition's own splits cannot
be reused.

**3. Patch sizes disagree with this project's.** Landslide4Sense is 128×128
against our 256×256 (`models.patch.size_px`, from the brief). Its patches are
tiled or padded up rather than cropped, since cropping a 128-pixel patch to
256 is impossible and upsampling would invent detail. Sen1Floods11 has no DEM
or slope layer, so the `DEM`, `SLOPE`, `ILLUMINATION` and `TERRAIN_SHADOW`
channels must be filled from this project's own Copernicus DEM over the same
footprint, or masked out for those patches.

### The label mapping

Held in `models.sources.<name>.label_map` in config, applied by
`models.dataset.map_labels`, which **raises on any source value the map does
not cover**. An unmapped label is not defaulted to background: doing so would
turn an undocumented class into training signal for "land", and nothing
downstream could detect it.

| source | source value | our class | reasoning |
|---|---|---|---|
| Sen1Floods11 | −1 | `ignore_index` (255) | the source's own no-data marker is not an observation |
| Sen1Floods11 | 0 | 0 `background` | "Not Water" is the source's negative class, not a material claim |
| Sen1Floods11 | 1 | 1 `water` | direct |
| Landslide4Sense | 0 | 0 `background` | as above |
| Landslide4Sense | 1 | 2 `landslide` | our class 2 is "landslide or bare debris" |

**A note on what "Not Water" means.** Both datasets' zero class is "not the
thing I label", not "land". A Sen1Floods11 chip containing a landslide scar or
a snowfield labels it 0, so training on these sources teaches the model that
such surfaces are background. That pushes against classes 2, 3 and 4 and is a
reason to weight hand-labelled Himalayan patches heavily, or to restrict the
loss on externally sourced patches to the classes that source actually
distinguishes. The latter is not implemented; it is recorded as an open item.

### Channel availability by source

| channel group | Sen1Floods11 | Landslide4Sense | hand-labelled |
|---|---|---|---|
| S2 B2–B12 | ✅ | ✅ (B1–B12) | ✅ |
| NDWI / MNDWI / NDVI | derived from S2 | derived from S2 | derived from S2 |
| S1 VV / VH | ✅ | ❌ | ✅ |
| DEM / slope | ❌ (fill from our DEM) | ✅ | ✅ |
| illumination / terrain shadow | ❌ (compute from our DEM) | ❌ (compute) | ✅ |

A channel a source cannot supply must be filled from this project's own data
over the same footprint, or masked. It must **not** be zero-filled and left
unmarked: `models/predict.py` treats an all-zero stack as unobserved for
exactly this reason, and a zero-filled training channel would teach the model
that "no data" is a valid value for real terrain.

## How much ground to label, and where

**Read this before labelling anything.** The answer is counter-intuitive and
it decides whether the work is usable.

A geographic split partitions **blocks of ground**, and patches within
`split.buffer_px` of a block edge are discarded so that no retained patch
spans two partitions. With the shipped defaults that has a sharp consequence:

| | value |
|---|---|
| block | 10 km |
| buffer | 256 px = **2,560 m** |
| patch | 256 px = 2,560 m |
| **usable interior per block** | 4.88 km square = **23.8 km², only 24% of the block** |

The buffer is a band around *every* edge, so most of a block is unusable, and
**a single study area cannot be split at all**. The Baige AOI — a 3 km buffer,
about 28 km² — is smaller than one block: labelling it exhaustively yields a
training set with no validation or test partition, and metrics on an empty
partition are undefined, not zero.

Measured, with 12 patches at each site and sites one block apart:

| separated sites | train / val / test | usable? |
|---|---|---|
| 1 | 9 / 0 / 0 | ❌ |
| 2 | 9 / 0 / 9 | ❌ no validation |
| **3** | **9 / 9 / 9** | ✅ minimum |
| 6 | 36 / 9 / 9 | ✅ |
| 10 | 63 / 18 / 9 | ✅ |

### So

* **Label in at least 3 areas, each at least 10 km from the others.** Six to
  ten is better, so no partition rests on a single site's quirks of
  illumination and terrain.
* **Spread beats depth.** Within a site only the patches matter, not full
  coverage: a handful of 2,560 m squares of carefully labelled ground is worth
  more than one exhaustively labelled valley, which cannot be split.
* **Keep labels clear of block edges**, or place sites near block centres. A
  patch on a boundary is discarded however good it is.
* `split.block_km` and `split.buffer_px` are configurable, and widening the
  block is the right response to a dataset concentrated in one region — but it
  weakens the separation the split exists to provide, so change it
  deliberately and say so when reporting.

Artifact: `outputs/phase6_labelling_footprint.json`.

---

## Hand-labelled Himalayan patches

**pending Phase 6.** To be produced in QGIS over real Sentinel-2/Sentinel-1
imagery, concentrating on what the public datasets lack: deep terrain shadow,
snow/ice, and water inside shadow.

Each labelled patch must record: the source scene IDs, acquisition dates, the
MGRS tile, the labeller, the date of labelling, and any pixels the labeller
marked as uncertain.

### What to deliver

`models/build_patches.py` takes a **co-registered stack** and a **label
raster**, and the contract is narrow on purpose:

* a **single-band GeoTIFF on exactly the stack's grid**, holding this
  project's class integers 0-4;
* **`ignore_index` (255) wherever nothing was labelled** — never 0.

The second point is the one that goes wrong. A QGIS export of rasterised
polygons defaults empty space to zero, which is our `background` class, so an
unedited export tells the model that every unvisited lake, scar and shadow is
land. `build_patches` warns when over 98% of labelled pixels are background,
which is that mistake's signature, but the warning cannot repair the data.

The grid must match exactly: a label raster offset by one pixel mislabels
every boundary in the scene while looking entirely reasonable, so the builder
refuses a mismatch rather than resampling.

Pixels where the stack has no observation are forced to `ignore_index`
whatever the label says — a label without a measurement cannot be trained on.

---

## Splits

Train/validation/test splits are **geographic or event-based** (brief, Section
7.5). Random pixel or random patch splits are not permitted, because spatially
adjacent patches share terrain, illumination and sensor geometry, and would leak
the test set into training — inflating the reported metrics without improving
the model.

**Implemented** in `models.dataset.assign_splits`:

* `models.split.strategy` offers only `geographic` and `event`. There is no
  `random` option, so it cannot be selected by accident.
* **Blocks of ground are partitioned, never patches.** With `geographic`, a
  `block_km` grid is assigned to partitions and every patch follows its block.
  With `event`, a whole labelled event goes to one partition.
* **Patches within `buffer_px` of a block boundary are discarded.** Two
  256-pixel patches whose origins are 128 pixels apart share half their
  ground; without the buffer, a patch either side of the line puts the same
  terrain in train and test. The default buffer is one patch edge.
* The assignment is **seeded and reproducible**, and
  `models.dataset.split_summary` is written into the run's `comparison.json`
  so a reported metric carries the split it was measured on.
* A high drop rate is **warned about**: the buffer is a band around every
  block edge, so its cost grows as the buffer approaches the block size, and
  losing most of a hand-labelled set to it is a configuration problem rather
  than a safety feature.

The split is derived from config and the patches' own recorded coordinates, so
it is reproducible from the repository rather than stored as a separate
artefact.

---

## Metrics

Per-class IoU, Dice, precision, recall and F1, plus the full confusion matrix.
Overall accuracy is **not** a headline metric: with class 0 dominating, a model
that never predicts class 3 could still score well.

The **water-vs-shadow confusion** — the off-diagonal cells between class 1 and
class 3 — is reported explicitly as the project's primary result, for both the
plain U-Net baseline and the Attention U-Net.
