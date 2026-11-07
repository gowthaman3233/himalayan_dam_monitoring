"""Phase 6 dataset building: label mapping and leak-free splits.

The split tests are the ones that matter. The brief forbids random pixel or
random patch splits that leak spatially adjacent data, because two 256-pixel
patches 128 pixels apart share half their ground -- scored across a random
split, a model is partly tested on its own training data and every metric in
Section 7.5 comes out optimistic. A leak is invisible in the output: the run
completes, the numbers look good, and they are wrong.

All arrays here are synthetic.
"""

from __future__ import annotations

import numpy as np
import pytest

from config.schema import Config
from models.dataset import (
    SPLITS,
    DatasetError,
    PatchDataset,
    PatchRef,
    assign_splits,
    discover_patches,
    keep_patch,
    labelled_fraction,
    map_labels,
    read_patch_meta,
    split_summary,
    write_patch,
)

pytestmark = pytest.mark.synthetic

IGNORE = 255


def replace_models_config(cfg: Config, **overrides) -> Config:
    data = cfg.model_dump(mode="python")
    section = data["models"]
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(section.get(key), dict):
            section[key].update(value)
        else:
            section[key] = value
    return Config.model_validate(data)


def make_patch(path, cfg: Config, *, x_m: float, y_m: float, event=None, label=0):
    size = cfg.models.patch.size_px
    x = np.zeros((cfg.models.in_channels, size, size), dtype=np.float32)
    y = np.full((size, size), label, dtype=np.uint8)
    return write_patch(
        path, x, y, cfg.models.channels, x_m=x_m, y_m=y_m,
        crs="EPSG:32645", event=event,
    )


# --------------------------------------------------------------------------- #
# Label mapping
# --------------------------------------------------------------------------- #
class TestLabelMapping:
    def test_sen1floods11_values_map_as_documented(self, cfg: Config) -> None:
        """-1 No Data, 0 Not Water, 1 Water, per the official repository."""
        source = np.array([[-1, 0, 1], [1, 0, -1]])
        mapping = cfg.models.sources["sen1floods11"].label_map
        out = map_labels(source, mapping, ignore_index=IGNORE,
                         source_name="sen1floods11")
        assert out[0, 0] == IGNORE, "No Data must become ignore, not background"
        assert out[0, 1] == 0
        assert out[0, 2] == 1

    def test_landslide4sense_maps_to_our_landslide_class(self, cfg: Config) -> None:
        source = np.array([[0, 1]])
        mapping = cfg.models.sources["landslide4sense"].label_map
        out = map_labels(source, mapping, ignore_index=IGNORE,
                         source_name="landslide4sense")
        assert out[0, 0] == 0
        assert out[0, 1] == 2, "landslide must map to class 2, not class 1"

    def test_an_unmapped_label_is_refused(self) -> None:
        """The central rule: an undocumented class must not become background.

        Defaulting it would turn unknown ground into training signal for
        "land", which is worse than failing, because nothing downstream could
        detect it.
        """
        with pytest.raises(DatasetError, match="no entry in label_map"):
            map_labels(np.array([[0, 1, 9]]), {"0": 0, "1": 1},
                       ignore_index=IGNORE, source_name="sen1floods11")

    def test_the_error_names_the_offending_values(self) -> None:
        with pytest.raises(DatasetError, match=r"\[4, 9\]"):
            map_labels(np.array([[0, 4, 9]]), {"0": 0},
                       ignore_index=IGNORE, source_name="src")

    def test_none_maps_to_ignore_not_to_zero(self) -> None:
        out = map_labels(np.array([[5]]), {"5": None}, ignore_index=IGNORE)
        assert out[0, 0] == IGNORE


# --------------------------------------------------------------------------- #
# Splits -- no spatial leakage
# --------------------------------------------------------------------------- #
class TestGeographicSplitDoesNotLeak:
    def _grid(self, tmp_path, cfg: Config, *, step_m=4000.0, extent_m=40000.0):
        refs = []
        n = int(extent_m // step_m)
        for i in range(n):
            for j in range(n):
                x, y = i * step_m, j * step_m
                refs.append(
                    PatchRef(
                        path=make_patch(tmp_path / f"p_{i}_{j}.npz", cfg,
                                        x_m=x, y_m=y),
                        x_m=x, y_m=y,
                    )
                )
        return refs

    def test_no_block_appears_in_two_partitions(self, cfg: Config, tmp_path) -> None:
        """The property that makes the test set a test set."""
        refs = self._grid(tmp_path, cfg)
        splits = assign_splits(refs, cfg)
        block_m = cfg.models.split.block_km * 1000.0
        blocks = {
            name: {r.block(block_m) for r in refs_} for name, refs_ in splits.items()
        }
        assert not (blocks["train"] & blocks["val"])
        assert not (blocks["train"] & blocks["test"])
        assert not (blocks["val"] & blocks["test"])

    def test_no_patch_is_in_two_partitions(self, cfg: Config, tmp_path) -> None:
        refs = self._grid(tmp_path, cfg)
        splits = assign_splits(refs, cfg)
        paths = [r.path for refs_ in splits.values() for r in refs_]
        assert len(paths) == len(set(paths))

    def test_patches_near_a_block_boundary_are_dropped(
        self, cfg: Config, tmp_path
    ) -> None:
        """Adjacency is the leak the buffer exists to stop."""
        refs = self._grid(tmp_path, cfg)
        splits = assign_splits(refs, cfg)
        kept = sum(len(v) for v in splits.values())
        assert kept < len(refs), "the buffer retained every patch"

        buffer_m = cfg.models.split.buffer_px * cfg.models.patch.scale_m
        block_m = cfg.models.split.block_km * 1000.0
        for refs_ in splits.values():
            for r in refs_:
                near_x = min(r.x_m % block_m, block_m - (r.x_m % block_m))
                near_y = min(r.y_m % block_m, block_m - (r.y_m % block_m))
                assert min(near_x, near_y) >= buffer_m

    def test_a_zero_buffer_keeps_every_patch(self, cfg: Config, tmp_path) -> None:
        """Proof the loss above is the buffer and not something else."""
        no_buffer = replace_models_config(cfg, split={"buffer_px": 0})
        refs = self._grid(tmp_path, no_buffer)
        splits = assign_splits(refs, no_buffer)
        assert sum(len(v) for v in splits.values()) == len(refs)

    def test_the_split_is_reproducible(self, cfg: Config, tmp_path) -> None:
        refs = self._grid(tmp_path, cfg)
        first = assign_splits(refs, cfg)
        second = assign_splits(refs, cfg)
        for name in SPLITS:
            assert [r.path for r in first[name]] == [r.path for r in second[name]]

    def test_a_different_seed_gives_a_different_split(
        self, cfg: Config, tmp_path
    ) -> None:
        refs = self._grid(tmp_path, cfg)
        a = assign_splits(refs, cfg)
        b = assign_splits(refs, replace_models_config(cfg, split={"seed": 99}))
        assert [r.path for r in a["test"]] != [r.path for r in b["test"]]

    def test_a_test_set_always_survives_when_there_is_more_than_one_block(
        self, cfg: Config, tmp_path
    ) -> None:
        """An empty test set would make every reported metric vacuous."""
        refs = self._grid(tmp_path, cfg, step_m=12000.0, extent_m=60000.0)
        splits = assign_splits(refs, replace_models_config(cfg, split={"buffer_px": 0}))
        assert splits["test"], "no test partition was produced"


class TestEventSplit:
    def test_an_event_goes_entirely_to_one_partition(
        self, cfg: Config, tmp_path
    ) -> None:
        by_event = replace_models_config(cfg, split={"strategy": "event"})
        refs = []
        for e in range(6):
            for k in range(3):
                refs.append(
                    PatchRef(
                        path=make_patch(tmp_path / f"e{e}_{k}.npz", by_event,
                                        x_m=float(k * 300), y_m=0.0,
                                        event=f"event-{e}"),
                        x_m=float(k * 300), y_m=0.0, event=f"event-{e}",
                    )
                )
        splits = assign_splits(refs, by_event)
        seen: dict[str, str] = {}
        for name, refs_ in splits.items():
            for r in refs_:
                assert seen.setdefault(r.event, name) == name, (
                    f"{r.event} was split across partitions"
                )

    def test_event_strategy_refuses_patches_without_an_event(
        self, cfg: Config, tmp_path
    ) -> None:
        by_event = replace_models_config(cfg, split={"strategy": "event"})
        refs = [
            PatchRef(path=make_patch(tmp_path / "a.npz", by_event, x_m=0.0, y_m=0.0),
                     x_m=0.0, y_m=0.0, event=None)
        ]
        with pytest.raises(DatasetError, match="no event label"):
            assign_splits(refs, by_event)

    def test_random_is_not_an_available_strategy(self, cfg: Config) -> None:
        """The brief forbids it, so it is not selectable at all."""
        with pytest.raises(Exception):
            replace_models_config(cfg, split={"strategy": "random"})


# --------------------------------------------------------------------------- #
# Patch IO and the channel contract
# --------------------------------------------------------------------------- #
class TestPatchIO:
    def test_a_patch_describes_its_own_channels(self, cfg: Config, tmp_path) -> None:
        path = make_patch(tmp_path / "p.npz", cfg, x_m=1.0, y_m=2.0)
        with np.load(path, allow_pickle=True) as data:
            assert [str(c) for c in data["channels"]] == list(cfg.models.channels)

    def test_meta_round_trips(self, cfg: Config, tmp_path) -> None:
        make_patch(tmp_path / "p.npz", cfg, x_m=450000.0, y_m=3085000.0,
                   event="jure-2014")
        meta = read_patch_meta(tmp_path / "p.npz")
        assert meta["x_m"] == 450000.0
        assert meta["event"] == "jure-2014"

    def test_a_channel_count_mismatch_is_refused_on_write(
        self, cfg: Config, tmp_path
    ) -> None:
        size = cfg.models.patch.size_px
        with pytest.raises(DatasetError, match="channel"):
            write_patch(
                tmp_path / "bad.npz",
                np.zeros((3, size, size), np.float32),
                np.zeros((size, size), np.uint8),
                cfg.models.channels,
                x_m=0.0, y_m=0.0,
            )

    def test_a_stale_stack_fails_by_name_not_by_shape(
        self, cfg: Config, tmp_path
    ) -> None:
        """A renamed stack must not silently feed the wrong band per slot."""
        size = cfg.models.patch.size_px
        stale = list(cfg.models.channels)
        stale[0] = "SOMETHING_ELSE"
        write_patch(
            tmp_path / "stale.npz",
            np.zeros((len(stale), size, size), np.float32),
            np.zeros((size, size), np.uint8),
            stale, x_m=0.0, y_m=0.0,
        )
        refs = discover_patches(tmp_path)
        dataset = PatchDataset(refs, cfg)
        with pytest.raises(DatasetError, match="models.channels"):
            _ = dataset[0]

    def test_discover_refuses_an_empty_directory(self, cfg: Config, tmp_path) -> None:
        empty = tmp_path / "none"
        empty.mkdir()
        with pytest.raises(DatasetError, match="no .npz patches"):
            discover_patches(empty)

    def test_class_pixel_counts_report_every_class_and_the_ignored(
        self, cfg: Config, tmp_path
    ) -> None:
        """Per-class IoU cannot be read without knowing the support."""
        size = cfg.models.patch.size_px
        y = np.zeros((size, size), np.uint8)
        y[:10] = 3
        y[10:20] = IGNORE
        write_patch(
            tmp_path / "p.npz",
            np.zeros((cfg.models.in_channels, size, size), np.float32),
            y, cfg.models.channels, x_m=0.0, y_m=0.0,
        )
        counts = PatchDataset(discover_patches(tmp_path), cfg).class_pixel_counts()
        assert set(counts) == {*cfg.models.classes, "ignored"}
        assert counts["terrain_shadow"] == 10 * size
        assert counts["ignored"] == 10 * size
        assert counts["snow_ice"] == 0


class TestLabelledFraction:
    def test_an_all_ignored_patch_is_dropped(self, cfg: Config) -> None:
        y = np.full((16, 16), IGNORE, dtype=np.uint8)
        assert labelled_fraction(y, IGNORE) == 0.0
        assert not keep_patch(y, cfg)

    def test_a_fully_labelled_patch_is_kept(self, cfg: Config) -> None:
        y = np.zeros((16, 16), dtype=np.uint8)
        assert labelled_fraction(y, IGNORE) == 1.0
        assert keep_patch(y, cfg)

    def test_the_threshold_is_read_from_config(self, cfg: Config) -> None:
        y = np.full((10, 10), IGNORE, dtype=np.uint8)
        y[:2] = 0  # 20% labelled
        assert keep_patch(y, replace_models_config(
            cfg, patch={"min_labelled_fraction": 0.1}))
        assert not keep_patch(y, replace_models_config(
            cfg, patch={"min_labelled_fraction": 0.5}))


def test_split_summary_counts_each_partition(cfg: Config, tmp_path) -> None:
    refs = [
        PatchRef(path=make_patch(tmp_path / "a.npz", cfg, x_m=0.0, y_m=0.0,
                                 event="e1"),
                 x_m=0.0, y_m=0.0, event="e1")
    ]
    summary = split_summary({"train": refs, "val": [], "test": []})
    assert summary["train"]["patches"] == 1
    assert summary["train"]["events"] == ["e1"]
    assert summary["val"]["events"] is None


class TestTheBufferIsAppliedBeforeAssignment:
    """Order matters: buffer first, then partition what survives.

    Assigning blocks to partitions *before* dropping buffered patches makes
    the non-empty guarantee meaningless -- a block can be given to "test" and
    then lose every one of its patches to the buffer, leaving an empty
    partition while the assignment believed otherwise. Found when a
    three-site simulation produced train 6, val 0, test 0 despite there being
    three blocks to share out.
    """

    def _sites(self, tmp_path, cfg: Config, n_sites: int, per_site: int = 9):
        """Patches clustered at well-separated sites, inside block interiors."""
        block_m = cfg.models.split.block_km * 1000.0
        span = cfg.models.patch.size_px * cfg.models.patch.scale_m
        refs = []
        for site in range(n_sites):
            base = site * block_m
            for k in range(per_site):
                x = base + block_m / 2.0 + ((k % 3) - 1) * span * 0.5
                y = block_m / 2.0 + ((k // 3) - 1) * span * 0.5
                refs.append(
                    PatchRef(
                        path=make_patch(tmp_path / f"s{site}_{k}.npz", cfg,
                                        x_m=x, y_m=y),
                        x_m=x, y_m=y,
                    )
                )
        return refs

    def test_three_separated_sites_fill_every_partition(
        self, cfg: Config, tmp_path
    ) -> None:
        splits = assign_splits(self._sites(tmp_path, cfg, 3), cfg)
        for name in SPLITS:
            assert splits[name], f"{name} is empty with three separated sites"

    def test_more_sites_never_empty_a_partition(
        self, cfg: Config, tmp_path
    ) -> None:
        """The erratic behaviour the bug produced: adding sites broke it."""
        for n in (3, 4, 6):
            splits = assign_splits(self._sites(tmp_path, cfg, n), cfg)
            assert all(splits[name] for name in SPLITS), (
                f"{n} sites left a partition empty"
            )

    def test_one_site_cannot_be_split(self, cfg: Config, tmp_path) -> None:
        """Honest failure: one area of ground has nothing to partition."""
        splits = assign_splits(self._sites(tmp_path, cfg, 1), cfg)
        assert not splits["val"] and not splits["test"]

    def test_buffered_patches_never_reach_a_partition(
        self, cfg: Config, tmp_path
    ) -> None:
        """A patch on a boundary belongs to no partition at all."""
        block_m = cfg.models.split.block_km * 1000.0
        refs = [
            PatchRef(path=make_patch(tmp_path / "edge.npz", cfg,
                                     x_m=block_m, y_m=block_m),
                     x_m=block_m, y_m=block_m),
        ]
        refs += self._sites(tmp_path, cfg, 3)
        splits = assign_splits(refs, cfg)
        kept = {r.path.name for v in splits.values() for r in v}
        assert "edge.npz" not in kept
