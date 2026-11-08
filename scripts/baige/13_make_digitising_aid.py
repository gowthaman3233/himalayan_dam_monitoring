"""Build georeferenced layers to digitise against in QGIS.

Supports: validation.md 31, and the accuracy figures that follow

Half the Baige deposit was already present on the "pre-event" date, because
the river was dammed twice (validation.md 31). So the landslide layer must
outline only what is NEW on 2018-11-09, which means comparing two dates by
eye -- fiddly with raster layers and a visibility checkbox.

This writes three GeoTIFFs to make that comparison easy:

    baige_aid_pre.tif          false colour, 2018-11-02
    baige_aid_post.tif         false colour, 2018-11-09, same stretch
    baige_aid_difference.tif   post minus pre

**These are RAW BAND ARITHMETIC, not detector output.** Nothing here applies
a threshold, a model or any of this project's detection logic. The difference
layer shows exactly what toggling the two scenes would show, in one image --
so tracing it is no more circular than tracing the imagery itself. A layer
derived from the detectors would be, and is deliberately not produced.

All three carry the scene's CRS and transform, so QGIS places them on the
ground and anything digitised over them lands in the right place.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

RAW = ROOT / "data" / "raw" / "baige_2018"
OUT = ROOT / "data" / "validation"
BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]

#: False colour: water near-black, fresh bare debris bright, vegetation green.
#: The combination a digitiser would choose, stated so the choice is explicit.
DISPLAY = ("B11", "B8", "B4")

SCENES = {
    "pre": ("S2_47RMQ_20181102T041940_refl.tif", "2018-11-02, after the first dam"),
    "post": ("S2_47RMQ_20181109T040948_refl.tif", "2018-11-09, after the second"),
}


def read(stem: str):
    with rasterio.open(RAW / stem) as src:
        bands = {n: src.read(i + 1).astype("float32")
                 for i, n in enumerate(BANDS)}
        return bands, src.profile


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    loaded = {key: read(stem) for key, (stem, _) in SCENES.items()}

    # One stretch across BOTH dates, so a difference in the display is a
    # difference on the ground and not a difference in contrast.
    limits = {}
    for band in DISPLAY:
        values = np.concatenate([
            bands[band][np.isfinite(bands[band]) & (bands[band] > 0)].ravel()
            for bands, _ in loaded.values()
        ])
        limits[band] = (
            float(np.percentile(values, 2)), float(np.percentile(values, 98))
        )
        print(f"{band}: shared stretch {limits[band][0]:.0f}-{limits[band][1]:.0f}")

    def to_rgb(bands) -> np.ndarray:
        out = []
        for band in DISPLAY:
            low, high = limits[band]
            scaled = np.clip((bands[band] - low) / max(high - low, 1e-9), 0, 1)
            out.append((scaled * 255).astype("uint8"))
        return np.stack(out, axis=0)

    rgbs = {}
    for key, (bands, profile) in loaded.items():
        rgb = to_rgb(bands)
        rgbs[key] = rgb
        path = OUT / f"baige_aid_{key}.tif"
        out_profile = {
            **profile, "count": 3, "dtype": "uint8", "nodata": None,
            "compress": "lzw", "photometric": "RGB",
        }
        with rasterio.open(path, "w", **out_profile) as dst:
            dst.write(rgb)
            for i, band in enumerate(DISPLAY, start=1):
                dst.set_band_description(i, band)
            dst.update_tags(
                scene=SCENES[key][0], note=SCENES[key][1],
                rendering=f"false colour R={DISPLAY[0]} G={DISPLAY[1]} B={DISPLAY[2]}",
                value_type="observed",
            )
        print(f"wrote {path.name}  ({SCENES[key][1]})")

    # post - pre, with two corrections. Without them the layer is worse than
    # useless: it looks like change everywhere and would lead a digitiser to
    # trace artefacts.
    #
    # 1. NODATA. One date has no data over roughly 40% of this scene (the
    #    Sentinel-2 edge), and "data minus nodata" is not a difference. Those
    #    pixels are forced to neutral grey rather than left to dominate.
    # 2. A GLOBAL SHIFT. The two dates differ in sun angle and atmosphere, so
    #    the whole scene moves together. Subtracting the median difference
    #    per channel removes that common offset and leaves LOCAL change, which
    #    is the only part that means anything on the ground.
    raw = rgbs["post"].astype("int16") - rgbs["pre"].astype("int16")

    observed = np.ones(raw.shape[1:], dtype=bool)
    for bands, _ in loaded.values():
        present = np.zeros(raw.shape[1:], dtype=bool)
        for band in BANDS:
            present |= np.isfinite(bands[band]) & (bands[band] > 0)
        observed &= present
    print(f"observed on BOTH dates: {100 * observed.mean():.1f}% of the scene")

    shifts = []
    for i in range(raw.shape[0]):
        shift = float(np.median(raw[i][observed])) if observed.any() else 0.0
        shifts.append(shift)
        raw[i] = raw[i] - int(round(shift))
    print(f"removed a global shift of {[round(s, 1) for s in shifts]} "
          f"(sun angle and atmosphere, not ground change)")

    difference = np.clip(raw + 128, 0, 255).astype("uint8")
    difference[:, ~observed] = 128  # neutral where either date is blind
    path = OUT / "baige_aid_difference.tif"
    _, profile = loaded["post"]
    out_profile = {
        **profile, "count": 3, "dtype": "uint8", "nodata": None,
        "compress": "lzw", "photometric": "RGB",
    }
    with rasterio.open(path, "w", **out_profile) as dst:
        dst.write(difference)
        for i, band in enumerate(DISPLAY, start=1):
            dst.set_band_description(i, f"{band} post-minus-pre")
        dst.update_tags(
            note=("post minus pre, centred on 128. Mid-grey is unchanged. "
                  "Bright = brighter after, i.e. new bare material. Dark = "
                  "darker after, i.e. new water."),
            value_type="derived",
        )
    print(f"wrote {path.name}")

    strong = np.abs(difference.astype("int16") - 128).max(axis=0) > 40
    changed = int(np.count_nonzero(strong & observed))
    total = int(np.count_nonzero(observed))
    print(f"\n{100 * changed / max(total, 1):.1f}% of the OBSERVED scene "
          f"changed strongly between the two dates")
    print(f"""
In QGIS, load all three from {OUT}

  baige_aid_difference.tif   on top. MID-GREY means unchanged AND ALSO means
                             "one date could not see here", so grey is never
                             evidence of anything.
                             WHITE/PINK    = brighter after: new bare material
                             ORANGE        = the downstream channel that drained
                             OLIVE/NAVY    = the impounded lake and its newly
                                             flooded margin
                             CYAN, bottom-left = most likely cloud or snow,
                                             NOT ground change. Do not trace.
                             A residual magenta cast over most of the ground is
                             illumination difference the median shift does not
                             fully remove. Only LOCAL contrast is meaningful.

  This layer is a guide for the LANDSLIDE layer only. Trace the LAKE on
  baige_aid_post.tif, where water is near-black, not on the difference.
  baige_aid_post.tif         beneath it, for context
  baige_aid_pre.tif          beneath that, to toggle against

Digitise the LANDSLIDE layer over the bright areas of the difference, and
the LAKE layer over the dark water on baige_aid_post.tif. See
docs/validation.md 31 for why the landslide layer must be new material only.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
