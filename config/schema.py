"""Pydantic models validating ``config/config.yaml``.

Project brief, Section 2: thresholds, weights, dates, AOIs and paths all live in
the config file and are validated here. No magic numbers in code.

Config sections are introduced at the phase that first *consumes* them, so that
every key in ``config.yaml`` has a reader and no dead configuration accumulates.

Phase 0 covers: ``project``, ``paths``, ``aoi``, ``dates``, ``gee``, ``logging``;
Phase 1 adds ``acquisition``; Phase 2 ``preprocessing``; Phase 3 ``detection``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    """Base model: unknown keys are an error, and instances are immutable.

    ``extra="forbid"`` turns a typo in config.yaml into a loud failure instead of
    a silently ignored setting -- which matters when the ignored setting would
    have been a detection threshold.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- #
# Area of interest
# --------------------------------------------------------------------------- #
# Brief, Section 6: the AOI is user-defined as a bounding box, a polygon
# (GeoJSON) or a point plus buffer. No single site may be hard-coded in code --
# the default lives only in config.yaml and is overridable per run.


class AOIBase(Strict):
    name: str = Field(min_length=1, description="Human-readable label for the AOI.")
    source: str | None = Field(
        default=None,
        description=(
            "Provenance of these coordinates: a citation, a URL, or user-supplied. "
            "Required for any AOI used as a validation site, so that no coordinate "
            "in this project is untraceable."
        ),
    )


class BBoxAOI(AOIBase):
    """Axis-aligned bounding box in geographic (WGS84) degrees."""

    kind: Literal["bbox"]
    west: float = Field(ge=-180.0, le=180.0)
    south: float = Field(ge=-90.0, le=90.0)
    east: float = Field(ge=-180.0, le=180.0)
    north: float = Field(ge=-90.0, le=90.0)

    @model_validator(mode="after")
    def _ordered(self) -> BBoxAOI:
        if self.west >= self.east:
            raise ValueError(f"west ({self.west}) must be < east ({self.east})")
        if self.south >= self.north:
            raise ValueError(f"south ({self.south}) must be < north ({self.north})")
        return self

    @property
    def centroid(self) -> tuple[float, float]:
        """(lon, lat) centre of the box, used to pick the UTM zone."""
        return ((self.west + self.east) / 2.0, (self.south + self.north) / 2.0)


class PointBufferAOI(AOIBase):
    """A cited point plus a buffer radius in metres.

    Preferred over a bounding box when the underlying source publishes a point
    (for example coordinates quoted to arcminute precision in a paper): it
    avoids inventing box corners to a precision the source does not support.
    """

    kind: Literal["point"]
    lon: float = Field(ge=-180.0, le=180.0)
    lat: float = Field(ge=-90.0, le=90.0)
    buffer_m: float = Field(gt=0.0, description="Buffer radius in metres.")

    @property
    def centroid(self) -> tuple[float, float]:
        return (self.lon, self.lat)


class GeoJSONAOI(AOIBase):
    """A polygon read from a GeoJSON file on disk.

    Existence is *not* checked here: the schema may legitimately be validated on
    a machine that does not hold the data. The file is resolved and checked when
    it is read (``utils.io.read_geojson_geometry``).
    """

    kind: Literal["geojson"]
    path: Path

    @field_validator("path")
    @classmethod
    def _suffix(cls, v: Path) -> Path:
        if v.suffix.lower() not in {".geojson", ".json"}:
            raise ValueError(f"expected a .geojson/.json file, got {v.name!r}")
        return v


AOIConfig = Annotated[
    Union[BBoxAOI, PointBufferAOI, GeoJSONAOI],
    Field(discriminator="kind"),
]


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #


class DateRange(Strict):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateRange:
        if self.start > self.end:
            raise ValueError(f"start ({self.start}) must be <= end ({self.end})")
        return self

    @property
    def days(self) -> int:
        return (self.end - self.start).days


class DatesConfig(Strict):
    """Default query window for the acquisition modules.

    Per-run overrides, and the pre-/post-event pairs needed for bi-temporal
    change detection (Phase 5), are passed as arguments rather than stored here.
    """

    query_window: DateRange


# --------------------------------------------------------------------------- #
# Google Earth Engine
# --------------------------------------------------------------------------- #


class GEECollections(Strict):
    """Earth Engine collection IDs.

    Kept in config rather than inline in code so that a catalog change is a
    one-line edit. Brief, Section 5: every ID must be verified against the live
    GEE catalog before it is relied upon. ``tests/test_gee_smoke.py`` reports
    what each ID actually returns (bands, image count, date range) rather than
    asserting an assumed value.
    """

    s2_sr: str = Field(min_length=1, description="Sentinel-2 L2A surface reflectance.")
    s2_cloud_score_plus: str = Field(
        min_length=1, description="Cloud Score+, used for S2 cloud masking."
    )
    s1_grd: str = Field(min_length=1, description="Sentinel-1 GRD backscatter.")
    landsat8_l2: str = Field(min_length=1, description="Landsat 8 Collection 2 Level 2.")
    landsat9_l2: str = Field(min_length=1, description="Landsat 9 Collection 2 Level 2.")
    dem_glo30: str = Field(min_length=1, description="Copernicus GLO-30 DEM.")


class GEEConfig(Strict):
    project_env_var: str = Field(
        default="GEE_PROJECT",
        min_length=1,
        description=(
            "Name of the environment variable holding the GEE Cloud project ID. "
            "Brief, Section 3: the ID itself is read from .env, never hard-coded."
        ),
    )
    collections: GEECollections
    default_scale_m: float = Field(
        gt=0.0,
        description="Working grid resolution in metres (Sentinel-2 native: 10 m).",
    )
    max_request_pixels: int = Field(
        gt=0,
        description="Guard against accidentally requesting a full scene from a laptop.",
    )


# --------------------------------------------------------------------------- #
# Acquisition (Phase 1)
# --------------------------------------------------------------------------- #

#: Band lists are tuples so that a frozen config cannot be mutated in place.
BandList = Annotated[tuple[str, ...], Field(min_length=1)]


class Sentinel2Acquisition(Strict):
    reflectance_bands: BandList
    qa_bands: tuple[str, ...] = ()
    cloud_score_bands: tuple[str, ...] = Field(
        default=(),
        description=(
            "Cloud Score+ bands to export alongside the scene, matched by "
            "system:index. Empty disables the Cloud Score+ export, in which "
            "case cloud masking falls back to SCL."
        ),
    )


class Sentinel1Acquisition(Strict):
    bands: BandList
    instrument_mode: str = Field(min_length=1)
    orbit_pass: Literal["ASCENDING", "DESCENDING"] | None = Field(
        default=None,
        description=(
            "None keeps both orbit directions, exported separately with the "
            "orbit recorded (brief, Section 5)."
        ),
    )


class LandsatAcquisition(Strict):
    reflectance_bands: BandList
    qa_bands: tuple[str, ...] = ()


class DEMAcquisition(Strict):
    bands: BandList
    tile_version_policy: Literal["highest", "lowest"] = Field(
        default="highest",
        description=(
            "How to pick among overlapping Copernicus DEM tile versions. "
            "Deterministic selection prevents a mosaic that blends versions "
            "(see docs/methods.md 0.6)."
        ),
    )


class AcquisitionConfig(Strict):
    max_scenes_per_sensor: int = Field(
        gt=0, description="Upper bound on scenes exported per sensor per run."
    )
    export_crs: str = Field(
        default="auto",
        description=(
            "'auto' derives the UTM zone from the AOI centroid (brief, Section "
            "6); an explicit 'EPSG:xxxxx' overrides it."
        ),
    )
    max_export_bytes: int = Field(
        gt=0,
        description="Refuse a single export above this size, with a clear error.",
    )
    max_cloud_fraction: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description=(
            "Scene-level cloud screening for the optical sensors, as a "
            "percentage. This decides which scenes are worth downloading and is "
            "NOT the per-pixel cloud mask (Phase 2) -- the two are different "
            "things and both are needed. Scenes dropped by this filter are "
            "counted and logged, never silently discarded. None disables it."
        ),
    )
    sentinel2: Sentinel2Acquisition
    sentinel1: Sentinel1Acquisition
    landsat: LandsatAcquisition
    dem: DEMAcquisition

    @field_validator("export_crs")
    @classmethod
    def _crs_form(cls, v: str) -> str:
        import re

        if v != "auto" and not re.fullmatch(r"EPSG:\d{4,6}", v):
            raise ValueError(f"export_crs must be 'auto' or 'EPSG:xxxxx', got {v!r}")
        return v


# --------------------------------------------------------------------------- #
# Preprocessing (Phase 2)
# --------------------------------------------------------------------------- #


class TerrainPreprocessing(Strict):
    quicklook_azimuth_deg: float = Field(ge=0.0, le=360.0)
    quicklook_altitude_deg: float = Field(ge=0.0, le=90.0)
    shadow_ray_step_px: float = Field(
        gt=0.0, description="Ray sampling interval for the cast-shadow search."
    )
    shadow_max_distance_m: float | None = Field(
        default=None,
        gt=0.0,
        description=(
            "None derives the search distance from the DEM's own relief, which "
            "is exact rather than a cutoff."
        ),
    )


class CloudPreprocessing(Strict):
    method: Literal["cloud_score_plus", "scl", "both"]
    cloud_score_threshold: float = Field(ge=0.0, le=1.0)
    cloud_score_band: Literal["cs", "cs_cdf"] = "cs"
    scl_cloud_classes: tuple[int, ...] = Field(min_length=1)
    scl_cloud_shadow_classes: tuple[int, ...]
    scl_defective_classes: tuple[int, ...]
    dilate_px: int = Field(ge=0)

    @field_validator(
        "scl_cloud_classes", "scl_cloud_shadow_classes", "scl_defective_classes"
    )
    @classmethod
    def _valid_scl(cls, v: tuple[int, ...]) -> tuple[int, ...]:
        for code in v:
            if not 0 <= code <= 11:
                raise ValueError(f"SCL class codes run 0-11, got {code}")
        return v

    @model_validator(mode="after")
    def _terrain_shadow_is_not_cloud(self) -> CloudPreprocessing:
        # SCL class 2 ("dark area pixels") is dominated by topographic shadow in
        # steep terrain. Masking it as cloud would throw away the very signal
        # this project exists to reason about (brief, Section 7.1).
        if 2 in self.scl_cloud_classes or 2 in self.scl_cloud_shadow_classes:
            raise ValueError(
                "SCL class 2 (dark area pixels) must not be treated as cloud or "
                "cloud shadow: in steep terrain it is mostly TERRAIN shadow, "
                "which this project must keep rather than mask (brief, 7.1)"
            )
        return self


class SARPreprocessing(Strict):
    convert_to_db: bool = Field(
        description=(
            "COPERNICUS/S1_GRD is already in dB; converting again would corrupt "
            "it. True only for a linear-power source such as S1_GRD_FLOAT."
        )
    )
    speckle_filter: Literal["lee", "median", "none"]
    speckle_window_px: int = Field(ge=3)
    equivalent_number_of_looks: float = Field(gt=0.0)
    toward_sensor_azimuth_deg: dict[str, float]
    geometry_dilate_px: int = Field(ge=0)

    @field_validator("speckle_window_px")
    @classmethod
    def _odd_window(cls, v: int) -> int:
        if v % 2 == 0:
            raise ValueError(f"speckle window must be odd so it has a centre, got {v}")
        return v

    @field_validator("toward_sensor_azimuth_deg")
    @classmethod
    def _known_passes(cls, v: dict[str, float]) -> dict[str, float]:
        unknown = set(v) - {"ASCENDING", "DESCENDING"}
        if unknown:
            raise ValueError(f"unknown orbit pass key(s): {sorted(unknown)}")
        for key, azimuth in v.items():
            if not 0.0 <= azimuth <= 360.0:
                raise ValueError(f"{key} azimuth must be 0-360, got {azimuth}")
        return v


class HydrologyPreprocessing(Strict):
    stream_threshold_cells: int = Field(gt=0)
    depression_handling: Literal["breach", "fill", "none"]


class StackPreprocessing(Strict):
    resampling: Literal["nearest", "bilinear", "cubic"]


class PreprocessingConfig(Strict):
    terrain: TerrainPreprocessing
    cloud: CloudPreprocessing
    sar: SARPreprocessing
    hydrology: HydrologyPreprocessing
    stack: StackPreprocessing


# --------------------------------------------------------------------------- #
# Detection (Phase 3 onward)
# --------------------------------------------------------------------------- #


class OpticalWaterConfig(Strict):
    """Optical water rule (brief, Section 7.2).

    The index thresholds default to zero because zero is the land/water
    boundary proposed by the authors of each index (McFeeters 1996 for NDWI;
    Xu 2006 for MNDWI), not a value tuned in this project.
    """

    rule: Literal["ndwi", "mndwi", "both_and", "both_or"] = "both_and"
    ndwi_threshold: float = 0.0
    mndwi_threshold: float = 0.0
    snow_screen_nir_max_reflectance: float | None = Field(
        default=0.11,
        gt=0.0,
        le=1.0,
        description=(
            "Reject index-water whose NIR reflectance reaches this, because "
            "MNDWI is the same expression as NDSI and cannot tell snow from "
            "water. 0.11 is the MODIS snow algorithm's water/snow "
            "discriminator (Hall et al. 1995, 2002). None disables the screen."
        ),
    )
    reflectance_scale: float = Field(
        default=1.0e-4,
        gt=0.0,
        description=(
            "Converts stored Sentinel-2 scaled integers to reflectance for the "
            "snow screen. The indices are ratios and so need no scaling."
        ),
    )


class SARWaterConfig(Strict):
    """Data-driven Sentinel-1 water threshold (brief, Section 7.2).

    ``fixed_threshold_db`` is ``None`` by default and that is deliberate: where
    the histogram does not support a threshold, the SAR mask is reported as
    *unavailable with a reason* rather than falling back to an invented dB
    cutoff (brief, Section 2 -- never fabricate a measurement).
    """

    band: Literal["VV", "VH"] = "VV"
    threshold_method: Literal["tiled_otsu", "otsu", "fixed"] = "tiled_otsu"
    histogram_bins: int = Field(default=256, ge=16)
    search_range_db: tuple[float, float] = (-35.0, 5.0)
    tile_px: int = Field(default=128, ge=16)
    min_tile_valid_fraction: float = Field(default=0.5, ge=0.0, le=1.0)
    min_separation: float = Field(
        default=2.0,
        ge=0.0,
        description=(
            "Minimum dimensionless separation of the two fitted modes for a "
            "histogram to count as bimodal; 2.0 is the two-peak condition of "
            "Ashman, Bird & Zepf (1994) eq. 3.2."
        ),
    )
    min_tiles: int = Field(default=1, ge=1)
    fixed_threshold_db: float | None = None

    @field_validator("search_range_db")
    @classmethod
    def _ordered_range(cls, v: tuple[float, float]) -> tuple[float, float]:
        low, high = v
        if low >= high:
            raise ValueError(f"search_range_db must be (low, high) with low < high, got {v}")
        return v

    @model_validator(mode="after")
    def _fixed_needs_a_value(self) -> SARWaterConfig:
        if self.threshold_method == "fixed" and self.fixed_threshold_db is None:
            raise ValueError(
                "threshold_method 'fixed' needs fixed_threshold_db to be set; it is "
                "None, and this project does not invent a backscatter threshold"
            )
        return self


class WaterPolygonConfig(Strict):
    min_area_m2: float = Field(default=1000.0, ge=0.0)
    connectivity: Literal[4, 8] = 8


class WaterDetectionConfig(Strict):
    """Rule-based water detection.

    Note what is *absent*: nothing here consults the terrain-shadow mask. This
    stage is the shadow-naive baseline that Phase 4 is measured against, because
    Section 7.3 requires the false-water reduction to be reported against the
    index-only mask.
    """

    optical: OpticalWaterConfig = OpticalWaterConfig()
    sar: SARWaterConfig = SARWaterConfig()
    combine: Literal["optical", "sar", "union", "intersection"] = Field(
        default="intersection",
        description=(
            "How the per-source masks are combined. 'intersection' (both "
            "sensors agree) is the default on measured evidence: single-scene "
            "SAR amplitude thresholding is unreliable in steep terrain, so "
            "'union' is swamped by radar layover/shadow false water. See "
            "config.yaml and docs/methods.md 3.5."
        ),
    )
    polygons: WaterPolygonConfig = WaterPolygonConfig()


# --- Shadow rejection (Phase 4) ------------------------------------------- #


class SlopeMembership(Strict):
    water_max_deg: float = Field(
        default=10.0,
        gt=0.0,
        le=90.0,
        description=(
            "Slope at which water support crosses zero. 10 deg is the "
            "topographic-shadow mask threshold of Chen et al. (2021) for "
            "glacial lakes in High Mountain Asia."
        ),
    )
    softness_deg: float = Field(default=4.0, gt=0.0)
    flat_support_scale: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "How much flat ground counts as evidence FOR water. Default 0: "
            "steep ground rules water out, but flatness is a necessary "
            "condition most dry land also meets, so it does not rule water in. "
            "1.0 makes the term symmetric."
        ),
    )


class IlluminationMembership(Strict):
    shadow_below: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Shaded-relief threshold of Chen et al. (2021).",
    )
    softness: float = Field(default=0.10, gt=0.0)


class NIRMembership(Strict):
    water_max_reflectance: float = Field(default=0.11, gt=0.0, le=1.0)
    softness: float = Field(default=0.04, gt=0.0)


class WaterIndexMembership(Strict):
    softness: float = Field(default=0.15, gt=0.0)


class SARMembership(Strict):
    water_max_db: float | None = Field(
        default=None,
        description=(
            "None uses the threshold Phase 3 derived from the scene, so a run "
            "has one SAR threshold rather than two."
        ),
    )
    softness_db: float = Field(default=2.5, gt=0.0)


class PersistenceMembership(Strict):
    water_min_fraction: float = Field(default=0.5, ge=0.0, le=1.0)
    softness: float = Field(default=0.25, gt=0.0)
    min_observations: int = Field(
        default=2,
        ge=1,
        description=(
            "Below this many valid observations the persistence term is "
            "dropped rather than computed from too little evidence."
        ),
    )


class ShadowRejectionMembership(Strict):
    optical_determinacy_scale: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "How far the optical indices are trusted to determine surface "
            "material inside a shadow, relative to SAR. NDWI/MNDWI are band "
            "ratios in which the illumination factor cancels to first order, "
            "so they retain material information in shadow -- but only to "
            "first order, hence a value below 1."
        ),
    )
    slope: SlopeMembership = SlopeMembership()
    illumination: IlluminationMembership = IlluminationMembership()
    nir: NIRMembership = NIRMembership()
    water_index: WaterIndexMembership = WaterIndexMembership()
    sar: SARMembership = SARMembership()
    persistence: PersistenceMembership = PersistenceMembership()


class ShadowRejectionWeights(Strict):
    """Evidence weights in arbitrary points. All convention -- see
    docs/methods.md 4.6 for the sensitivity analysis reported in their place."""

    water_index: float = Field(default=1.0, ge=0.0)
    nir: float = Field(default=1.5, ge=0.0)
    slope: float = Field(default=2.0, ge=0.0)
    sar_backscatter: float = Field(default=1.0, ge=0.0)
    persistence: float = Field(default=1.0, ge=0.0)
    illumination: float = Field(default=1.0, ge=0.0)
    terrain_shadow_mask: float = Field(default=1.5, ge=0.0)

    @model_validator(mode="after")
    def _not_all_zero(self) -> ShadowRejectionWeights:
        if not any(getattr(self, name) > 0.0 for name in type(self).model_fields):
            raise ValueError("at least one evidence weight must be greater than zero")
        return self


class ShadowRejectionConfig(Strict):
    """Transparent additive evidence fusion (brief, Section 7.3).

    ``p_terrain_shadow`` is the probability that shadow leaves the surface
    material *indeterminate* (the brief's Section 7.5 class 3), not the
    probability that a pixel is geometrically shadowed -- the Phase 2 mask
    already states that, and a lake inside a shadow is still a lake.
    """

    membership: ShadowRejectionMembership = ShadowRejectionMembership()
    weights: ShadowRejectionWeights = ShadowRejectionWeights()
    material_determinacy_weight: float = Field(
        default=2.0,
        ge=0.0,
        description=(
            "How strongly determinate material evidence suppresses the shadow "
            "class. This is what makes Section 7.3 rule 2 fall out of the "
            "fusion instead of being special-cased."
        ),
    )
    temperature: float = Field(default=1.0, gt=0.0)
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    require_optical_for_water: bool = Field(
        default=True,
        description=(
            "Refuse a WATER verdict where no optical term applied, marking the "
            "pixel uncertain instead. A pixel counts as valid if ANY single "
            "term applies, and the DEM-derived and SAR terms apply everywhere, "
            "so a pixel with no usable optical data still received a verdict "
            "-- decided by radar, over which water, dry snow and smooth ice "
            "are all dark. Measured on Baige 2018, where 40.1% of the "
            "Sentinel-2 scene is optical nodata: the fusion reported water at "
            "a median 3,822 m on flat high ground, and 88.9% of everything it "
            "added over the rule-based mask had no optical observation. Every "
            "rule in Section 7.3 begins 'dark OPTICAL pixel' and its third "
            "rule makes uncorroborated SAR uncertain, so this follows the "
            "section's intent for a case it does not cover. Set false to "
            "restore the old behaviour; the reason mask "
            "'water_without_optical' is populated either way."
        ),
    )
    trust_sar_in_layover_shadow: bool = Field(
        default=False,
        description=(
            "Brief, Section 7.3: a SAR-water-like pixel inside the layover or "
            "shadow mask is uncertain and the fusion defers to optical "
            "evidence. True would trust SAR everywhere."
        ),
    )


# --- Bi-temporal landslide change detection (Phase 5) ---------------------- #


class LandslideOpticalConfig(Strict):
    """Optical change signals (brief, Section 7.4)."""

    ndvi_drop: float = Field(
        default=-0.15,
        lt=0.0,
        ge=-2.0,
        description=(
            "NDVIvar = NDVI_post - NDVI_pre below which vegetation loss is "
            "flagged. -0.15 is the upper end of the -0.20..-0.15 range of "
            "Notti et al. (2023), who stress it has no fixed value and must be "
            "calibrated per AOI."
        ),
    )
    brightness_method: Literal["mad_zscore", "fixed"] = "mad_zscore"
    brightness_min_z: float = Field(default=3.0, gt=0.0)
    brightness_fixed_increase: float | None = None

    @model_validator(mode="after")
    def _fixed_needs_a_value(self) -> LandslideOpticalConfig:
        if self.brightness_method == "fixed" and self.brightness_fixed_increase is None:
            raise ValueError(
                "brightness_method 'fixed' needs brightness_fixed_increase to be "
                "set; no brightness-change threshold is published, so this "
                "project does not invent one"
            )
        return self


class LandslideSARConfig(Strict):
    """Sentinel-1 change signal.

    The magnitude of the backscatter change is used, not its sign: backscatter
    rises on some parts of a landslide and falls on others (Burrows et al.
    2022; Mondini et al. 2021).
    """

    change_method: Literal["mad_zscore", "fixed"] = "mad_zscore"
    min_abs_z: float = Field(default=3.0, gt=0.0)
    fixed_min_abs_db: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def _fixed_needs_a_value(self) -> LandslideSARConfig:
        if self.change_method == "fixed" and self.fixed_min_abs_db is None:
            raise ValueError(
                "change_method 'fixed' needs fixed_min_abs_db to be set; this "
                "project does not invent a backscatter-change threshold"
            )
        return self


class LandslideGatingConfig(Strict):
    """What is excluded before change is believed."""

    min_slope_deg: float = Field(
        default=15.0,
        ge=0.0,
        le=90.0,
        description="Notti et al. (2023) pair their NDVI threshold with slope > 15 deg.",
    )
    min_median_slope_deg: float = Field(
        default=17.0,
        ge=0.0,
        le=90.0,
        description="Polygon-level median slope filter; Notti et al. used 17 and 20 deg.",
    )
    exclude_snow: bool = True
    snow_ndsi_min: float = Field(default=0.4, ge=-1.0, le=1.0)
    snow_nir_min_reflectance: float = Field(default=0.11, gt=0.0, le=1.0)
    exclude_terrain_shadow: bool = True
    exclude_water_on_post_date: bool = Field(
        default=True,
        description=(
            "Exclude pixels that are open water on the post date: a landslide "
            "deposit cannot be under water. Excluding only NEWLY wet pixels is "
            "insufficient -- a river that deepens into a lake is water on both "
            "dates yet trips the NDVI and SAR signals."
        ),
    )


class LandslidePolygonConfig(Strict):
    min_area_m2: float = Field(default=1000.0, ge=0.0)
    connectivity: Literal[4, 8] = 8


class LandslideChangeConfig(Strict):
    """Bi-temporal change detection.

    This module is the sole source of *novelty*: the brief (Section 7.4) is
    explicit that the U-Net classifies landslide-like surfaces on a single
    date, so "new" must come from here.
    """

    optical: LandslideOpticalConfig = LandslideOpticalConfig()
    sar: LandslideSARConfig = LandslideSARConfig()
    min_agreeing_signals: int = Field(
        default=2,
        ge=1,
        description=(
            "How many available signals must agree. Each has a known failure "
            "mode alone, so agreement is what makes them complementary."
        ),
    )
    gating: LandslideGatingConfig = LandslideGatingConfig()
    polygons: LandslidePolygonConfig = LandslidePolygonConfig()


# --- River blockage detection (Phase 7) ------------------------------------ #


class BlockageWeights(Strict):
    """Confidence weights. Convention -- no published weighting exists."""

    intersects_stream: float = Field(default=1.0, ge=0.0)
    new_upstream_water: float = Field(default=3.0, ge=0.0)
    downstream_water_loss: float = Field(default=2.0, ge=0.0)
    channel_narrowing: float = Field(default=2.0, ge=0.0)

    @model_validator(mode="after")
    def _not_all_zero(self) -> BlockageWeights:
        if self.total() <= 0.0:
            raise ValueError("at least one blockage weight must be greater than zero")
        return self

    def total(self) -> float:
        return sum(getattr(self, name) for name in type(self).model_fields)

    def obstruction_total(self) -> float:
        """Weight carried by the obstruction signals alone.

        Proximity is excluded: it is a precondition, not evidence of
        obstruction (brief, Section 7.6).
        """
        return (
            self.new_upstream_water
            + self.downstream_water_loss
            + self.channel_narrowing
        )


class BlockageConfig(Strict):
    """River blockage candidates (brief, Section 7.6).

    A candidate requires proximity to the stream network **and** evidence of
    obstruction. Proximity alone never suffices, which ``min_evidence_types``
    enforces by refusing to go below 1.
    """

    min_landslide_area_m2: float = Field(
        default=1000.0,
        ge=0.0,
        description=(
            "Smallest landslide component that may become a dam candidate. "
            "Phase 5 applies this floor to its own polygons, but Phase 7 "
            "consumes the raw change mask and so bypassed it: on the Baige "
            "2018 run, 76 of 153 candidates were a SINGLE 10 m pixel, and 18 "
            "scored confidence 1.000, because the obstruction evidence is "
            "measured over a 500 m reach and a one-pixel fragment beside a "
            "blocked river sees all of it. Defaults to the Phase 5 polygon "
            "floor: anything smaller is below the system's own threshold for "
            "calling something a landslide at all. A deployment should raise "
            "it toward the channel width, since a deposit must span the river "
            "to dam it."
        ),
    )
    merge_along_stream_m: float = Field(
        default=500.0,
        ge=0.0,
        description=(
            "How far apart along the stream network two blockages must lie to "
            "count as distinct. One dam is routinely detected as several "
            "landslide components -- the slope gate carves the "
            "channel-crossing part out of a deposit on a flat valley floor, "
            "and cloud and snow fragment it further -- and because the "
            "obstruction evidence is measured over a reach, every fragment "
            "sees the same impounded water and reports it as independent "
            "confirmation. On Baige 2018 the four top-ranked candidates "
            "claimed 136,500-154,800 m2 of gained water upstream: the same "
            "water, counted four times. Defaults to evidence_search_m, "
            "because two blockages closer than the radius over which evidence "
            "is gathered cannot be distinguished by that evidence. Note that 0 "
            "does not disable merging: deposits reaching the SAME stream "
            "pixels are one obstruction at any distance, which is the "
            "slope-gate case. This setting controls only how far along the "
            "channel the grouping additionally extends."
        ),
    )
    max_distance_to_stream_m: float = Field(default=50.0, gt=0.0)
    evidence_search_m: float = Field(default=500.0, gt=0.0)
    channel_zone_m: float = Field(
        default=30.0,
        gt=0.0,
        description=(
            "The cross-section examined at the blockage. Must stay well inside "
            "evidence_search_m: the zone grows in all directions, so a generous "
            "value reaches into the water impounded upstream and the narrowing "
            "test then sees more water after the blockage than before."
        ),
    )
    min_evidence_types: int = Field(
        default=1,
        ge=1,
        description=(
            "How many obstruction signals must be present. At least 1: a "
            "landslide beside a river is not a dam (required system test 4)."
        ),
    )
    min_new_upstream_water_m2: float = Field(default=1000.0, ge=0.0)
    min_downstream_water_loss_m2: float = Field(default=1000.0, ge=0.0)
    min_channel_narrowing_fraction: float = Field(default=0.3, ge=0.0, le=1.0)
    weights: BlockageWeights = BlockageWeights()
    min_confidence: float = Field(default=0.3, ge=0.0, le=1.0)
    code_prefix: str = Field(default="ND", min_length=1)
    site_type: str = Field(default="Potential Landslide Dam", min_length=1)


# --- Barrier lake detection and tracking (Phase 8) ------------------------- #


class BarrierLakeConfig(Strict):
    """Barrier lakes upstream of a blockage (brief, Section 7.7).

    ``min_observable_fraction`` is the integrity control: a lake absent from a
    scene has only *disappeared* if its own footprint could be seen. Cloud
    over a barrier lake otherwise reads as a breach.
    """

    min_area_m2: float = Field(default=1000.0, ge=0.0)
    upstream_search_m: float = Field(default=2000.0, gt=0.0)
    min_new_area_m2: float = Field(default=1000.0, ge=0.0)
    min_expansion_fraction: float = Field(default=0.10, ge=0.0)
    lake_width_m: float = Field(
        default=300.0,
        gt=0.0,
        description=(
            "How far from the channel impounded water may spread. A barrier "
            "lake fills the valley floor, so this must contain it."
        ),
    )
    match_min_overlap_fraction: float = Field(default=0.30, gt=0.0, le=1.0)
    min_residual_water_fraction: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description=(
            "How much of a lake's last footprint must still hold water for an "
            "unmatched lake to be called re-partitioned rather than gone. "
            "Being unmatched means no QUALIFYING lake overlapped the "
            "footprint, which is not the same as the footprint being dry: a "
            "lake that merges into the river channel, or stops qualifying as "
            "new or expanding, is unmatched while still full of water. On "
            "Baige 2018 the old logic reported four lakes as disappeared, "
            "each claiming it held no water, on a date when the lake had "
            "grown from 166,800 to 294,000 m2 and 40.9% of the largest "
            "footprint was still water. Deliberately LOW: declaring a barrier "
            "lake gone reads as a breach, so a little residual water should "
            "be enough to withhold that claim."
        ),
    )
    min_observable_fraction: float = Field(
        default=0.50,
        gt=0.0,
        le=1.0,
        description=(
            "Fraction of a lake's last known footprint that must be "
            "observable before its absence counts as a disappearance rather "
            "than a missed observation."
        ),
    )
    code_prefix: str = Field(default="BL", min_length=1)


class DetectionConfig(Strict):
    water: WaterDetectionConfig = WaterDetectionConfig()
    shadow_rejection: ShadowRejectionConfig = ShadowRejectionConfig()
    landslide_change: LandslideChangeConfig = LandslideChangeConfig()
    blockage: BlockageConfig = BlockageConfig()
    barrier_lake: BarrierLakeConfig = BarrierLakeConfig()


# --------------------------------------------------------------------------- #
# Analysis (Phase 10 onward)
# --------------------------------------------------------------------------- #


class ShorelineConfig(Strict):
    """How the water surface elevation is read from the DEM.

    Brief, Section 8: the median DEM elevation along a buffer just outside the
    water polygon, with its spread stored as uncertainty.
    """

    buffer_m: float = Field(
        default=10.0,
        gt=0.0,
        description=(
            "Ring width outside the water polygon. Narrow by default: on a "
            "steep shoreline a wider ring walks up the valley wall and biases "
            "the WSE upward (measured +10.7 m from 10 m to 50 m at Tsho Rolpa)."
        ),
    )
    statistic: Literal["median", "p25", "min"] = "median"
    min_samples: int = Field(default=20, ge=1)
    spread_statistic: Literal["iqr", "std", "mad"] = "iqr"


class DepthBranchConfig(Strict):
    """Thresholds deciding branch A, B or C (brief, Section 8)."""

    flat_std_tolerance_m: float = Field(
        default=0.5,
        ge=0.0,
        description=(
            "Standard deviation of DEM elevation inside the lake below which "
            "the DEM is taken to have recorded a flattened water surface "
            "(Branch B). GLO-30 flattens water bodies; measured 0.00 m over "
            "Tsho Rolpa."
        ),
    )
    dem_water_overlap_fraction: float = Field(default=0.5, ge=0.0, le=1.0)
    use_height_error_mask: bool = Field(
        default=True,
        description=(
            "Split a mixed lake per pixel using the GLO-30 height-error mask. "
            "A barrier lake routinely floods new ground AND deepens the river "
            "it dams: over the new ground the DEM holds the pre-lake surface "
            "(Branch A), over the old channel it recorded a WATER SURFACE "
            "(Branch B) and 'WSE - DEM' there measures the RISE in water "
            "level, not the depth. A height error of exactly zero means no "
            "height was measured, which over water is the product stating it "
            "recorded a surface rather than a bed. On the Baige lake it reads "
            "62.8% zero against 64.2% of the lake being pre-existing river -- "
            "agreement to within 1.4 points. Branch A is then computed over "
            "the measured part only and the volume reported as a LOWER BOUND, "
            "which is traceable to Section 8 pixel by pixel; summing the two "
            "together was not. Set false to apply one branch to the whole "
            "lake as before."
        ),
    )
    min_branch_b_fraction_to_split: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description=(
            "Below this Branch B fraction the lake is treated as wholly "
            "Branch A rather than split. A few scattered zero-error pixels "
            "are noise in the mask, not a submerged channel, and splitting on "
            "them would discard good data and label the result a lower bound "
            "for no reason. convention."
        ),
    )
    min_depth_for_branch_a_m: float = Field(default=1.0, ge=0.0)


class DepthVolumeConfig(Strict):
    shoreline: ShorelineConfig = ShorelineConfig()
    branch: DepthBranchConfig = DepthBranchConfig()
    dem_vertical_error_m: float | None = Field(
        default=None,
        ge=0.0,
        description="None uses the GLO-30 HEM band, the product's own estimate.",
    )
    branch_b_empirical_formula: str | None = Field(
        default=None,
        description=(
            "Branch B empirical area-volume relationship. The brief permits "
            "one only with approval and a cited formula; none has been "
            "approved, so any value raises rather than silently producing a "
            "number that looks like a measurement."
        ),
    )


class RiskWeights(Strict):
    """Factor weights (brief, Section 9). All convention -- no published
    weighting exists for this combination; see docs/methods.md 11.4."""

    lake_growth_rate: float = Field(default=3.0, ge=0.0)
    lake_volume: float = Field(default=2.0, ge=0.0)
    new_landslide_activity: float = Field(default=2.0, ge=0.0)
    blockage_confidence: float = Field(default=3.0, ge=0.0)
    slope: float = Field(default=1.0, ge=0.0)
    rainfall: float = Field(
        default=0.0,
        ge=0.0,
        description="Optional in the brief; 0.0 until a rainfall source is wired in.",
    )

    @model_validator(mode="after")
    def _not_all_zero(self) -> RiskWeights:
        if self.total() <= 0.0:
            raise ValueError("at least one risk weight must be greater than zero")
        return self

    def total(self) -> float:
        return sum(getattr(self, name) for name in type(self).model_fields)


#: A scale is [value scoring 0, value scoring 1].
RiskScale = Annotated[tuple[float, float], Field(min_length=2, max_length=2)]


class RiskScales(Strict):
    lake_growth_rate_m2_per_day: RiskScale = (0.0, 2000.0)
    lake_volume_m3: RiskScale = (0.0, 10_000_000.0)
    new_landslide_area_m2: RiskScale = (0.0, 50_000.0)
    blockage_confidence: RiskScale = (0.0, 1.0)
    slope_deg: RiskScale = (15.0, 45.0)
    rainfall_mm_24h: RiskScale = (0.0, 100.0)

    @field_validator("*")
    @classmethod
    def _distinct_ends(cls, v: tuple[float, float]) -> tuple[float, float]:
        if v[0] == v[1]:
            raise ValueError(
                f"a scale needs two distinct ends, got {v}: otherwise every value "
                "maps to the same score"
            )
        return v


class RiskLevels(Strict):
    """Score at or above which each level is reached."""

    monitor: float = Field(default=0.25, ge=0.0, le=1.0)
    high_risk: float = Field(default=0.50, ge=0.0, le=1.0)
    critical: float = Field(default=0.75, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> RiskLevels:
        if not self.monitor < self.high_risk < self.critical:
            raise ValueError(
                "level thresholds must increase: monitor < high_risk < critical, "
                f"got {self.monitor}, {self.high_risk}, {self.critical}"
            )
        return self


class RiskConfig(Strict):
    weights: RiskWeights = RiskWeights()
    scales: RiskScales = RiskScales()
    levels: RiskLevels = RiskLevels()
    min_data_coverage: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Below this share of total weight being measurable, the assessment "
            "is flagged insufficient_data. An unmeasured factor must never read "
            "as reassurance."
        ),
    )


class TemporalChangeConfig(Strict):
    """Lake-area time series and trend (brief, Section 7.8)."""

    min_valid_observations: int = Field(
        default=3,
        ge=1,
        description=(
            "Below this, the trend is Unknown -- not Stable. Too little data "
            "is not evidence of stability, and two points can always be "
            "joined by a line."
        ),
    )
    trend_metric: Literal["relative", "absolute"] = Field(
        default="relative",
        description=(
            "relative scales the stable band by lake size, since an absolute "
            "m^2/day threshold means different things for a pond and a lake."
        ),
    )
    stable_fraction_per_day: float = Field(default=0.001, ge=0.0)
    stable_rate_m2_per_day: float = Field(default=100.0, ge=0.0)
    slope_method: Literal["theil_sen", "endpoints"] = Field(
        default="theil_sen",
        description="Theil-Sen (Sen 1968): the median of all pairwise slopes.",
    )
    max_age_days: int = Field(
        default=60,
        ge=1,
        description=(
            "If the most recent valid observation is older than this, the "
            "trend is Unknown with a staleness reason."
        ),
    )


class AnalysisConfig(Strict):
    depth_volume: DepthVolumeConfig = DepthVolumeConfig()
    risk: RiskConfig = RiskConfig()
    temporal_change: TemporalChangeConfig = TemporalChangeConfig()


# --------------------------------------------------------------------------- #
# Segmentation models (Phase 6)
# --------------------------------------------------------------------------- #


class PatchConfig(Strict):
    """Training patch geometry (brief, Section 7.5)."""

    size_px: int = Field(
        default=256,
        gt=0,
        description="Patch edge in pixels. The brief specifies 256.",
    )
    stride_px: int = Field(
        default=128,
        gt=0,
        description=(
            "Step between patch origins. Below size_px the patches overlap, "
            "which augments a small hand-labelled set -- but overlapping "
            "patches must never straddle a split boundary, or the same ground "
            "appears in train and test. See SplitConfig."
        ),
    )
    scale_m: float = Field(
        default=10.0,
        gt=0.0,
        description="Ground sample distance the patches are cut at.",
    )
    min_labelled_fraction: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description=(
            "Discard a patch whose labelled pixels fall below this fraction. "
            "Mostly-ignore patches contribute almost no gradient and dilute "
            "the per-class balance that Section 7.5's metrics are read from."
        ),
    )


class SplitConfig(Strict):
    """Train/validation/test partitioning (brief, Section 7.5).

    The brief forbids random pixel or random patch splits that leak spatially
    adjacent data. ``strategy`` therefore has no "random" option at all: an
    unavailable option cannot be selected by accident.
    """

    strategy: Literal["geographic", "event"] = Field(
        default="geographic",
        description=(
            "geographic: split by spatial block, so no block contributes to "
            "more than one partition. event: split by labelled event, so a "
            "whole landslide or flood goes to one partition. Both satisfy "
            "Section 7.5; random splitting is not offered."
        ),
    )
    block_km: float = Field(
        default=10.0,
        gt=0.0,
        description=(
            "Edge of a geographic block, in km. Must exceed the patch edge by "
            "enough that adjacent patches rarely cross a block boundary."
        ),
    )
    train_fraction: float = Field(default=0.70, gt=0.0, lt=1.0)
    val_fraction: float = Field(default=0.15, gt=0.0, lt=1.0)
    buffer_px: int = Field(
        default=256,
        ge=0,
        description=(
            "Patches within this distance of a split boundary are dropped. "
            "Without it, two patches on either side of the line share ground "
            "and the test set is contaminated by adjacency. Defaults to one "
            "patch edge."
        ),
    )
    seed: int = Field(
        default=0,
        description="Seed for assigning blocks to partitions, for repeatability.",
    )

    @model_validator(mode="after")
    def _fractions_leave_a_test_set(self) -> "SplitConfig":
        if self.train_fraction + self.val_fraction >= 1.0:
            raise ValueError(
                f"train_fraction + val_fraction = "
                f"{self.train_fraction + self.val_fraction:.2f} leaves no test "
                "set; they must sum below 1.0"
            )
        return self


class TrainingConfig(Strict):
    """Optimisation settings for Phase 6 (Colab)."""

    batch_size: int = Field(default=8, gt=0)
    epochs: int = Field(default=50, gt=0)
    learning_rate: float = Field(default=3e-4, gt=0.0)
    weight_decay: float = Field(default=1e-4, ge=0.0)
    num_workers: int = Field(default=2, ge=0)
    seed: int = Field(default=0)
    class_weights: list[float] | None = Field(
        default=None,
        description=(
            "Per-class loss weights, or null for unweighted. Terrain shadow "
            "and snow are rare relative to land, and an unweighted loss can "
            "reach a low value while never predicting them -- which is the "
            "failure Section 7.5's per-class metrics exist to expose. Set "
            "deliberately and report that it was set."
        ),
    )
    early_stopping_patience: int = Field(
        default=10,
        ge=0,
        description="Epochs without validation improvement before stopping; 0 disables.",
    )
    monitor_metric: Literal["macro_iou", "water_iou", "val_loss"] = Field(
        default="macro_iou",
        description=(
            "What early stopping and checkpointing follow. Never overall "
            "accuracy: Section 7.5 forbids relying on it, and a model that "
            "never predicts shadow can still score highly on it."
        ),
    )


class DatasetSourceConfig(Strict):
    """One external dataset and how its labels map onto our classes.

    ``label_map`` is the mapping the brief requires to be documented. Keys are
    the source dataset's own label values as strings; values are our class
    integers, or null to ignore those pixels.
    """

    enabled: bool = False
    root: str | None = Field(
        default=None,
        description="Local directory holding the downloaded dataset.",
    )
    label_map: dict[str, int | None] = Field(default_factory=dict)
    notes: str | None = None


class ModelsConfig(Strict):
    """Phase 6: dataset building, training and evaluation.

    The channel stack is configurable here, as Section 7.5 requires, and is
    the single source of truth for a model's input width: a model built with a
    different ``in_channels`` than the stack length is a silent mismatch that
    only shows up as a shape error mid-training.
    """

    classes: list[str] = Field(
        default=[
            "background",
            "water",
            "landslide",
            "terrain_shadow",
            "snow_ice",
        ],
        min_length=2,
        description=(
            "Class names in label order, so index == integer label. Section "
            "7.5 fixes these five; the names are configurable for reporting, "
            "the order is not safe to change once patches exist."
        ),
    )
    ignore_index: int = Field(
        default=255,
        ge=0,
        description="Label value excluded from loss and from every metric.",
    )
    channels: list[str] = Field(
        default=[
            "S2_B2", "S2_B3", "S2_B4", "S2_B8", "S2_B11", "S2_B12",
            "NDWI", "MNDWI", "NDVI",
            "S1_VV", "S1_VH",
            "DEM", "SLOPE", "ILLUMINATION", "TERRAIN_SHADOW",
        ],
        min_length=1,
        description=(
            "The input stack, in order. Section 7.5 lists exactly these. A "
            "channel named here must be produced by the patch builder, and "
            "the model's in_channels is len(channels)."
        ),
    )
    normalisation: Literal["per_channel_zscore", "none"] = Field(
        default="per_channel_zscore",
        description=(
            "How to scale the input channels. This stack spans four orders of "
            "magnitude -- reflectance near 0.2, indices at +/-1, slope 0-90 "
            "and DEM in the THOUSANDS -- and fed raw to the first "
            "convolution the DEM channel dominates and the network collapses "
            "to the majority class. Measured on real Landslide4Sense data: "
            "landslide IoU 0.0 from both models, with bit-identical metrics. "
            "On synthetic data at realistic scales, standardisation alone "
            "took landslide IoU from 0.127 to 0.769 with nothing else "
            "changed. Statistics are computed from the TRAINING split only "
            "and stored in the checkpoint, so inference applies exactly what "
            "training saw. 'none' is offered for data already scaled."
        ),
    )
    patch: PatchConfig = PatchConfig()
    split: SplitConfig = SplitConfig()
    training: TrainingConfig = TrainingConfig()
    baseline_encoder: str = Field(
        default="resnet34",
        description=(
            "Encoder for the segmentation_models_pytorch baseline the brief "
            "names. Note the controlled ablation is models.attention_unet."
            "plain_unet, which differs from the Attention U-Net only in the "
            "gates; an smp model differs in many ways at once."
        ),
    )
    baseline_encoder_weights: str | None = Field(
        default=None,
        description=(
            "Pretrained weights for the smp encoder, or null for random init. "
            "ImageNet weights expect 3 RGB channels; with a 15-channel stack "
            "smp adapts the first convolution, so the transfer is partial and "
            "should be reported if used."
        ),
    )
    sources: dict[str, DatasetSourceConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ignore_index_is_not_a_class(self) -> "ModelsConfig":
        if self.ignore_index < len(self.classes):
            raise ValueError(
                f"ignore_index {self.ignore_index} collides with class "
                f"{self.classes[self.ignore_index]!r}: ignored pixels would be "
                "trained on as that class"
            )
        return self

    @model_validator(mode="after")
    def _stride_does_not_exceed_patch(self) -> "ModelsConfig":
        if self.patch.stride_px > self.patch.size_px:
            raise ValueError(
                f"stride_px {self.patch.stride_px} exceeds size_px "
                f"{self.patch.size_px}, which would leave unlabelled gaps "
                "between patches"
            )
        return self

    @property
    def in_channels(self) -> int:
        """Model input width implied by the configured stack."""
        return len(self.channels)

    @property
    def num_classes(self) -> int:
        return len(self.classes)


# --------------------------------------------------------------------------- #
# Paths and logging
# --------------------------------------------------------------------------- #


class PathsConfig(Strict):
    """Directories, relative to the repository root.

    ``data/`` and ``outputs/`` are gitignored (brief, Section 11).
    """

    data: Path = Path("data")
    raw: Path = Path("data/raw")
    processed: Path = Path("data/processed")
    training: Path = Path("data/training")
    validation: Path = Path("data/validation")
    outputs: Path = Path("outputs")
    maps: Path = Path("outputs/maps")
    figures: Path = Path("outputs/figures")
    reports: Path = Path("outputs/reports")
    logs: Path = Path("outputs/logs")

    @field_validator("*")
    @classmethod
    def _relative(cls, v: Path) -> Path:
        if v.is_absolute():
            raise ValueError(
                f"paths must be relative to the repository root, got absolute {v}"
            )
        return v

    def absolute(self, root: Path) -> dict[str, Path]:
        """All configured directories resolved against ``root``."""
        return {
            name: (Path(root) / getattr(self, name)).resolve()
            for name in type(self).model_fields
        }


class LoggingConfig(Strict):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    file_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG"
    to_console: bool = True
    to_file: bool = True
    format: str = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
    date_format: str = "%Y-%m-%dT%H:%M:%S"


# --------------------------------------------------------------------------- #
# Project
# --------------------------------------------------------------------------- #

# Brief, Section 9: this exact text must accompany every warning and report.
REQUIRED_DISCLAIMER_PHRASE = "Not an official warning"


class ProjectConfig(Strict):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    disclaimer: str = Field(
        min_length=1,
        description=(
            "Carried by every warning and report (brief, Section 9). Single-sourced "
            "here so it cannot drift between the dashboard and the PDF reports."
        ),
    )

    @field_validator("disclaimer")
    @classmethod
    def _not_weakened(cls, v: str) -> str:
        # Integrity guard: the disclaimer is a hard requirement of the brief, so
        # it must not be quietly softened by editing config.yaml.
        if REQUIRED_DISCLAIMER_PHRASE.lower() not in v.lower():
            raise ValueError(
                f"disclaimer must contain {REQUIRED_DISCLAIMER_PHRASE!r} "
                "(project brief, Section 9)"
            )
        return v


# --------------------------------------------------------------------------- #
# Root
# --------------------------------------------------------------------------- #


class Config(Strict):
    project: ProjectConfig
    paths: PathsConfig
    aoi: AOIConfig
    dates: DatesConfig
    gee: GEEConfig
    acquisition: AcquisitionConfig
    preprocessing: PreprocessingConfig
    detection: DetectionConfig = DetectionConfig()
    analysis: AnalysisConfig = AnalysisConfig()
    models: ModelsConfig = ModelsConfig()
    logging: LoggingConfig = LoggingConfig()

    @property
    def aoi_centroid(self) -> tuple[float, float] | None:
        """(lon, lat) for bbox/point AOIs; ``None`` for a GeoJSON AOI.

        A GeoJSON centroid requires reading the file, which is the job of
        ``utils.io.read_geojson_geometry`` -- the schema itself stays I/O-free.
        """
        if isinstance(self.aoi, GeoJSONAOI):
            return None
        return self.aoi.centroid
