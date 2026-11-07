"""Terrain-aware shadow rejection: the project's core contribution.

Brief, Section 7.3. Combines the optical indices, the terrain-shadow mask,
illumination, SAR backscatter, the SAR layover/shadow mask and multi-temporal
persistence into per-pixel ``p_water``, ``p_terrain_shadow`` and ``p_land``,
and reports how much false water this removes relative to the index-only mask
built in Phase 3.

Design
------
**Transparent additive evidence.** Each piece of evidence is mapped by a soft
membership to a signed support in ``[-1, +1]``, multiplied by a configured
weight, and summed into a per-class score. **Land is the reference class with
a score of zero**, so water and terrain shadow must each earn evidence above
it. Probabilities are a softmax over the three scores. Every factor's
contribution is retained, so any verdict can be traced to the evidence that
produced it rather than emerging from a fitted black box.

**What ``p_terrain_shadow`` means.** It is the probability that shadow leaves
the surface material *indeterminate* -- the brief's Section 7.5 class 3, which
the labelling rule reserves for "terrain shadow (material indeterminate)",
noting that "a landslide scar or lake inside shadow keeps its material class if
it is identifiable". It is **not** the probability that a pixel is
geometrically shadowed: the Phase 2 mask already states that deterministically,
and water and shadow are not mutually exclusive -- a lake inside a shadow is
still a lake.

That reading is what makes the three Section 7.3 rules fall out of the fusion
instead of being special-cased. The shadow score is discounted by
``material_determinacy_weight`` times the strength of *determinate* material
evidence, which is chiefly SAR, because SAR is illumination-independent and so
is exactly the evidence that resolves a shadow ambiguity:

===================================================  ==========================
Section 7.3 rule                                     How it arises here
===================================================  ==========================
dark optical + terrain shadow + SAR not water-like   SAR support is negative,
                                                     so water loses; the shadow
                                                     score stands -> shadow
dark optical + terrain shadow + SAR water-like       SAR support is positive
(and not in SAR shadow/layover)                      *and* determinate, which
                                                     both lifts water and
                                                     discounts shadow -> water
SAR water-like but inside SAR layover/shadow         the SAR term is gated out
                                                     entirely, so nothing is
                                                     determinate; the verdict
                                                     rests on optical evidence
                                                     and the pixel is flagged
                                                     ``sar_unreliable``
===================================================  ==========================

Two findings from earlier phases constrain what may be used (docs/methods.md):

- **§2.4** -- observed brightness does not indicate shadow in these
  snow-dominated scenes (``r = -0.18``; shadowed pixels are *brighter*). So
  darkness is never evidence of shadow here. The shadow evidence is geometric:
  the Phase 2 cast/self-shadow mask and the illumination layer.
- **§3.5** -- single-scene SAR amplitude thresholding fails in this terrain,
  which is why ``weights.sar_backscatter`` is modest and why the layover/shadow
  gate matters.

References
----------
Chen, F., Zhang, M., Guo, H., Allen, S., Kargel, J. S., Haritashya, U. K., &
    Watson, C. S. (2021). Annual 30 m dataset for glacial lakes in High
    Mountain Asia from 2008 to 2017. *Earth System Science Data*, 13(2),
    741-766. doi:10.5194/essd-13-741-2021 -- topographic shadows masked using
    slope > 10 deg and shaded relief < 0.25.
Hall, D. K., Riggs, G. A., & Salomonson, V. V. (1995). Development of methods
    for mapping global snow cover using MODIS data. *Remote Sensing of
    Environment*, 54(2), 127-140. doi:10.1016/0034-4257(95)00137-P
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from config.schema import Config

log = get_logger(__name__)

# Class codes. These match the segmentation classes of the brief, Section 7.5
# (0 background/land, 1 water, 2 landslide/bare debris, 3 terrain shadow,
# 4 snow/ice) so that a Phase 4 map and a Phase 6 prediction can be compared
# without a translation table. 2 and 4 are not produced here.
CLASS_LAND = 0
CLASS_WATER = 1
CLASS_TERRAIN_SHADOW = 3
CLASS_UNCLASSIFIED = -1

CLASS_NAMES = {
    CLASS_LAND: "land",
    CLASS_WATER: "water",
    CLASS_TERRAIN_SHADOW: "terrain_shadow",
    CLASS_UNCLASSIFIED: "unclassified",
}

#: Evidence that supports the water class.
WATER_TERMS = ("water_index", "nir", "slope", "sar_backscatter", "persistence")
#: Evidence that supports the terrain-shadow class.
SHADOW_TERMS = ("illumination", "terrain_shadow_mask")

#: Terms whose evidence is *determinate about surface material* -- it tells you
#: what the surface is, not merely how it is lit -- and how far each is trusted
#: to do so inside a shadow.
#:
#: SAR and persistence count fully. SAR is illumination-independent, so a
#: shadow does not weaken it at all; persistence counts because a pixel reading
#: as water across observations is not material-indeterminate.
#:
#: The optical terms count only partially, at
#: ``membership.optical_determinacy_scale``. NDWI and MNDWI are band *ratios*,
#: in which the illumination factor cancels to first order -- which is why
#: ratio indices are used in topographically complex terrain at all -- so they
#: do retain material information in shadow. Only to first order, though:
#: diffuse skylight is spectrally different from direct beam, so the
#: cancellation is imperfect, and docs/methods.md 2.4 showed that reflectance
#: in these snow-dominated scenes is not governed by direct-beam geometry.
#: Hence a scale below 1, not equal to it.
FULLY_DETERMINATE_TERMS = ("sar_backscatter", "persistence")
PARTLY_DETERMINATE_TERMS = ("water_index", "nir")

#: Terms that constitute an OPTICAL OBSERVATION of the surface.
#:
#: Every rule in Section 7.3 begins "dark **optical** pixel", and its third
#: rule makes SAR that is water-like but unreliable *uncertain*, deferring to
#: optical evidence. The section has no rule for the case where there is no
#: optical observation at all -- and over scene edges and thick cloud that case
#: is common: 40.1% of one real Sentinel-2 scene here.
#:
#: Left to itself the fusion filled that gap by trusting SAR, and reported
#: water at a median 3,822 m on flat high ground where dry snow and ice are
#: equally dark to radar. 88.9% of the pixels it added over the rule-based mask
#: had no optical observation (docs/validation.md 24, Finding 4a).
OPTICAL_TERMS = ("water_index", "nir")


def soft_support(
    values: np.ndarray,
    midpoint: float,
    softness: float,
    *,
    below_is_positive: bool,
) -> np.ndarray:
    """Map values to a signed support in ``[-1, +1]`` through a logistic.

    The support is 0 exactly at ``midpoint``, so a cited mask threshold can be
    used as the crossing point and keep its meaning while yielding a graded
    probability instead of a hard veto. ``softness`` is the scale over which
    the transition happens: at ``midpoint ± softness`` the support is about
    ±0.46, and it saturates within a few multiples.

    Args:
        below_is_positive: whether values *below* ``midpoint`` support the
            class (true for slope, NIR and SAR backscatter; false for a water
            index, where higher means more water-like).
    """
    if softness <= 0.0:
        raise ValueError(f"softness must be positive, got {softness}")

    data = np.asarray(values, dtype=np.float64)
    direction = -1.0 if below_is_positive else 1.0
    # tanh rather than a 0-1 logistic: it is symmetric about the midpoint and
    # already signed, so "no evidence" and "evidence against" stay distinct.
    with np.errstate(over="ignore", invalid="ignore"):
        support = np.tanh(direction * (data - midpoint) / softness)
    return np.where(np.isfinite(data), support, 0.0)


@dataclass
class EvidenceTerm:
    """One named piece of evidence, its support and where it applies.

    ``positive_scale`` makes a term **asymmetric**, which some evidence
    genuinely is. Slope is the case that matters here: steep ground is strong
    evidence *against* standing water, but flat ground is not evidence *for*
    it, because flatness is a necessary condition that most dry land also
    meets. Treating the two directions symmetrically turns every valley floor
    and flat glacier surface into a water candidate. Chen et al. (2021) use
    slope the same way -- as an exclusion criterion, not an inclusion one.
    """

    name: str
    target: str  # "water" or "terrain_shadow"
    weight: float
    support: np.ndarray  # signed, [-1, +1]
    available: np.ndarray  # bool: where this term has anything to say
    positive_scale: float = 1.0

    def effective_support(self) -> np.ndarray:
        """Support after any asymmetry is applied."""
        if self.positive_scale == 1.0:
            return self.support
        return np.where(
            self.support > 0.0, self.support * self.positive_scale, self.support
        )

    def contribution(self) -> np.ndarray:
        """Weighted, signed contribution to :attr:`target`, zero where absent."""
        return np.where(self.available, self.weight * self.effective_support(), 0.0)

    def summary(self) -> dict[str, float]:
        present = self.available
        count = int(np.count_nonzero(present))
        return {
            "weight": float(self.weight),
            "available_fraction": float(present.mean()),
            "mean_support": float(self.support[present].mean()) if count else 0.0,
        }


@dataclass
class FusionResult:
    """Per-pixel water / terrain-shadow / land probabilities and the evidence."""

    p_water: np.ndarray
    p_terrain_shadow: np.ndarray
    p_land: np.ndarray
    classification: np.ndarray
    uncertain: np.ndarray
    valid: np.ndarray
    terms: dict[str, EvidenceTerm] = field(default_factory=dict)
    reasons: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def water(self) -> np.ndarray:
        """Confident water: the water class, excluding uncertain pixels."""
        return (self.classification == CLASS_WATER) & ~self.uncertain

    @property
    def terrain_shadow(self) -> np.ndarray:
        return (self.classification == CLASS_TERRAIN_SHADOW) & ~self.uncertain

    def class_fractions(self) -> dict[str, float]:
        total = int(np.count_nonzero(self.valid))
        if not total:
            return {name: 0.0 for name in CLASS_NAMES.values()}
        return {
            name: float(np.count_nonzero((self.classification == code) & self.valid) / total)
            for code, name in CLASS_NAMES.items()
            if code != CLASS_UNCLASSIFIED
        }

    def explain(self, row: int, col: int) -> dict[str, object]:
        """Why one pixel was classified as it was.

        Returns the class probabilities and every evidence term's signed
        contribution, so a verdict on the dashboard can list its factors
        (brief, Section 9: each warning lists the factors behind it).
        """
        contributions = {
            name: {
                "target": term.target,
                "support": float(term.support[row, col]),
                "weight": float(term.weight),
                "contribution": float(term.contribution()[row, col]),
                "available": bool(term.available[row, col]),
            }
            for name, term in self.terms.items()
        }
        return {
            "classification": CLASS_NAMES[int(self.classification[row, col])],
            "uncertain": bool(self.uncertain[row, col]),
            "p_water": float(self.p_water[row, col]),
            "p_terrain_shadow": float(self.p_terrain_shadow[row, col]),
            "p_land": float(self.p_land[row, col]),
            "factors": contributions,
            "reasons": {
                name: bool(mask[row, col]) for name, mask in self.reasons.items()
            },
        }

    def summary(self) -> str:
        fractions = self.class_fractions()
        valid_count = int(np.count_nonzero(self.valid))
        if not valid_count:
            return "no valid pixels: nothing could be classified"
        return (
            f"water {fractions['water'] * 100:.2f}%, "
            f"terrain shadow {fractions['terrain_shadow'] * 100:.2f}%, "
            f"land {fractions['land'] * 100:.2f}% "
            f"of {valid_count} valid px; "
            f"uncertain {self.uncertain[self.valid].mean() * 100:.2f}%"
        )


def fuse(
    cfg: "Config",
    *,
    water_index: np.ndarray | None = None,
    water_index_threshold: float = 0.0,
    nir_reflectance: np.ndarray | None = None,
    slope_deg: np.ndarray | None = None,
    illumination: np.ndarray | None = None,
    terrain_shadow: np.ndarray | None = None,
    sar_db: np.ndarray | None = None,
    sar_threshold_db: float | None = None,
    sar_unreliable: np.ndarray | None = None,
    persistence: np.ndarray | None = None,
    persistence_observations: int = 0,
    optical_invalid: np.ndarray | None = None,
) -> FusionResult:
    """Fuse the available evidence into per-pixel class probabilities.

    Every input is optional: a run with no SAR scene, or with the optical
    scene wholly clouded, still produces a result from what remains, and
    pixels with no evidence at all are left ``CLASS_UNCLASSIFIED`` rather than
    defaulting to land.

    Args:
        water_index: the index driving the optical rule (MNDWI or NDWI), and
            ``water_index_threshold`` its land/water boundary.
        nir_reflectance: NIR in reflectance units, not stored integers.
        slope_deg, illumination, terrain_shadow: Phase 2 terrain products. The
            shadow mask is geometric; brightness is never used as evidence of
            shadow (docs/methods.md 2.4).
        sar_db: backscatter in dB. ``sar_threshold_db`` defaults to the
            configured membership midpoint, which in turn defaults to the
            threshold Phase 3 derived for the scene.
        sar_unreliable: the SAR layover/shadow mask. Where true the SAR term is
            gated out entirely unless ``trust_sar_in_layover_shadow``.
        persistence: fraction of valid observations reading as water, with
            ``persistence_observations`` the number of observations behind it.
        optical_invalid: cloud, cloud shadow and defective pixels. Terrain
            shadow must not be passed here.

    Returns:
        A :class:`FusionResult`. Probabilities are NaN where nothing is valid.
    """
    settings = cfg.detection.shadow_rejection
    membership = settings.membership
    weights = settings.weights

    shape = _common_shape(
        water_index, nir_reflectance, slope_deg, illumination, terrain_shadow, sar_db
    )
    terms: dict[str, EvidenceTerm] = {}
    reasons: dict[str, np.ndarray] = {}

    optical_ok = np.ones(shape, dtype=bool)
    if optical_invalid is not None:
        optical_ok &= ~np.asarray(optical_invalid, dtype=bool)

    # --- evidence for water ------------------------------------------------ #
    if water_index is not None and weights.water_index > 0.0:
        values = np.asarray(water_index, dtype=np.float64)
        terms["water_index"] = EvidenceTerm(
            name="water_index",
            target="water",
            weight=weights.water_index,
            support=soft_support(
                values,
                water_index_threshold,
                membership.water_index.softness,
                below_is_positive=False,
            ),
            available=np.isfinite(values) & optical_ok,
        )

    if nir_reflectance is not None and weights.nir > 0.0:
        values = np.asarray(nir_reflectance, dtype=np.float64)
        terms["nir"] = EvidenceTerm(
            name="nir",
            target="water",
            weight=weights.nir,
            support=soft_support(
                values,
                membership.nir.water_max_reflectance,
                membership.nir.softness,
                below_is_positive=True,
            ),
            available=np.isfinite(values) & optical_ok,
        )

    if slope_deg is not None and weights.slope > 0.0:
        values = np.asarray(slope_deg, dtype=np.float64)
        terms["slope"] = EvidenceTerm(
            name="slope",
            target="water",
            weight=weights.slope,
            support=soft_support(
                values,
                membership.slope.water_max_deg,
                membership.slope.softness_deg,
                below_is_positive=True,
            ),
            # The DEM is cloud-independent, so slope is available wherever the
            # DEM is -- including under cloud.
            available=np.isfinite(values),
            # Asymmetric: steep ground rules water out, flat ground does not
            # rule it in. See EvidenceTerm and docs/methods.md 4.4.
            positive_scale=membership.slope.flat_support_scale,
        )

    if sar_db is not None and weights.sar_backscatter > 0.0:
        values = np.asarray(sar_db, dtype=np.float64)
        midpoint = (
            membership.sar.water_max_db
            if membership.sar.water_max_db is not None
            else sar_threshold_db
        )
        if midpoint is None:
            log.warning(
                "SAR evidence skipped: no threshold configured and none supplied "
                "by Phase 3 for this scene"
            )
            reasons["sar_no_threshold"] = np.ones(shape, dtype=bool)
        else:
            available = np.isfinite(values)
            if sar_unreliable is not None:
                unreliable = np.asarray(sar_unreliable, dtype=bool)
                reasons["sar_unreliable"] = unreliable
                if not settings.trust_sar_in_layover_shadow:
                    # Brief, Section 7.3: inside layover/shadow the SAR
                    # evidence is not merely weaker, it is uninterpretable, so
                    # it is withdrawn rather than downweighted.
                    available = available & ~unreliable
            terms["sar_backscatter"] = EvidenceTerm(
                name="sar_backscatter",
                target="water",
                weight=weights.sar_backscatter,
                support=soft_support(
                    values,
                    float(midpoint),
                    membership.sar.softness_db,
                    below_is_positive=True,
                ),
                available=available,
            )

    if persistence is not None and weights.persistence > 0.0:
        if persistence_observations < membership.persistence.min_observations:
            log.info(
                "persistence evidence skipped: %d observation(s), fewer than the "
                "%d required",
                persistence_observations,
                membership.persistence.min_observations,
            )
            reasons["persistence_too_few_observations"] = np.ones(shape, dtype=bool)
        else:
            values = np.asarray(persistence, dtype=np.float64)
            terms["persistence"] = EvidenceTerm(
                name="persistence",
                target="water",
                weight=weights.persistence,
                support=soft_support(
                    values,
                    membership.persistence.water_min_fraction,
                    membership.persistence.softness,
                    below_is_positive=False,
                ),
                available=np.isfinite(values),
            )

    # --- evidence for terrain shadow --------------------------------------- #
    # Geometric only. Brightness is never used here (docs/methods.md 2.4).
    if illumination is not None and weights.illumination > 0.0:
        values = np.asarray(illumination, dtype=np.float64)
        # Our illumination is signed cos(incidence); the cited threshold is on
        # shaded relief, which is the same quantity clipped at zero.
        hillshade = np.clip(values, 0.0, 1.0)
        terms["illumination"] = EvidenceTerm(
            name="illumination",
            target="terrain_shadow",
            weight=weights.illumination,
            support=soft_support(
                hillshade,
                membership.illumination.shadow_below,
                membership.illumination.softness,
                below_is_positive=True,
            ),
            available=np.isfinite(values),
        )

    if terrain_shadow is not None and weights.terrain_shadow_mask > 0.0:
        mask = np.asarray(terrain_shadow, dtype=bool)
        terms["terrain_shadow_mask"] = EvidenceTerm(
            name="terrain_shadow_mask",
            target="terrain_shadow",
            weight=weights.terrain_shadow_mask,
            # Binary evidence: +1 inside the mask, -1 outside. The mask was
            # validated at 92.3% agreement against ee.Terrain.hillShadow
            # (docs/methods.md 2.3), so "outside" is informative too.
            support=np.where(mask, 1.0, -1.0),
            available=np.ones(shape, dtype=bool),
        )

    if not terms:
        raise ValueError(
            "no evidence supplied: fuse() needs at least one of water_index, "
            "nir_reflectance, slope_deg, illumination, terrain_shadow, sar_db "
            "or persistence, with a non-zero weight"
        )

    # --- scores ------------------------------------------------------------ #
    score_water = np.zeros(shape, dtype=np.float64)
    score_shadow = np.zeros(shape, dtype=np.float64)
    for term in terms.values():
        if term.target == "water":
            score_water += term.contribution()
        else:
            score_shadow += term.contribution()

    # Determinate material evidence suppresses "shadow, material
    # indeterminate". Only the magnitude matters: SAR saying confidently "not
    # water" determines the material just as much as it saying "water".
    determinacy = np.zeros(shape, dtype=np.float64)
    scales = {name: 1.0 for name in FULLY_DETERMINATE_TERMS}
    scales.update(
        {
            name: membership.optical_determinacy_scale
            for name in PARTLY_DETERMINATE_TERMS
        }
    )
    for name, scale in scales.items():
        term = terms.get(name)
        if term is not None and scale > 0.0:
            determinacy = np.maximum(
                determinacy,
                np.where(term.available, np.abs(term.support) * scale, 0.0),
            )
    score_shadow -= settings.material_determinacy_weight * determinacy

    # Land is the reference class: score zero, no evidence of its own.
    score_land = np.zeros(shape, dtype=np.float64)

    # --- probabilities ----------------------------------------------------- #
    stacked = np.stack([score_land, score_water, score_shadow], axis=0)
    stacked /= settings.temperature
    stacked -= stacked.max(axis=0, keepdims=True)  # softmax, stabilised
    exponentiated = np.exp(stacked)
    probabilities = exponentiated / exponentiated.sum(axis=0, keepdims=True)

    p_land, p_water, p_shadow = probabilities

    # A pixel is valid where at least one term actually applies.
    valid = np.zeros(shape, dtype=bool)
    for term in terms.values():
        valid |= term.available

    codes = np.array([CLASS_LAND, CLASS_WATER, CLASS_TERRAIN_SHADOW])
    classification = codes[np.argmax(probabilities, axis=0)].astype(np.int16)
    classification = np.where(valid, classification, CLASS_UNCLASSIFIED).astype(np.int16)

    top = probabilities.max(axis=0)
    uncertain = (top < settings.min_confidence) & valid

    reasons["low_confidence"] = uncertain.copy()
    reasons["no_evidence"] = ~valid

    # Section 7.3's missing case: water asserted with NO optical observation.
    #
    # Being "valid" only requires one term, and the DEM-derived and SAR terms
    # apply everywhere, so a pixel with no usable optical data still gets a
    # verdict -- from radar, over which dry snow, smooth ice and water are all
    # dark. Such a pixel is marked uncertain rather than classified, which is
    # how the section treats SAR evidence it cannot corroborate.
    optical_available = np.zeros(shape, dtype=bool)
    for name in OPTICAL_TERMS:
        term = terms.get(name)
        if term is not None:
            optical_available |= term.available

    if settings.require_optical_for_water:
        sar_only_water = (
            (classification == CLASS_WATER) & valid & ~optical_available
        )
        reasons["water_without_optical"] = sar_only_water
        uncertain = uncertain | sar_only_water
        if sar_only_water.any():
            log.info(
                "%d pixel(s) called water on non-optical evidence alone are "
                "marked uncertain: radar cannot separate water from dry snow "
                "or smooth ice, and Section 7.3's rules all presuppose an "
                "optical observation",
                int(sar_only_water.sum()),
            )
    else:
        reasons["water_without_optical"] = (
            (classification == CLASS_WATER) & valid & ~optical_available
        )
    if "sar_unreliable" in reasons:
        # Section 7.3's "uncertain" case: SAR looked water-like but sits inside
        # the layover/shadow mask, so the verdict rests on optical evidence.
        sar_term = terms.get("sar_backscatter")
        if sar_term is not None:
            deferred = reasons["sar_unreliable"] & ~sar_term.available & valid
            reasons["sar_deferred_to_optical"] = deferred

    for array in (p_water, p_shadow, p_land):
        array[~valid] = np.nan

    result = FusionResult(
        p_water=p_water,
        p_terrain_shadow=p_shadow,
        p_land=p_land,
        classification=classification,
        uncertain=uncertain,
        valid=valid,
        terms=terms,
        reasons=reasons,
    )
    log.info("shadow-rejection fusion -- %s", result.summary())
    log.info("  evidence used: %s", ", ".join(sorted(terms)))
    return result


def false_water_reduction(
    baseline: np.ndarray,
    result: FusionResult,
    *,
    reference_water: np.ndarray | None = None,
    pixel_area_m2: float = 100.0,
) -> dict[str, float | None]:
    """Quantify the reduction against the index-only mask (brief, Section 7.3).

    Args:
        baseline: the Phase 3 index-only water mask
            (``WaterEvidence.pre_screen_water``).
        reference_water: an independent observation of real water, used to
            report what the reduction *cost*. Without it the removal count
            alone would be meaningless -- a mask that removes everything
            removes all false water too.

    Returns:
        Counts, areas and, where a reference is supplied, the retention of
        known water. ``None`` for retention when no reference is given.
    """
    baseline = np.asarray(baseline, dtype=bool) & result.valid
    retained = result.water & baseline
    removed = baseline & ~result.water
    added = result.water & ~baseline

    report: dict[str, float | None] = {
        "baseline_px": float(np.count_nonzero(baseline)),
        "baseline_area_km2": float(np.count_nonzero(baseline) * pixel_area_m2 / 1e6),
        "fused_px": float(np.count_nonzero(result.water)),
        "fused_area_km2": float(np.count_nonzero(result.water) * pixel_area_m2 / 1e6),
        "retained_px": float(np.count_nonzero(retained)),
        "removed_px": float(np.count_nonzero(removed)),
        "removed_area_km2": float(np.count_nonzero(removed) * pixel_area_m2 / 1e6),
        "added_px": float(np.count_nonzero(added)),
        "removed_fraction_of_baseline": (
            float(np.count_nonzero(removed) / np.count_nonzero(baseline))
            if np.any(baseline)
            else 0.0
        ),
    }

    # Of what was removed, how much the fusion attributes to shadow rather than
    # simply dropping.
    report["removed_as_terrain_shadow_px"] = float(
        np.count_nonzero(removed & (result.classification == CLASS_TERRAIN_SHADOW))
    )
    report["removed_as_land_px"] = float(
        np.count_nonzero(removed & (result.classification == CLASS_LAND))
    )
    report["removed_as_uncertain_px"] = float(np.count_nonzero(removed & result.uncertain))

    if reference_water is None:
        report["reference_retained_fraction"] = None
        report["reference_px"] = None
    else:
        reference = np.asarray(reference_water, dtype=bool) & result.valid
        reference_count = int(np.count_nonzero(reference))
        report["reference_px"] = float(reference_count)
        report["reference_retained_fraction"] = (
            float(np.count_nonzero(result.water & reference) / reference_count)
            if reference_count
            else None
        )
        report["reference_retained_fraction_baseline"] = (
            float(np.count_nonzero(baseline & reference) / reference_count)
            if reference_count
            else None
        )

    log.info(
        "false-water reduction: %d -> %d px (%.1f%% of the index-only mask "
        "removed); known water retained: %s",
        int(report["baseline_px"]),
        int(report["fused_px"]),
        100.0 * report["removed_fraction_of_baseline"],
        (
            f"{report['reference_retained_fraction']:.1%}"
            if report["reference_retained_fraction"] is not None
            else "no reference supplied"
        ),
    )
    return report


def _common_shape(*arrays: np.ndarray | None) -> tuple[int, int]:
    """The shape shared by every supplied array, or an error naming the clash."""
    shapes = {np.asarray(a).shape for a in arrays if a is not None}
    if not shapes:
        raise ValueError("no evidence arrays supplied")
    if len(shapes) > 1:
        raise ValueError(f"evidence arrays have mismatched shapes: {sorted(shapes)}")
    shape = shapes.pop()
    if len(shape) != 2:
        raise ValueError(f"evidence arrays must be 2-D, got shape {shape}")
    return shape  # type: ignore[return-value]
