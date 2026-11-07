"""Cloud masking and the co-registered stack.

All arrays are SYNTHETIC. The emphasis is on the two rules the brief makes
non-negotiable: cloud shadow is never merged with terrain shadow, and
categorical layers are never interpolated.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from config.loader import ConfigError, load_config
from config.schema import Config
from preprocessing.cloud_mask import (
    SCL_DARK_AREA,
    build_masks,
    dilate,
    masks_from_cloud_score,
    masks_from_scl,
    terrain_shadow_overlap,
)
from preprocessing.stack import (
    Grid,
    StackedLayers,
    is_categorical,
    read_stack,
    write_stack,
)

pytestmark = pytest.mark.synthetic


def scl_scene() -> np.ndarray:
    """A synthetic SCL raster containing one patch of each relevant class."""
    scene = np.full((40, 40), 5, dtype=np.uint8)  # bare soil
    scene[0:8, 0:8] = 9  # cloud high probability
    scene[0:8, 10:18] = 8  # cloud medium probability
    scene[10:18, 0:8] = 3  # cloud shadow
    scene[20:28, 0:8] = SCL_DARK_AREA  # terrain shadow -- must NOT become cloud
    scene[30:38, 0:8] = 6  # water
    scene[30:38, 20:28] = 11  # snow/ice
    return scene


# --------------------------------------------------------------------------- #
# The rule that matters most
# --------------------------------------------------------------------------- #


def test_dark_area_pixels_are_never_masked_as_cloud(cfg: Config) -> None:
    """SCL 2 is mostly TERRAIN shadow in steep terrain -- the core signal."""
    masks = masks_from_scl(scl_scene(), cfg)
    dark = scl_scene() == SCL_DARK_AREA
    assert not masks.cloud[dark].any()
    assert not masks.cloud_shadow[dark].any()


def test_terrain_shadow_survives_cloud_masking_as_usable(cfg: Config) -> None:
    """A terrain-shadowed pixel is still a real observation of the ground."""
    masks = masks_from_scl(scl_scene(), cfg)
    dark = scl_scene() == SCL_DARK_AREA
    # Dilation of nearby cloud can clip the edges, but the core must survive.
    assert masks.valid[dark].mean() > 0.5


def test_config_refuses_to_call_terrain_shadow_cloud(
    mutable_config, write_config
) -> None:
    """The schema enforces the separation; it is not merely a convention."""
    mutable_config["preprocessing"]["cloud"]["scl_cloud_classes"] = [2, 8, 9, 10]
    with pytest.raises(ConfigError, match="TERRAIN shadow"):
        load_config(write_config(mutable_config), load_env=False)


def test_config_refuses_dark_area_as_cloud_shadow(
    mutable_config, write_config
) -> None:
    mutable_config["preprocessing"]["cloud"]["scl_cloud_shadow_classes"] = [2, 3]
    with pytest.raises(ConfigError, match="TERRAIN shadow"):
        load_config(write_config(mutable_config), load_env=False)


def test_cloud_and_cloud_shadow_stay_separate(cfg: Config) -> None:
    """Brief, Section 7.1: they are reported as distinct components."""
    masks = masks_from_scl(scl_scene(), cfg)
    assert masks.cloud.any()
    assert masks.cloud_shadow.any()
    # The combined view exists, but only on request.
    assert masks.unusable.sum() >= masks.cloud.sum()


# --------------------------------------------------------------------------- #
# Cloud masking mechanics
# --------------------------------------------------------------------------- #


def test_cloud_classes_are_detected(cfg: Config) -> None:
    masks = masks_from_scl(scl_scene(), cfg)
    assert masks.cloud[2, 2]  # class 9
    assert masks.cloud[2, 12]  # class 8


def test_water_and_snow_are_not_cloud(cfg: Config) -> None:
    masks = masks_from_scl(scl_scene(), cfg)
    assert not masks.cloud[34, 4]  # water
    assert not masks.cloud[34, 24]  # snow/ice


def test_dilation_grows_a_mask() -> None:
    mask = np.zeros((20, 20), dtype=bool)
    mask[10, 10] = True
    assert dilate(mask, 0).sum() == 1
    assert dilate(mask, 1).sum() == 9
    assert dilate(mask, 2).sum() == 25


def test_cloud_score_threshold_is_applied(cfg: Config) -> None:
    score = np.linspace(0.0, 1.0, 100).reshape(10, 10)
    masks = masks_from_cloud_score(score, cfg)
    threshold = cfg.preprocessing.cloud.cloud_score_threshold
    # Clear pixels well above the threshold are not cloud.
    assert not masks.cloud[score > threshold + 0.2].any()


def test_build_masks_reports_a_missing_band_rather_than_guessing(
    mutable_config, write_config
) -> None:
    mutable_config["preprocessing"]["cloud"]["method"] = "cloud_score_plus"
    local = load_config(write_config(mutable_config), load_env=False)
    with pytest.raises(ValueError, match="Cloud Score"):
        build_masks(local, scl=scl_scene())


def test_both_method_takes_the_union(cfg: Config) -> None:
    """Conservative: a pixel either method doubts is treated as cloud."""
    assert cfg.preprocessing.cloud.method == "both"
    scl = scl_scene()
    score = np.ones(scl.shape)
    score[35:39, 30:38] = 0.0  # Cloud Score+ alone flags this corner

    masks = build_masks(cfg, scl=scl, cloud_score=score)
    assert masks.cloud[36, 34], "Cloud Score+ detection was lost in the union"
    assert masks.cloud[2, 2], "SCL detection was lost in the union"


def test_valid_fraction_is_a_fraction(cfg: Config) -> None:
    masks = masks_from_scl(scl_scene(), cfg)
    assert 0.0 <= masks.valid_fraction <= 1.0
    assert np.array_equal(masks.valid, ~masks.unusable)


def test_overlap_report_quantifies_the_separation(cfg: Config) -> None:
    """The separation must be demonstrable, not just asserted."""
    scl = scl_scene()
    masks = masks_from_scl(scl, cfg)
    terrain = scl == SCL_DARK_AREA

    report = terrain_shadow_overlap(masks, terrain)
    assert report["terrain_shadow_fraction"] > 0
    assert report["terrain_shadow_not_cloud_shadow"] > 0
    assert report["terrain_shadow_also_usable"] > 0


# --------------------------------------------------------------------------- #
# Stacking
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name", ["SCL", "scl", "cloud_mask", "terrain_shadow", "sar_geometry", "streams", "WBM"]
)
def test_categorical_layers_are_recognised(name: str) -> None:
    assert is_categorical(name)


@pytest.mark.parametrize("name", ["B2", "VV", "ndwi", "elevation", "illumination"])
def test_continuous_layers_are_not_categorical(name: str) -> None:
    assert not is_categorical(name)


def _grid(size: int = 20) -> Grid:
    from affine import Affine

    return Grid(
        crs="EPSG:32645",
        transform=Affine(10.0, 0.0, 400000.0, 0.0, -10.0, 3100000.0),
        width=size,
        height=size,
    )


def test_stack_rejects_a_mismatched_layer() -> None:
    """A silent shape mismatch would misalign every downstream pixel."""
    stack = StackedLayers(grid=_grid())
    with pytest.raises(ValueError, match="shape"):
        stack.add("bad", np.zeros((5, 5)))


def test_stack_rejects_duplicate_names() -> None:
    stack = StackedLayers(grid=_grid())
    stack.add("VV", np.zeros((20, 20)))
    with pytest.raises(ValueError, match="duplicate"):
        stack.add("VV", np.ones((20, 20)))


def test_stack_round_trips_through_disk(tmp_path: Path) -> None:
    grid = _grid()
    stack = StackedLayers(grid=grid)
    stack.add("VV", np.full((20, 20), -12.0))
    stack.add("elevation", np.full((20, 20), 4500.0))
    stack.add("terrain_shadow", np.zeros((20, 20)))

    path = write_stack(stack, tmp_path / "stack.tif")
    restored = read_stack(path)

    assert restored.names == ["VV", "elevation", "terrain_shadow"]
    assert restored.grid.matches(grid)
    assert np.allclose(restored.get("elevation"), 4500.0)


def test_stack_cube_shape() -> None:
    stack = StackedLayers(grid=_grid())
    for name in ("B2", "B3", "B4"):
        stack.add(name, np.zeros((20, 20)))
    assert stack.as_array().shape == (3, 20, 20)


def test_empty_stack_cannot_be_written() -> None:
    with pytest.raises(ValueError, match="empty"):
        StackedLayers(grid=_grid()).as_array()


def test_missing_layer_raises_a_helpful_error() -> None:
    stack = StackedLayers(grid=_grid())
    stack.add("VV", np.zeros((20, 20)))
    with pytest.raises(KeyError, match="VH"):
        stack.get("VH")


def test_grid_matching_detects_a_shifted_transform() -> None:
    from affine import Affine

    a = _grid()
    shifted = Grid(
        crs=a.crs,
        transform=Affine(10.0, 0.0, 400010.0, 0.0, -10.0, 3100000.0),
        width=a.width,
        height=a.height,
    )
    assert not a.matches(shifted)
    assert a.matches(_grid())


# --------------------------------------------------------------------------- #
# Dilation fallback
# --------------------------------------------------------------------------- #
# scipy's compiled extensions are intermittently blocked by Windows Smart App
# Control on this project's machine, so `dilate` has a pure-numpy path. It must
# be exactly equivalent, not an approximation.


@pytest.mark.synthetic
def test_numpy_dilation_matches_scipy() -> None:
    ndimage = pytest.importorskip("scipy.ndimage")
    from preprocessing.cloud_mask import dilate_square

    rng = np.random.default_rng(42)
    mask = rng.random((37, 41)) < 0.04
    for pixels in (1, 2, 3):
        size = 2 * pixels + 1
        expected = ndimage.binary_dilation(
            mask, structure=np.ones((size, size), dtype=bool)
        )
        assert np.array_equal(dilate_square(mask, pixels), expected), pixels


@pytest.mark.synthetic
def test_numpy_dilation_grows_a_single_pixel_into_a_square() -> None:
    from preprocessing.cloud_mask import dilate_square

    mask = np.zeros((7, 7), dtype=bool)
    mask[3, 3] = True
    grown = dilate_square(mask, 2)
    assert grown[1:6, 1:6].all()
    assert grown.sum() == 25


@pytest.mark.synthetic
def test_numpy_dilation_does_not_wrap_at_the_edges() -> None:
    from preprocessing.cloud_mask import dilate_square

    mask = np.zeros((5, 5), dtype=bool)
    mask[0, 0] = True
    grown = dilate_square(mask, 1)
    assert grown[:2, :2].all()
    assert not grown[-1, :].any()
    assert not grown[:, -1].any()


@pytest.mark.synthetic
def test_zero_pixel_dilation_is_a_no_op() -> None:
    from preprocessing.cloud_mask import dilate_square

    mask = np.zeros((4, 4), dtype=bool)
    mask[1, 1] = True
    assert np.array_equal(dilate_square(mask, 0), mask)
