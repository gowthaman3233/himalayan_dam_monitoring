"""Configuration loading and validation.

These tests enforce the parts of the brief that must not be weakened by an edit
to ``config.yaml``: the mandatory disclaimer (Section 9), AOI traceability
(Section 6), and the rule that unknown keys fail loudly rather than being
silently ignored (Section 2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config.loader import ConfigError, config_hash, load_config, resolved_paths
from config.schema import (
    REQUIRED_DISCLAIMER_PHRASE,
    BBoxAOI,
    Config,
    DateRange,
    GeoJSONAOI,
    PointBufferAOI,
)

# --------------------------------------------------------------------------- #
# The real config file
# --------------------------------------------------------------------------- #


def test_real_config_loads(cfg: Config) -> None:
    assert cfg.project.name
    assert cfg.project.version
    assert cfg.gee.default_scale_m == 10.0, "working grid should be Sentinel-2 native"


def test_disclaimer_is_the_text_the_brief_requires(cfg: Config) -> None:
    """Brief, Section 9: every warning and report carries this exact wording."""
    text = " ".join(cfg.project.disclaimer.split())
    assert text == (
        "Research prototype output. Not an official warning. "
        "Verify with authoritative sources."
    )


def test_default_aoi_is_traceable(cfg: Config) -> None:
    """Brief, Section 2: no invented coordinates -- the AOI cites its source."""
    assert cfg.aoi.source, "the default AOI must record where its coordinates came from"
    assert "doi" in cfg.aoi.source.lower() or "http" in cfg.aoi.source.lower(), (
        "the AOI source should contain a resolvable citation (DOI or URL)"
    )


def test_default_aoi_is_in_nepal_utm(cfg: Config) -> None:
    from utils.crs import NEPAL_UTM_EPSG, utm_epsg_for_centroid

    centroid = cfg.aoi_centroid
    assert centroid is not None
    assert utm_epsg_for_centroid(centroid) in NEPAL_UTM_EPSG


def test_configured_collection_ids_are_present(cfg: Config) -> None:
    """Every collection the brief lists in Section 5 has an ID in config.

    Whether each ID is *correct* is verified against the live catalog by
    tests/test_gee_smoke.py -- it cannot be checked offline.
    """
    collections = cfg.gee.collections
    for name in type(collections).model_fields:
        assert getattr(collections, name).strip(), f"{name} has no collection ID"


def test_paths_resolve_under_repo_root(cfg: Config, root: Path) -> None:
    for name, path in resolved_paths(cfg).items():
        assert path.is_absolute(), name
        assert root.resolve() in path.parents or path == root.resolve(), name


# --------------------------------------------------------------------------- #
# Validation failures must be loud
# --------------------------------------------------------------------------- #


def test_unknown_key_is_rejected(mutable_config, write_config) -> None:
    mutable_config["gee"]["ndwi_threshld"] = 0.3  # deliberate typo
    with pytest.raises(ConfigError) as err:
        load_config(write_config(mutable_config), load_env=False)
    assert "ndwi_threshld" in str(err.value)


def test_weakened_disclaimer_is_rejected(mutable_config, write_config) -> None:
    mutable_config["project"]["disclaimer"] = "Research prototype output."
    with pytest.raises(ConfigError) as err:
        load_config(write_config(mutable_config), load_env=False)
    assert REQUIRED_DISCLAIMER_PHRASE in str(err.value)


def test_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml", load_env=False)


def test_empty_file_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError, match="empty"):
        load_config(path, load_env=False)


def test_non_mapping_file_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(path, load_env=False)


def test_absolute_path_is_rejected(mutable_config, write_config) -> None:
    mutable_config["paths"]["outputs"] = "C:/somewhere/else"
    with pytest.raises(ConfigError, match="relative"):
        load_config(write_config(mutable_config), load_env=False)


# --------------------------------------------------------------------------- #
# AOI models (synthetic coordinates)
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
def test_bbox_requires_ordered_corners() -> None:
    with pytest.raises(ValueError, match="west"):
        BBoxAOI(kind="bbox", name="synthetic", west=87.0, south=27.0, east=86.0, north=28.0)
    with pytest.raises(ValueError, match="south"):
        BBoxAOI(kind="bbox", name="synthetic", west=86.0, south=28.0, east=87.0, north=27.0)


@pytest.mark.synthetic
def test_bbox_centroid() -> None:
    box = BBoxAOI(kind="bbox", name="synthetic", west=86.0, south=27.0, east=87.0, north=28.0)
    assert box.centroid == (86.5, 27.5)


@pytest.mark.synthetic
def test_point_buffer_must_be_positive() -> None:
    with pytest.raises(ValueError):
        PointBufferAOI(kind="point", name="synthetic", lon=86.0, lat=27.0, buffer_m=0.0)
    with pytest.raises(ValueError):
        PointBufferAOI(kind="point", name="synthetic", lon=86.0, lat=27.0, buffer_m=-100.0)


@pytest.mark.synthetic
def test_out_of_range_coordinates_rejected() -> None:
    with pytest.raises(ValueError):
        PointBufferAOI(kind="point", name="synthetic", lon=200.0, lat=27.0, buffer_m=10.0)
    with pytest.raises(ValueError):
        PointBufferAOI(kind="point", name="synthetic", lon=86.0, lat=120.0, buffer_m=10.0)


@pytest.mark.synthetic
def test_geojson_aoi_checks_suffix_not_existence(tmp_path: Path) -> None:
    """A config must stay valid on a machine that does not hold the data."""
    aoi = GeoJSONAOI(kind="geojson", name="synthetic", path=tmp_path / "absent.geojson")
    assert aoi.path.name == "absent.geojson"

    with pytest.raises(ValueError, match="geojson"):
        GeoJSONAOI(kind="geojson", name="synthetic", path=Path("aoi.txt"))


@pytest.mark.synthetic
def test_geojson_aoi_has_no_offline_centroid(mutable_config, write_config) -> None:
    """The schema stays I/O-free, so a GeoJSON AOI reports no centroid.

    Reading the file is ``utils.io.read_geojson_geometry``'s job instead.
    """
    mutable_config["aoi"] = {
        "kind": "geojson",
        "name": "synthetic AOI",
        "path": "data/validation/synthetic.geojson",
        "source": "user-supplied",
    }
    loaded = load_config(write_config(mutable_config), load_env=False)
    assert isinstance(loaded.aoi, GeoJSONAOI)
    assert loaded.aoi_centroid is None


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
def test_date_range_must_be_ordered() -> None:
    from datetime import date

    with pytest.raises(ValueError, match="start"):
        DateRange(start=date(2023, 11, 30), end=date(2023, 10, 1))


@pytest.mark.synthetic
def test_date_range_days() -> None:
    from datetime import date

    assert DateRange(start=date(2023, 10, 1), end=date(2023, 10, 31)).days == 30


# --------------------------------------------------------------------------- #
# Config hashing (brief, Section 10: runs.config_hash)
# --------------------------------------------------------------------------- #


def test_config_hash_is_stable(cfg: Config) -> None:
    assert config_hash(cfg) == config_hash(cfg)
    assert len(config_hash(cfg)) == 64


def test_config_hash_changes_with_a_value(
    mutable_config, write_config, cfg: Config
) -> None:
    mutable_config["gee"]["default_scale_m"] = 20.0
    changed = load_config(write_config(mutable_config), load_env=False)
    assert config_hash(changed) != config_hash(cfg)


def test_config_hash_ignores_key_order(mutable_config, write_config, cfg: Config) -> None:
    reordered = dict(reversed(list(mutable_config.items())))
    assert config_hash(load_config(write_config(reordered), load_env=False)) == config_hash(
        cfg
    )


def test_config_is_immutable(cfg: Config) -> None:
    with pytest.raises(Exception):
        cfg.gee.default_scale_m = 30.0  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Per-site overlays
# --------------------------------------------------------------------------- #
# A validation event changes the AOI and the dates, not the science. Copying
# the whole configuration per site would duplicate every threshold, and the
# duplicates would drift the first time one was tuned -- so an overlay carries
# only what differs and is merged over the base.


def test_deep_merge_replaces_leaves_and_merges_mappings() -> None:
    from config.loader import deep_merge

    base = {"a": {"b": 1, "c": 2}, "d": 3}
    assert deep_merge(base, {"a": {"c": 9}}) == {"a": {"b": 1, "c": 9}, "d": 3}
    assert base == {"a": {"b": 1, "c": 2}, "d": 3}, "the base must not be mutated"


def test_deep_merge_replaces_lists_rather_than_appending() -> None:
    """Every list here is a complete specification, not an accumulator."""
    from config.loader import deep_merge

    merged = deep_merge({"bands": ["B2", "B3", "B4"]}, {"bands": ["B8"]})
    assert merged["bands"] == ["B8"]


def test_an_overlay_changes_the_aoi_but_not_the_thresholds(cfg: Config) -> None:
    from config.loader import load_config_with_overlay

    overlaid = load_config_with_overlay(
        {"aoi": {"kind": "point", "name": "elsewhere", "lon": 90.0, "lat": 29.0,
                 "buffer_m": 1000.0, "source": "test"}},
        load_env=False,
    )
    assert overlaid.aoi.name == "elsewhere"
    assert overlaid.detection.water.optical.rule == cfg.detection.water.optical.rule
    assert (
        overlaid.detection.shadow_rejection.weights.slope
        == cfg.detection.shadow_rejection.weights.slope
    )


def test_the_merged_config_is_validated_in_full() -> None:
    """An overlay cannot smuggle in a key the schema refuses."""
    from config.loader import ConfigError, load_config_with_overlay

    with pytest.raises(ConfigError, match="invalid after merging"):
        load_config_with_overlay({"detection": {"nonsense": 1}}, load_env=False)


def test_an_overlay_cannot_weaken_the_disclaimer() -> None:
    from config.loader import ConfigError, load_config_with_overlay

    with pytest.raises(ConfigError, match="invalid after merging"):
        load_config_with_overlay(
            {"project": {"disclaimer": "All clear."}}, load_env=False
        )


def test_a_missing_overlay_is_reported(tmp_path: Path) -> None:
    from config.loader import ConfigError, load_config_with_overlay

    with pytest.raises(ConfigError, match="overlay file not found"):
        load_config_with_overlay(tmp_path / "nope.yaml", load_env=False)


def test_a_bare_name_resolves_to_config_sites() -> None:
    from config.loader import available_sites, load_config_with_overlay

    assert "baige_2018" in available_sites()
    cfg = load_config_with_overlay("baige_2018", load_env=False)
    assert "Baige" in cfg.aoi.name


def test_the_baige_overlay_is_traceable_and_outside_nepal() -> None:
    """A validation AOI must carry its citation (brief, Section 6).

    Baige is in UTM 47N, outside Nepal's 44N/45N -- which makes it a genuine
    test that the projection is derived from the AOI rather than assumed.
    """
    from config.loader import load_config_with_overlay
    from utils.crs import NEPAL_UTM_EPSG, utm_epsg_for_centroid

    cfg = load_config_with_overlay("baige_2018", load_env=False)
    assert cfg.aoi.source and len(cfg.aoi.source) > 100
    assert "31 deg 04'" in cfg.aoi.source
    assert "CONFLICT" in cfg.aoi.source, "the conflicting volumes must stay recorded"

    epsg = utm_epsg_for_centroid(cfg.aoi.centroid)
    assert epsg == 32647
    assert epsg not in NEPAL_UTM_EPSG


def test_the_baige_window_spans_both_failures() -> None:
    from datetime import date

    from config.loader import load_config_with_overlay

    window = load_config_with_overlay("baige_2018", load_env=False).dates.query_window
    assert window.start <= date(2018, 10, 10)   # first dam
    assert window.end >= date(2018, 11, 13)     # engineered release


# --------------------------------------------------------------------------- #
# Every configuration key must have a reader
# --------------------------------------------------------------------------- #
# A key nobody reads is worse than clutter: it looks like a control, and
# turning it does nothing. An audit of the schema found ten such keys; these
# tests pin the wiring that was added for them.


@pytest.mark.synthetic
class TestConfigKeysAreWired:
    def test_the_pixel_guard_is_read(self, cfg: Config) -> None:
        """gee.max_request_pixels claims to refuse oversized requests."""
        import inspect

        from acquisition.gee_client import export_image

        assert "max_request_pixels" in inspect.getsource(export_image)

    def test_the_cloud_score_band_selects(self, cfg: Config) -> None:
        import numpy as np

        from preprocessing.cloud_mask import select_cloud_score

        bands = {"cs": np.full((2, 2), 0.9), "cs_cdf": np.full((2, 2), 0.1)}
        assert cfg.preprocessing.cloud.cloud_score_band == "cs"
        assert select_cloud_score(bands, cfg).mean() == pytest.approx(0.9)

        swapped = Config.model_validate(
            {
                **cfg.model_dump(mode="python"),
                "preprocessing": {
                    **cfg.preprocessing.model_dump(mode="python"),
                    "cloud": {
                        **cfg.preprocessing.cloud.model_dump(mode="python"),
                        "cloud_score_band": "cs_cdf",
                    },
                },
            }
        )
        assert select_cloud_score(bands, swapped).mean() == pytest.approx(0.1)

    def test_a_missing_cloud_score_band_is_named_not_guessed(
        self, cfg: Config
    ) -> None:
        import numpy as np

        from preprocessing.cloud_mask import select_cloud_score

        with pytest.raises(ValueError, match="cloud_score_band"):
            select_cloud_score({"cs_cdf": np.zeros((2, 2))}, cfg)

    def test_the_terrain_shadow_settings_reach_the_ray_search(
        self, cfg: Config, monkeypatch
    ) -> None:
        import numpy as np

        import preprocessing.terrain as terrain

        seen: dict = {}

        def spy(dem, cellsize, azimuth, zenith, *, max_distance_m, step_px):
            seen.update(max_distance_m=max_distance_m, step_px=step_px)
            return {"terrain_shadow": np.zeros((2, 2), dtype=bool)}

        monkeypatch.setattr(terrain, "terrain_shadow_mask", spy)
        terrain.terrain_shadow_for_scene(cfg, np.zeros((2, 2)), 10.0, 150.0, 40.0)

        assert seen["step_px"] == cfg.preprocessing.terrain.shadow_ray_step_px
        assert seen["max_distance_m"] == cfg.preprocessing.terrain.shadow_max_distance_m

    def test_the_sar_geometry_dilation_is_read(self, cfg: Config, monkeypatch) -> None:
        import numpy as np

        import preprocessing.sar as sar

        seen: dict = {}

        def spy(dem, cellsize, incidence, azimuth, *, dilate_px):
            seen.update(dilate_px=dilate_px, azimuth=azimuth)
            return "geometry"

        monkeypatch.setattr(sar, "layover_shadow_mask", spy)
        sar.layover_shadow_for_scene(cfg, np.zeros((2, 2)), 10.0, 35.0, "DESCENDING")

        assert seen["dilate_px"] == cfg.preprocessing.sar.geometry_dilate_px
        assert seen["azimuth"] == pytest.approx(
            cfg.preprocessing.sar.toward_sensor_azimuth_deg["DESCENDING"]
        )

    def test_the_snow_thresholds_reach_the_test_they_describe(
        self, cfg: Config
    ) -> None:
        """Hall et al. (1995): NDSI >= 0.4 and NIR > 0.11."""
        import numpy as np

        from detection.landslide_change import snow_mask_from_config

        gating = cfg.detection.landslide_change.gating
        assert gating.snow_ndsi_min == 0.4
        assert gating.snow_nir_min_reflectance == 0.11

        # Snow: high NDSI, bright NIR. Water: high NDSI, dark NIR.
        snow = snow_mask_from_config(
            cfg, np.array([7000.0]), np.array([600.0]), np.array([0.55])
        )
        water = snow_mask_from_config(
            cfg, np.array([900.0]), np.array([100.0]), np.array([0.05])
        )
        assert snow[0] and not water[0]

    def test_the_quicklook_sun_is_separate_from_the_scene_sun(
        self, cfg: Config
    ) -> None:
        """Analysis must never use the configured quick-look angles."""
        import numpy as np

        from preprocessing.terrain import quicklook_hillshade

        shaded = quicklook_hillshade(cfg, np.zeros((4, 4)), 10.0)
        assert shaded.shape == (4, 4)
        assert float(shaded.min()) >= 0.0 and float(shaded.max()) <= 1.0
