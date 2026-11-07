"""The Landslide4Sense adapter (Phase 6).

The dataset is real, CC BY 4.0 labelled data and the only route to the brief's
required architecture comparison without hand labelling. These tests cover the
three places where using someone else's dataset can quietly corrupt a result:

* a channel the dataset cannot supply must be **refused**, not zero-filled;
* a patch of the wrong size must be **refused**, not resampled;
* the label mapping must come from config and refuse anything unmapped.

The HDF5 files here are synthetic, written in the dataset's documented layout:
``image_N.h5`` holding ``(128, 128, 14)`` and ``mask_N.h5`` holding
``(128, 128)`` with values 0 and 1.
"""

from __future__ import annotations

import numpy as np
import pytest

h5py = pytest.importorskip("h5py")

from config.loader import load_config_with_overlay  # noqa: E402
from config.schema import Config  # noqa: E402
from models.dataset import DatasetError  # noqa: E402
from models.landslide4sense import (  # noqa: E402
    BAND_INDEX,
    CITATION,
    SOURCE_NAME,
    SUPPORTED,
    check_channels,
    convert,
    write_report,
)

pytestmark = pytest.mark.synthetic

OVERLAY = "config/landslide4sense.yaml"


@pytest.fixture
def l4s_cfg() -> Config:
    """The shipped overlay for a Landslide4Sense run."""
    return load_config_with_overlay(OVERLAY, load_env=False)


def write_l4s(root, n_patches: int = 6, size: int = 128, bands: int = 14,
              label_value: int = 1):
    """A synthetic TrainData directory in the dataset's own layout."""
    (root / "img").mkdir(parents=True, exist_ok=True)
    (root / "mask").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    for n in range(1, n_patches + 1):
        image = rng.normal(0.2, 0.05, (size, size, bands)).astype("float32")
        with h5py.File(root / "img" / f"image_{n}.h5", "w") as handle:
            handle.create_dataset("img", data=image)
        mask = np.zeros((size, size), dtype="uint8")
        mask[: size // 4] = label_value
        with h5py.File(root / "mask" / f"mask_{n}.h5", "w") as handle:
            handle.create_dataset("mask", data=mask)
    return root


class TestChannelsAreRefusedNotFilled:
    def test_the_overlay_stack_is_supported(self, l4s_cfg: Config) -> None:
        assert check_channels(l4s_cfg) == list(l4s_cfg.models.channels)

    def test_the_full_project_stack_is_refused(self, cfg: Config) -> None:
        """SAR, illumination and terrain shadow are not in this dataset."""
        with pytest.raises(DatasetError) as excinfo:
            check_channels(cfg)
        message = str(excinfo.value)
        for missing in ("S1_VV", "S1_VH", "ILLUMINATION", "TERRAIN_SHADOW"):
            assert missing in message

    def test_the_refusal_explains_why_not_to_zero_fill(self, cfg: Config) -> None:
        """Zero-filling would teach the model that no-data is a value."""
        with pytest.raises(DatasetError, match="not a measurement"):
            check_channels(cfg)

    def test_sar_is_not_in_the_supported_set(self) -> None:
        assert "S1_VV" not in SUPPORTED
        assert "TERRAIN_SHADOW" not in SUPPORTED

    def test_indices_are_derivable(self) -> None:
        for name in ("NDWI", "MNDWI", "NDVI"):
            assert name in SUPPORTED
            assert name not in BAND_INDEX  # derived, not a band


class TestConversion:
    def test_patches_are_written_with_our_channels(
        self, l4s_cfg: Config, tmp_path
    ) -> None:
        write_l4s(tmp_path / "TrainData")
        report = convert(l4s_cfg, tmp_path / "TrainData", tmp_path / "out")
        assert report.written == 6
        assert report.channels == list(l4s_cfg.models.channels)

        from models.dataset import PatchDataset, discover_patches

        refs = discover_patches(tmp_path / "out")
        x, y = PatchDataset(refs, l4s_cfg)[0]
        assert x.shape == (l4s_cfg.models.in_channels, 128, 128)
        assert y.shape == (128, 128)

    def test_the_label_mapping_comes_from_config(
        self, l4s_cfg: Config, tmp_path
    ) -> None:
        """Their 1 is our 2, because our class 1 is water."""
        write_l4s(tmp_path / "TrainData", n_patches=2)
        report = convert(l4s_cfg, tmp_path / "TrainData", tmp_path / "out")
        assert report.class_pixels["landslide"] > 0
        assert report.class_pixels["water"] == 0

    def test_an_unmapped_source_label_is_refused(
        self, l4s_cfg: Config, tmp_path
    ) -> None:
        """A value nobody decided about must not become background."""
        write_l4s(tmp_path / "TrainData", n_patches=1, label_value=7)
        with pytest.raises(DatasetError, match="no entry in label_map"):
            convert(l4s_cfg, tmp_path / "TrainData", tmp_path / "out")

    def test_a_wrong_patch_size_is_refused_not_resampled(
        self, l4s_cfg: Config, tmp_path
    ) -> None:
        """Interpolating a label raster invents boundaries never drawn."""
        write_l4s(tmp_path / "TrainData", n_patches=1, size=64)
        with pytest.raises(DatasetError) as excinfo:
            convert(l4s_cfg, tmp_path / "TrainData", tmp_path / "out")
        assert "invents boundaries" in str(excinfo.value)

    def test_a_missing_directory_points_at_zenodo(
        self, l4s_cfg: Config, tmp_path
    ) -> None:
        with pytest.raises(DatasetError, match="zenodo"):
            convert(l4s_cfg, tmp_path / "nope", tmp_path / "out")

    def test_patches_carry_an_event_so_the_split_can_work(
        self, l4s_cfg: Config, tmp_path
    ) -> None:
        """No coordinates exist, so only an event split is honest here."""
        write_l4s(tmp_path / "TrainData", n_patches=6)
        convert(l4s_cfg, tmp_path / "TrainData", tmp_path / "out")

        from models.dataset import assign_splits, discover_patches

        refs = discover_patches(tmp_path / "out")
        assert all(r.event for r in refs)
        assert l4s_cfg.models.split.strategy == "event"
        splits = assign_splits(refs, l4s_cfg)
        assert all(splits[name] for name in ("train", "val", "test"))

    def test_no_patch_appears_in_two_partitions(
        self, l4s_cfg: Config, tmp_path
    ) -> None:
        write_l4s(tmp_path / "TrainData", n_patches=9)
        convert(l4s_cfg, tmp_path / "TrainData", tmp_path / "out")

        from models.dataset import assign_splits, discover_patches

        splits = assign_splits(discover_patches(tmp_path / "out"), l4s_cfg)
        paths = [r.path for v in splits.values() for r in v]
        assert len(paths) == len(set(paths))


class TestTheReportStatesItsLimits:
    def test_the_report_names_the_classes_it_cannot_supply(
        self, l4s_cfg: Config, tmp_path
    ) -> None:
        """The brief's primary result is unobtainable from this source."""
        write_l4s(tmp_path / "TrainData", n_patches=2)
        report = convert(l4s_cfg, tmp_path / "TrainData", tmp_path / "out")
        data = report.as_dict()
        assert set(data["classes_absent"]) == {
            "water", "terrain_shadow", "snow_ice"
        }
        assert "water-vs-shadow" in data["note"]

    def test_the_report_carries_the_licence_and_citation(
        self, l4s_cfg: Config, tmp_path
    ) -> None:
        """CC BY 4.0 requires attribution wherever a result is reported."""
        write_l4s(tmp_path / "TrainData", n_patches=1)
        report = convert(l4s_cfg, tmp_path / "TrainData", tmp_path / "out")
        data = report.as_dict()
        assert "CC BY 4.0" in data["licence"]
        assert "Ghorbanzadeh" in data["citation"]
        assert "zenodo" in data["licence"].lower()

    def test_the_report_is_written_to_disk(
        self, l4s_cfg: Config, tmp_path
    ) -> None:
        import json

        write_l4s(tmp_path / "TrainData", n_patches=1)
        report = convert(l4s_cfg, tmp_path / "TrainData", tmp_path / "out")
        path = write_report(report, tmp_path / "conversion.json")
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["source"] == SOURCE_NAME
        assert saved["cannot_supply"]


def test_the_citation_names_the_zenodo_doi() -> None:
    assert "10.5281/zenodo.10463239" in CITATION
    assert "CC BY 4.0" in CITATION
