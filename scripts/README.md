# Analysis scripts

The runs behind the verification records in `docs/validation.md`.

Before these were committed, every Baige claim in sections 20-27 cited an
artifact in `outputs/` that no code in the repository could reproduce --
the scripts lived in a throwaway session directory. That is fixed.

**This is a selected set, not an archive.** Runs whose results were later
superseded are deliberately absent: keeping them would imply their numbers
still stand. What remains reproduces the *current* claims.

Every script derives its paths from its own location, so run them from
anywhere:

```
python scripts/baige/03_rederive_chain.py
```

## Order

`01` and `02` need Earth Engine credentials and write to `data/`. The rest
read what they produced, so the chain can be re-run offline once the data
is on disk.

| script | what it does | supports |
|---|---|---|
| `baige/01_fetch.py` | Acquire Sentinel-2, Sentinel-1 and the DEM for the Baige AOI from GEE | validation.md 20 (Event and data) |
| `baige/02_streams.py` | Derive the stream network, flow direction and accumulation from the Baige DEM, and check the channel against observed water | validation.md 21 (Inputs) |
| `baige/03_rederive_chain.py` | THE AUTHORITATIVE RUN | validation.md 25 and 26 |
| `baige/04_depth.py` | Phase 10 branch logic on the real lake, and why its numbers are withheld | validation.md 24 |
| `baige/05_persist_and_report.py` | Store the results with their value_types and generate the site PDF | validation.md 19 (B) |
| `baige/06_mainstem_robustness.py` | Vary the candidate-grouping settings and ask whether the same dam is identified each time | validation.md 26 |
| `baige/07_fusion_level_test.py` | The level-surface test: a lake is level, so no real water pixel sits far above the waterline | validation.md 24 (Finding 4) |
| `baige/08_fusion_diagnosis.py` | Why the fusion adds pixels over optical nodata: what each evidence term actually saw | validation.md 24 (Finding 4a) |
| `baige/09_coordinate_check.py` | Where the published Baige coordinate actually is: 52.9 deg slope, 471 m above the river | validation.md 20 (C.0) |
| `baige/10_which_candidate.py` | Which blockage candidate holds the impounded water, tested against gained-water elevation rather than flow accumulation alone | validation.md 22 |
| `baige/11_build_patches.py` | Assemble the 15-channel stack from real imagery and cut demonstration patches | validation.md 27 |
| `checks/phase4_illumination.py` | Re-verify Phase 4's gate after the cos_incidence BLAS bug: is the stored illumination what the fixed code produces? | validation.md 24 (Finding 5a) |
| `checks/labelling_footprint.py` | How many separated areas must be labelled for a valid geographic split | validation.md 27, labelling.md |

## The one that matters

`baige/03_rederive_chain.py` is the authoritative run. It fuses water per
date with the scene's own sun angles, screens snow as an invalid
observation, wires the four-date persistence term, and keeps results only
where optical data exists -- then re-derives Phases 5, 7, 8, 9 and 11 on
it. Sections 25 and 26 are its output. Earlier figures in sections 20-23
came from unfused water and are superseded.

## What was left out, and why

- **patch_*** — one-off documentation edits; their content is now in the documents
- **baige_phase5/7/8/9/11, baige_phase8_final, baige_phase8_track, baige_fused_chain** — superseded by 03_rederive_chain.py; keeping them would imply their numbers still stand
- **baige_verify, baige_water_check, baige_direction, baige_lake_overlap, baige_track_diag, baige_phase7_verify, baige_mainstem_question** — diagnostics whose findings are recorded in the documents and whose inputs are superseded
- **fetch_alt, fetch_late** — scene-search attempts, no longer needed
- **make_colab_nb*, add_models_config, install_scripts, check_nb** — code generators; their output is committed

---

Research prototype output. Not an official warning. Verify with
authoritative sources.
