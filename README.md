# Himalayan Landslide-Dam and Barrier-Lake Monitoring

Early detection of landslide-induced river blockages and barrier-lake expansion in
Himalayan valleys, using multi-modal Sentinel-1/2 fusion, terrain-aware shadow
rejection and Attention U-Net segmentation.

> **Research prototype output. Not an official warning. Verify with authoritative sources.**
>
> This is a research decision-support prototype. It does not predict when a dam
> will fail, does not declare that a dam will form, and does not issue official
> warnings.

The full project brief — scope, method requirements, data-integrity rules and
phase gates — is in [CLAUDE.md](CLAUDE.md). Read it before contributing.

---

## Status

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Repo, environment, config + schema, logging, GEE auth, pytest skeleton | ✅ gate passed |
| 1 | Acquisition: S1, S2, Landsat and DEM for an AOI and date range, with metadata | ✅ gate passed |
| 2 | Preprocessing: cloud mask, SAR processing, terrain/SAR shadow masks, co-registered stack | ✅ gate passed |
| 3 | Rule-based water detection (optical + SAR) | ✅ gate passed |
| 4 | Shadow rejection fusion with probabilities | ✅ gate passed |
| 5 | Bi-temporal landslide change detection | module complete; gate awaiting imagery |
| 10 | Depth and volume (Branch A/B/C) | ✅ gate passed — taken early, as it needs no new imagery |
| 11 | Risk indicators and warnings | ✅ gate passed |
| — | Storage layer (brief §10) — not a numbered phase | ✅ complete |
| 9 | Temporal change and trend | ✅ gate passed |
| 7 | River blockage detection | module complete; positive gate awaiting imagery |
| 8 | Barrier lake detection and tracking | module complete; gate awaiting imagery |
| — | End-to-end integration (synthetic event) | ✅ complete |
| 12 | Streamlit dashboard | ✅ gate passed |
| 13 | Report generation + validation write-up | **gate passed, in review** |
| 6 | Dataset building, U-Net + Attention U-Net (Colab) | **architecture + metrics complete; training blocked on labels and Colab** |

**689 offline tests passing**, plus the **8 live Earth Engine tests now passing again** (697 total) — the acquisition layer is re-validated against the live catalog. The 8 live Earth
Engine tests were not re-run this session -- they need `earthengine
authenticate` -- and are unchanged since Phase 1. All six collection
IDs verified against the live catalog; seven GeoTIFFs exported with metadata
sidecars. See [`docs/validation.md`](docs/validation.md) for the verification
record and [`docs/methods.md`](docs/methods.md) for the citation register.

Explore an AOI end to end with [`notebooks/01_explore_aoi.ipynb`](notebooks/01_explore_aoi.ipynb).

Findings worth knowing:

- `COPERNICUS/DEM/GLO30` is **deprecated**; this project uses
  `GLO30_2024_1`, which carries the per-tile acquisition dates that Section 8's
  depth branching depends on. Measured epoch over the default AOI:
  **2011-01-05 → 2014-09-08**. See [`docs/methods.md`](docs/methods.md) §0.6.
- `COPERNICUS/S1_GRD` serves VV/VH **already in decibels**, so the dB conversion
  the brief asks for in Section 7.1 must **not** be applied again. See
  [`docs/methods.md`](docs/methods.md) §1.4.
- **MNDWI is the same expression as NDSI**, so it scores snow as water by
  construction. Over the default AOI that merges Tsho Rolpa into a 13.3 km²
  blob of glacier. A cited near-infrared screen (Hall et al. 1995) recovers the
  lake at 1.578 km² against a published 1.537 km².
  See [`docs/methods.md`](docs/methods.md) §3.2.
- **Single-scene Sentinel-1 amplitude thresholding fails in this terrain**: it
  selects 47.6% of the AOI as water, and excluding radar layover/shadow does not
  repair it. Phase 4 contains this but does not repair it.
  See [`docs/methods.md`](docs/methods.md) §3.5.
- **Shadow rejection removes 87.5% of the index-only mask's false water while
  retaining 96.4% of the independently observed lake surface**, and the result
  holds across every weight variant tried (80.1-89.0% removed).
  See [`docs/methods.md`](docs/methods.md) §4.6.
- **Flatness is a necessary condition for standing water, not evidence of it.**
  Treating slope symmetrically manufactured water on valley floors and flat
  glacier surfaces -- the ablation caught it, because dropping the slope term
  *reduced* detected water. See [`docs/methods.md`](docs/methods.md) §4.4.
- **The Branch A depth formula, applied to a lake the DEM already recorded,
  gives 14.3, 21.7 or 30.9 million m³** depending only on how wide the
  shoreline ring is. All three look plausible; none is traceable to a
  measurement of the bed. This is why Section 8's branch rule exists, and the
  system emits none of them. See [](docs/methods.md) §10.3.
- **A green indicator was the dangerous part of the warning design.** A
  NORMAL level built from 9% of the evidence printed 🟢, and a dashboard may
  render only the symbol. It is now ⚪ when NORMAL rests on thin evidence —
  but never on HIGH or CRITICAL, where withholding would mute a real alarm.
  See [`docs/methods.md`](docs/methods.md) §11.3.
- **The database refuses values the system promised not to produce.** The
  Section 10 value-type vocabulary and Section 8's "an unavailable depth is
  not a number" are SQL `CHECK` constraints, so a bug upstream cannot persist
  a plausible-looking volume for a lake whose bed was never measured.
  See [`docs/methods.md`](docs/methods.md) §D.2.
- **Two real dates would have reported a confident, false decline.** Tsho
  Rolpa measures 1.6005 km² then 1.2977 km² five days apart — a 19% "loss"
  that is half cloud obscuration and substantially half terrain shadow. The
  system reports **Unknown**, because three valid observations are required.
  See [`docs/methods.md`](docs/methods.md) §9.4.
- **A lake that cannot be seen has not disappeared.** A barrier lake
  vanishing reads as a breach, and cloud produces exactly that appearance. An
  absence is only called a disappearance when at least half the lake's last
  known footprint was observable. See [`docs/methods.md`](docs/methods.md) §8.3.
- **The cited slope gate removes the dam.** `min_slope_deg = 15` is right for
  shallow-landslide *source* areas (Notti et al. 2023) and wrong for landslide
  *dams*, whose deposits lie on the flat valley floor. Left at 15° it splits a
  river-blocking landslide in two and raises duplicate dam candidates.
  See [`docs/methods.md`](docs/methods.md) §5.9.
- **WeasyPrint installs but cannot import on Windows** — it needs GTK/Pango
  libraries Windows does not ship. PDF generation is engine-agnostic and falls
  back to headless Edge/Chrome, which needs no install. The HTML report is
  produced by Jinja2 alone and survives having no PDF engine at all.
  See [`docs/methods.md`](docs/methods.md) §13.2.
- **Overall accuracy is refused, not merely discouraged.** With water at ~4%
  of pixels, predicting "land" everywhere scores ~87% while finding no lakes.
  `models/evaluate` has no `accuracy` attribute; a test shows a scene where
  *every* shadow pixel is called water yet accuracy reads 0.90.
  See [`docs/methods.md`](docs/methods.md) §6.3–6.4.
- **Ten configuration keys had no reader.** An audit of all 182 schema leaf
  fields found controls that looked real and did nothing — including
  `gee.max_request_pixels`, documented as refusing oversized requests so "a
  mistyped AOI cannot try to pull a full Sentinel scene onto a laptop". That
  protection did not exist. Nine are now wired and tested; see
  [`docs/methods.md`](docs/methods.md) §A.
- **`ee.Initialize` takes ~4.6 minutes on this machine.** OAuth and the API
  both work (the discovery document fetches in 2 s by `curl`), so it is
  client-side slowness, not a broken network. Batch Earth Engine work into one
  long-running process rather than many short ones.
- **Smart App Control is now actively disruptive**, intermittently blocking
  `scipy`, `numpy.random` and numpy's BLAS. One test run took 3 h 29 min with
  97 spurious failures; the same suite passed in 81 s once the block lifted.
  See [`docs/validation.md`](docs/validation.md) §8, open item 5.

---

## Setup

### 1. Create the conda environment

GDAL and rasterio must come from **conda-forge**, never pip.

```bash
conda env create -f environment.yml
conda activate himalaya
```

<details>
<summary><strong>If conda fails with <code>CondaToSNonInteractiveError</code></strong></summary>

Miniconda ships with the Anaconda `defaults` channel configured, and recent conda
versions refuse to proceed until that channel's Terms of Service are accepted.
This project does not use `defaults` at all — `environment.yml` declares
`conda-forge` and `nodefaults` — but the Terms-of-Service check inspects the
*configured* channels before it ever reads the file, so `conda env create` is
blocked anyway.

`conda env create` does not accept `--override-channels`, and `CONDA_CHANNELS`
is not honoured by it either. The workaround that does work is to use
`conda create`, which does accept the override, with the same package list:

```bash
conda create -n himalaya -y --override-channels -c conda-forge \
  python=3.11 gdal rasterio rioxarray xarray numpy \
  geopandas shapely pyproj fiona \
  earthengine-api geemap \
  pyyaml "pydantic>=2.6" python-dotenv \
  matplotlib pytest pytest-cov tqdm pip
```

`environment.yml` remains the source of truth for what the environment contains;
the command above is purely a channel workaround and must be kept in step with
it.

The alternatives both have side effects beyond this project, so they are left to
you as deliberate choices rather than applied automatically:

- **Accept the Anaconda Terms of Service** (a licensing decision — note that
  Anaconda's terms restrict commercial use of the `defaults` channel):
  ```bash
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
  ```
- **Drop `defaults` from your global config** and use conda-forge everywhere.
  This changes the behaviour of every other conda project on the machine:
  ```bash
  conda config --remove channels defaults
  conda config --add channels conda-forge
  ```

</details>

<details id="smart-app-control">
<summary><strong>Windows Smart App Control — <code>An Application Control policy has blocked this file</code></strong></summary>

If an import fails with:

```
ImportError: DLL load failed while importing sparse:
An Application Control policy has blocked this file.
```

then Windows **Smart App Control** is enabled in enforcement mode and is
blocking compiled extension modules it does not recognise. Check with:

```powershell
Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' |
  Select-Object VerifiedAndReputablePolicyState
#  0 = off, 1 = enforcement, 2 = evaluation
```

Smart App Control allows or blocks binaries by **reputation**, so brand-new
package builds are blocked while older, widely-deployed ones pass. The block is
per-binary and is not fixed by reinstalling from a different channel — on this
machine, `pandas` 3.0.6 was blocked from *both* conda-forge and PyPI, while
`numpy`, `rasterio`, `pyproj` and `shapely` were unaffected.

**Workaround used here** — install a well-established pandas build:

```bash
conda activate himalaya
pip install --force-reinstall --no-deps "pandas==2.2.3"
pip install pytz tzdata          # pandas 2.x needs pytz; pandas 3.x dropped it
```

**The permanent fixes are your decision, because both have consequences beyond
this project:**

- **Turn Smart App Control off.** This is ⚠️ **irreversible** — once disabled it
  cannot be re-enabled without reinstalling Windows. It also lowers protection
  for every application on the machine.
- **Develop inside WSL2.** Smart App Control does not apply to Linux binaries,
  so the whole stack installs cleanly and this class of problem disappears for
  good. This is the more robust option if later phases hit the same wall.

**Expect this to recur.** `pytorch` (Phase 6), `whitebox` (Phase 2) and
`weasyprint` (Phase 13) all ship large compiled binaries and are candidates for
the same block.

</details>

`environment.yml` holds the **core** stack (Phases 0–5). Heavier dependencies are
added at the phase that first needs them, so that an install failure in, say, the
PDF stack cannot block early work:

| Added at | Packages |
|---|---|
| Phase 2 | `whitebox` (WhiteboxTools: flow routing, stream network), `scipy` |
| Phase 3 | `scikit-image` — **test-only**, to cross-check this project's own Otsu |
| Phase 4 | none — the fusion uses numpy only |
| Phase 6 | `torch` (CPU-only locally; training on Colab). `segmentation-models-pytorch` and `scikit-learn` are not yet needed |
| Phase 12 | `streamlit`, `streamlit-folium` (folium and plotly arrive with geemap) |
| Phase 13 | `jinja2`; `weasyprint` **cannot run on Windows without GTK**, so PDFs fall back to headless Edge/Chrome — see [`docs/methods.md`](docs/methods.md) §13.2 |

### 2. Configure the environment file

```bash
cp .env.example .env     # Windows: copy .env.example .env
```

Then edit `.env`. `.env` is gitignored and must never be committed.

### 3. Earth Engine access

The Earth Engine Cloud project ID is read from `$GEE_PROJECT` at runtime and is
never stored in the repository.

1. **Register a Cloud project** for Earth Engine (free for research and
   non-commercial use): <https://code.earthengine.google.com/register>
2. **Record the project ID** in `.env`:
   ```
   GEE_PROJECT=your-project-id
   ```
3. **Authenticate once** on this machine. This opens a browser, so run it
   yourself:
   ```bash
   conda activate himalaya
   earthengine authenticate
   ```

Verify access, and confirm that every collection ID and band name in
`config/config.yaml` is still current:

```bash
pytest -m gee -s
```

That test writes the catalog probe — real image counts, band names, observed date
ranges, Sentinel-1 orbit directions, Sentinel-2 tiles and solar angles — to
`outputs/gee_catalog_probe.json`. Nothing in the pipeline assumes a collection ID
is correct; this is where it is checked.

---

## Running the tests

```bash
pytest                  # everything that does not need network access
pytest -m gee -s        # the live Earth Engine gate check
pytest -m "not gee"     # explicitly offline
```

Markers (see `pyproject.toml`):

| Marker | Meaning |
|---|---|
| `gee` | needs an authenticated Earth Engine session; skips with a reason otherwise |
| `network` | needs internet access |
| `slow` | long-running |
| `synthetic` | uses small hand-made arrays/geometries — **never** satellite imagery presented as real |
| `realdata` | asserts against real imagery from a documented location |

---

## Configuration

Everything tunable lives in [`config/config.yaml`](config/config.yaml), validated
against the Pydantic models in [`config/schema.py`](config/schema.py). Unknown
keys are a **hard error**, so a typo in a threshold name fails loudly rather than
being silently ignored.

```python
from config.loader import load_config, config_hash

cfg = load_config()
print(cfg.aoi.name, cfg.aoi.source)
print(config_hash(cfg))      # stored with each run for reproducibility
```

Point at a different config file with `--`/`$HDM_CONFIG`:

```bash
HDM_CONFIG=/path/to/other.yaml pytest
```

### The default AOI

`config.yaml` ships with **Tsho Rolpa** (Rolwaling Valley, Dolakha District,
Nepal) as the default area of interest: a known large water body enclosed by
steep shadow-casting terrain, named in the brief as a water-vs-shadow test case.

It is encoded as a **point plus 4 km buffer** rather than a bounding box, because
both published sources give the position only to arcminute precision; a bounding
box would imply accuracy the sources do not support. Its `source` field carries
the full citation. Nothing in the code paths assumes this site — override `aoi`
per run.

---

## Project layout

See [CLAUDE.md](CLAUDE.md), Section 11, for the full tree and the role of each
module. Two directories are gitignored and regenerable:

- `data/` — `raw/`, `processed/`, `training/`, `validation/`
- `outputs/` — `maps/`, `figures/`, `reports/`, `logs/`

Each run writes a log to `outputs/logs/<run_id>.log`, where `run_id` is
`YYYYmmddTHHMMSSZ-<6 hex>`. That path is recorded in the `runs` table so any
stored result can be traced back to the run that produced it.

---

## Data-integrity rules

These are enforced, not aspirational:

- **No fabricated data.** Synthetic arrays exist only in `tests/` and are marked
  `@pytest.mark.synthetic`. No invented coordinates, dates or measurements.
- **Every coordinate is traceable.** An AOI used as a validation site must carry
  a citation in its `source` field; `tests/test_config.py` asserts this for the
  default AOI.
- **No measurement in degrees.** `utils.crs.ensure_projected` refuses a
  geographic CRS for any area, length or volume calculation. The UTM zone is
  derived from the AOI centroid, never assumed.
- **Depth and volume are branch-traceable.** Every estimate records branch A, B
  or C (brief, Section 8); a value that cannot be traced to a branch is never
  emitted. Where the DEM recorded the water surface, the answer is
  `unavailable`, never a number.
- **Gaps stay gaps.** Cloudy or missing observations are recorded as gaps and
  never silently interpolated.
- **The disclaimer cannot be weakened.** `config/schema.py` refuses to load a
  configuration whose disclaimer drops the phrase *"Not an official warning"*.

---

## Documentation

- [`docs/methods.md`](docs/methods.md) — methods, thresholds and the citation
  register for every scientific choice.
- [`docs/labelling.md`](docs/labelling.md) — segmentation classes and the
  labelling rule (Phase 6).
- [`docs/validation.md`](docs/validation.md) — validation events, results and
  the end-to-end write-up (Phase 13).
