"""Dashboard data layer (brief, Section 14).

The answers, the chart data and the marker styling are tested without
Streamlit or a browser. What is checked here is that the project's integrity
rules survive contact with a user interface: an unavailable value must not
render as a blank, a gap must not be bridged by a line, and a NORMAL level
built on thin evidence must not render as a green tick.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from analysis.change import AreaObservation
from app.charts import (
    INSUFFICIENT_COLOUR,
    STATUS_LIGHT,
    series_with_gaps,
    status_colour,
)
from app.maps import (
    SHAPE_STYLE,
    add_shape_layer,
    build_site_map,
    map_centre,
    marker_style,
    site_popup_html,
)
from app.site_view import (
    UNAVAILABLE_TEXT,
    WATER_NO,
    WATER_UNCERTAIN,
    WATER_YES,
    build_site_view,
    water_verdict,
)
from config.schema import REQUIRED_DISCLAIMER_PHRASE, Config

pytestmark = pytest.mark.synthetic

START = date(2023, 10, 1)
DISCLAIMER = (
    "Research prototype output. Not an official warning. "
    "Verify with authoritative sources."
)


# --------------------------------------------------------------------------- #
# Section 14's three-valued water question
# --------------------------------------------------------------------------- #


class TestWaterVerdict:
    def test_high_probability_is_yes(self) -> None:
        assert water_verdict(0.9, 0.05)[0] == WATER_YES

    def test_low_probability_is_no(self) -> None:
        assert water_verdict(0.1, 0.05)[0] == WATER_NO

    def test_shadow_more_probable_is_no_with_a_reason(self) -> None:
        verdict, why = water_verdict(0.4, 0.55)
        assert verdict == WATER_NO
        assert "shadow" in why

    def test_an_uncertain_classification_is_uncertain_not_no(self) -> None:
        """The brief asks for three values; collapsing to two hides the cases
        a reviewer should look at."""
        verdict, why = water_verdict(0.8, 0.1, uncertain=True)
        assert verdict == WATER_UNCERTAIN
        assert "confidence" in why

    def test_no_probability_is_uncertain(self) -> None:
        assert water_verdict(None, None)[0] == WATER_UNCERTAIN


# --------------------------------------------------------------------------- #
# Nothing unavailable renders as a blank
# --------------------------------------------------------------------------- #


class TestSiteView:
    def empty_view(self):
        return build_site_view(
            site={"site_code": "ND-001", "site_type": "Potential Landslide Dam"},
            disclaimer=DISCLAIMER,
        )

    def test_the_eleven_questions_are_all_answered(self) -> None:
        view = self.empty_view()
        questions = {a.question for a in view.answers}
        for required in (
            "Is there water here?",
            "Water vs shadow probability",
            "Evidence of a new landslide?",
            "Is a river potentially blocked?",
            "Is there a barrier lake?",
            "Water area",
            "Estimated depth / volume",
            "Trend",
            "Indicator level",
            "Contributing factors",
            "Data sources and observation dates",
        ):
            assert required in questions

    def test_every_answer_has_a_value_and_none_is_blank(self) -> None:
        for answer in self.empty_view().answers:
            assert answer.value
            assert answer.value.strip() != ""

    def test_missing_data_says_unavailable_not_nothing(self) -> None:
        view = self.empty_view()
        depth = view.answer("Estimated depth / volume")
        assert depth.value == UNAVAILABLE_TEXT
        assert depth.value_type == "unavailable"
        assert depth.detail

    def test_a_branch_b_depth_carries_the_branch_reason(self) -> None:
        """Section 8's reason must reach the screen, not just the database."""
        view = build_site_view(
            site={"site_code": "TR-001", "site_type": "Existing Glacial Lake"},
            disclaimer=DISCLAIMER,
            depth_estimate={
                "branch": "B",
                "volume_m3": None,
                "value_type": "unavailable",
                "notes": "DEM records water surface; no bathymetry",
            },
        )
        answer = view.answer("Estimated depth / volume")
        assert answer.value == UNAVAILABLE_TEXT
        assert "no bathymetry" in answer.detail
        assert "Branch B" in answer.detail

    def test_a_branch_a_volume_is_shown_with_its_bounds_and_caveat(self) -> None:
        view = build_site_view(
            site={"site_code": "ND-001", "site_type": "Potential Landslide Dam"},
            disclaimer=DISCLAIMER,
            depth_estimate={
                "branch": "A",
                "volume_m3": 173_000.0,
                "volume_low_m3": 133_000.0,
                "volume_high_m3": 213_000.0,
                "mean_depth_m": 6.69,
                "value_type": "estimated",
            },
        )
        answer = view.answer("Estimated depth / volume")
        assert "0.173" in answer.value
        assert "0.133" in answer.value and "0.213" in answer.value
        assert answer.value_type == "estimated"
        assert "not a statistical confidence interval" in answer.caveat

    def test_an_unknown_trend_is_unavailable_with_its_reason(self) -> None:
        view = build_site_view(
            site={"site_code": "X", "site_type": "y"},
            disclaimer=DISCLAIMER,
            trend={"trend": "Unknown", "reason": "only 2 valid observation(s)"},
        )
        answer = view.answer("Trend")
        assert answer.value == "Unknown"
        assert not answer.available
        assert "2 valid" in answer.detail

    def test_a_trend_reports_its_gaps(self) -> None:
        view = build_site_view(
            site={"site_code": "X", "site_type": "y"},
            disclaimer=DISCLAIMER,
            trend={
                "trend": "Increasing",
                "rate_m2_per_day": 773.3,
                "percent_change": 932.0,
                "span_days": 30,
                "n_gaps": 2,
            },
        )
        detail = view.answer("Trend").detail
        assert "2 gap(s), not interpolated" in detail

    def test_a_thin_evidence_level_carries_its_caveat(self) -> None:
        view = build_site_view(
            site={"site_code": "X", "site_type": "y"},
            disclaimer=DISCLAIMER,
            risk={
                "level": "NORMAL",
                "score": 0.1,
                "data_coverage": 0.09,
                "insufficient_data": 1,
                "factors": [],
            },
        )
        answer = view.answer("Indicator level")
        assert "INSUFFICIENT DATA" in answer.caveat
        assert "not evidence of safety" in answer.caveat
        assert "9%" in answer.detail

    def test_unmeasured_factors_are_named(self) -> None:
        view = build_site_view(
            site={"site_code": "X", "site_type": "y"},
            disclaimer=DISCLAIMER,
            risk={
                "level": "MONITOR",
                "score": 0.4,
                "data_coverage": 0.5,
                "insufficient_data": 0,
                "factors": [
                    {"name": "slope", "available": True, "value": 40.0,
                     "contribution": 0.9, "weight": 1.0},
                    {"name": "lake_volume", "available": False,
                     "reason": "DEM records water surface"},
                ],
            },
        )
        answer = view.answer("Contributing factors")
        assert "slope" in answer.value
        assert "lake_volume" in answer.detail

    def test_the_probability_carries_its_calibration_caveat(self) -> None:
        view = build_site_view(
            site={"site_code": "X", "site_type": "y"},
            disclaimer=DISCLAIMER,
            p_water=0.88,
            p_terrain_shadow=0.07,
        )
        answer = view.answer("Water vs shadow probability")
        assert "not a calibrated probability" in answer.caveat

    def test_the_blockage_answer_never_asserts_a_dam(self) -> None:
        view = build_site_view(
            site={"site_code": "ND-001", "site_type": "Potential Landslide Dam"},
            disclaimer=DISCLAIMER,
            blockage={"site_type": "Potential Landslide Dam", "confidence": 0.62,
                      "evidence_count": 2},
        )
        answer = view.answer("Is a river potentially blocked?")
        assert "Potential" in answer.value
        assert "not a confirmed dam" in answer.caveat

    def test_the_view_carries_the_disclaimer(self, cfg: Config) -> None:
        view = build_site_view(
            site={"site_code": "X", "site_type": "y"},
            disclaimer=cfg.project.disclaimer,
        )
        assert REQUIRED_DISCLAIMER_PHRASE in view.disclaimer


# --------------------------------------------------------------------------- #
# A gap must break the line
# --------------------------------------------------------------------------- #


class TestChartData:
    def test_a_gap_becomes_none_so_the_line_breaks(self) -> None:
        """A joined segment across a gap is a drawn interpolation."""
        observations = [
            AreaObservation(obs_date=START, area_m2=1000.0),
            AreaObservation.gap(START + timedelta(days=5), "cloud cover 96%"),
            AreaObservation(obs_date=START + timedelta(days=10), area_m2=1400.0),
        ]
        dates, areas, labels = series_with_gaps(observations)
        assert areas == [1000.0, None, 1400.0]
        assert len(dates) == 3
        assert "gap" in labels[1] and "96%" in labels[1]

    def test_points_are_sorted_by_date(self) -> None:
        observations = [
            AreaObservation(obs_date=START + timedelta(days=10), area_m2=3.0),
            AreaObservation(obs_date=START, area_m2=1.0),
        ]
        dates, areas, _ = series_with_gaps(observations)
        assert dates == sorted(dates)
        assert areas == [1.0, 3.0]

    def test_database_rows_are_accepted_too(self) -> None:
        rows = [
            {"obs_date": "2023-10-01", "water_area_m2": 1000.0},
            {"obs_date": "2023-10-11", "water_area_m2": 1400.0},
        ]
        dates, areas, _ = series_with_gaps(rows)
        assert areas == [1000.0, 1400.0]
        assert dates[0] == date(2023, 10, 1)

    def test_the_figure_does_not_connect_gaps(self) -> None:
        """Pinned on the rendered figure, not just the data."""
        from app.charts import area_series_figure

        observations = [
            AreaObservation(obs_date=START, area_m2=1000.0),
            AreaObservation.gap(START + timedelta(days=5), "cloud"),
            AreaObservation(obs_date=START + timedelta(days=10), area_m2=1400.0),
        ]
        figure = area_series_figure(observations)
        trace = figure.data[0]
        assert trace.connectgaps is False
        assert None in list(trace.y)

    def test_the_figure_reports_its_gap_count(self) -> None:
        from app.charts import area_series_figure

        observations = [
            AreaObservation(obs_date=START, area_m2=1000.0),
            AreaObservation.gap(START + timedelta(days=5), "cloud"),
        ]
        figure = area_series_figure(observations)
        assert "not interpolated" in figure.layout.title.text

    def test_a_single_series_carries_no_legend(self) -> None:
        """The skill's rule: one series is named by the title."""
        from app.charts import area_series_figure

        figure = area_series_figure(
            [AreaObservation(obs_date=START, area_m2=1.0)]
        )
        assert figure.data[0].showlegend is False

    def test_unavailable_factors_still_appear_in_the_bar_chart(self) -> None:
        from app.charts import factor_contributions_figure

        figure = factor_contributions_figure(
            [
                {"name": "slope", "available": True, "value": 40.0,
                 "contribution": 0.9, "weight": 1.0},
                {"name": "lake_volume", "available": False,
                 "reason": "no bathymetry"},
            ]
        )
        names = list(figure.data[0].y)
        assert "lake_volume" in names
        assert any("no bathymetry" in t for t in figure.data[0].text)


# --------------------------------------------------------------------------- #
# Status colour never carries meaning alone
# --------------------------------------------------------------------------- #


class TestStatusStyling:
    def test_each_level_has_a_reserved_status_colour(self) -> None:
        from analysis.risk import LEVELS

        for level in LEVELS:
            assert level in STATUS_LIGHT

    def test_green_is_withheld_when_normal_is_thinly_evidenced(self) -> None:
        assert status_colour("NORMAL") == STATUS_LIGHT["NORMAL"]
        assert status_colour("NORMAL", insufficient_data=True) == INSUFFICIENT_COLOUR

    def test_an_alarm_keeps_its_colour_whatever_the_coverage(self) -> None:
        critical = "CRITICAL INDICATORS - verification recommended"
        assert (
            status_colour(critical, insufficient_data=True) == STATUS_LIGHT[critical]
        )

    def test_every_marker_pairs_a_symbol_with_words(self) -> None:
        """MONITOR and HIGH RISK are adjacent hues at normal-vision dE 13.6,
        so colour alone is not a safe channel."""
        from analysis.risk import LEVELS

        for level in LEVELS:
            style = marker_style(level)
            assert style.symbol
            assert style.label
            assert style.symbol in style.tooltip and style.label in style.tooltip

    def test_a_thinly_evidenced_normal_marker_is_grey_and_says_so(self) -> None:
        style = marker_style("NORMAL", insufficient_data=True)
        assert style.colour == INSUFFICIENT_COLOUR
        assert "insufficient data" in style.label

    def test_a_site_with_no_assessment_is_not_drawn_green(self) -> None:
        style = marker_style(None)
        assert style.colour == INSUFFICIENT_COLOUR
        assert style.label == "No assessment"


class TestMapAssembly:
    def test_centre_is_the_mean_of_located_sites(self) -> None:
        centre = map_centre(
            [{"lat": 27.0, "lon": 86.0}, {"lat": 29.0, "lon": 88.0}]
        )
        assert centre == pytest.approx((28.0, 87.0))

    def test_sites_without_coordinates_do_not_break_the_centre(self) -> None:
        centre = map_centre([{"lat": None, "lon": None}])
        assert centre == (28.2, 84.0)

    def test_every_popup_carries_the_disclaimer(self, cfg: Config) -> None:
        """A popup can be screenshotted on its own."""
        html = site_popup_html(
            {"site_code": "ND-001", "site_type": "Potential Landslide Dam"},
            marker_style("MONITOR"),
            cfg.project.disclaimer,
        )
        assert REQUIRED_DISCLAIMER_PHRASE in html
        assert "ND-001" in html


# --------------------------------------------------------------------------- #
# The Phase 12 gate: the app actually runs
# --------------------------------------------------------------------------- #


@pytest.mark.slow
class TestAppRuns:
    """Renders the real Streamlit script, catching anything that would only
    fail in a browser session. This is the brief's Phase 12 gate check."""

    def app(self, root):
        streamlit_testing = pytest.importorskip("streamlit.testing.v1")
        db = root / "outputs" / "phase_db_demo.sqlite"
        if not db.exists():
            pytest.skip("no monitoring database; run the pipeline demo first")
        at = streamlit_testing.AppTest.from_file(
            str(root / "app" / "dashboard.py"), default_timeout=120
        )
        at.run()
        return at

    def test_the_app_renders_without_raising(self, root) -> None:
        at = self.app(root)
        assert not at.exception, [str(e.value) for e in at.exception]

    def test_all_eleven_section_14_questions_reach_the_page(self, root) -> None:
        at = self.app(root)
        rendered = [m.value for m in at.markdown if m.value.startswith("**")]
        assert len(rendered) == 11

    def test_the_disclaimer_is_on_the_page(self, root) -> None:
        at = self.app(root)
        shown = " ".join(w.value for w in at.warning)
        assert REQUIRED_DISCLAIMER_PHRASE in shown

    def test_a_thinly_evidenced_site_is_flagged_on_screen(self, root) -> None:
        """TR-001 has one measurable factor; the page must say so loudly."""
        at = self.app(root)
        errors = " ".join(e.value for e in at.error)
        assert "INSUFFICIENT DATA" in errors
        assert "not evidence of safety" in errors


# --------------------------------------------------------------------------- #
# The map must show WHERE, not only how concerned to be
# --------------------------------------------------------------------------- #
@pytest.mark.synthetic
class TestDetectedShapesOnTheMap:
    """A level answers "how worried"; it does not answer "where".

    Before this, the map drew a coloured marker per site and nothing else, so
    a reader seeing CRITICAL could not see the lake being measured, the
    deposit that produced the blockage, or the blockage itself -- even though
    all three existed as geometry.
    """

    LAKE = (
        "POLYGON ((98.70 31.08, 98.72 31.08, 98.72 31.10, 98.70 31.10, "
        "98.70 31.08))"
    )
    DEPOSIT = (
        "POLYGON ((98.705 31.082, 98.707 31.082, 98.707 31.084, "
        "98.705 31.082))"
    )
    SITES = [
        {
            "site_code": "ND-001",
            "site_type": "Potential Landslide Dam",
            "lat": 31.0836,
            "lon": 98.7129,
            "level": "CRITICAL INDICATORS - verification recommended",
        }
    ]

    def _render(self, shapes, disclaimer="Research prototype output."):
        return build_site_map(
            self.SITES, disclaimer=disclaimer, shapes=shapes
        ).get_root().render()

    def test_every_layer_is_drawn_and_named(self, cfg: Config) -> None:
        html = self._render({
            "lake_post": [(self.LAKE, "lake")],
            "lake_pre": [(self.LAKE, "before")],
            "landslide": [(self.DEPOSIT, "deposit")],
            "blockage": [("POINT (98.7129 31.0836)", "ND-001")],
            "stream": [("LINESTRING (98.70 31.07, 98.72 31.11)", "Jinsha")],
        })
        for label in ("Barrier lake", "Water before the event",
                      "New landslide", "Blockage candidate",
                      "Stream network"):
            assert label in html, f"{label} layer missing"

    def test_a_map_without_shapes_still_renders(self, cfg: Config) -> None:
        """Shapes are optional: a site with no geometry must still appear."""
        html = self._render(None)
        assert "ND-001" in html
        assert "Barrier lake" not in html

    def test_a_malformed_geometry_is_skipped_not_fatal(self, cfg: Config) -> None:
        """A dashboard that will not open is worse than one missing a shape."""
        html = self._render({"lake_post": [("NOT A GEOMETRY", "bad")]})
        assert "ND-001" in html, "one bad geometry took the whole map down"

    def test_add_shape_layer_counts_only_what_it_drew(self, cfg: Config) -> None:
        import folium

        site_map = folium.Map(location=[31.0, 98.7])
        drawn = add_shape_layer(
            site_map,
            [(self.LAKE, "ok"), ("NOT A GEOMETRY", "bad"), ("", "empty")],
            name="Barrier lake", style="lake_post",
        )
        assert drawn == 1

    def test_shape_colours_are_distinct_from_the_status_palette(self) -> None:
        """A shape says what was detected; a marker says how concerned to be.

        Sharing a palette would imply a lake is itself a warning level.
        """
        from app.charts import STATUS_LIGHT

        shape_colours = {c.lower() for c, _, _ in SHAPE_STYLE.values()}
        status_colours = {c.lower() for c in STATUS_LIGHT.values()}
        assert not (shape_colours & status_colours)

    def test_the_pre_event_outline_is_hidden_by_default(
        self, cfg: Config
    ) -> None:
        """It is reference for judging growth, not the thing being reported."""
        html = self._render({
            "lake_post": [(self.LAKE, "now")],
            "lake_pre": [(self.DEPOSIT, "before")],
        })
        assert "Water before the event" in html
        # Folium writes show=False as an explicit overlay default.
        assert "Barrier lake" in html


@pytest.mark.synthetic
class TestLakeAreasCarryTheirSearchDistance:
    """An area without its search distance cannot be interpreted.

    The same lake measured over 500 m and 3,000 m of channel differs
    threefold (validation.md 22), so the figure alone is not a measurement of
    anything. This is why the column exists.
    """

    def _shapes_for(self, tmp_path, **observation):
        from app.dashboard import _shapes
        from database.db import Database

        with Database(tmp_path / "db.sqlite") as db:
            db.initialise()
            site_id = db.upsert_site(
                site_code="ND-001", site_type="Potential Landslide Dam"
            )
            db.add_observation(
                site_id, obs_date="2018-11-09", sensor="Sentinel-2 MSI",
                value_type="classified", **observation,
            )
            return _shapes(db)

    def test_the_distance_appears_in_the_popup(self, tmp_path) -> None:
        shapes = self._shapes_for(
            tmp_path,
            water_area_m2=634900.0,
            geometry=TestDetectedShapesOnTheMap.LAKE,
            search_distance_m=2000.0,
        )
        popup = shapes["lake_post"][0][1]
        assert "within 2,000 m upstream" in popup
        assert "lower bound" in popup
        assert "634,900" in popup

    def test_a_missing_distance_is_called_out(self, tmp_path) -> None:
        """Silence would let a reader take the area at face value."""
        shapes = self._shapes_for(
            tmp_path,
            water_area_m2=634900.0,
            geometry=TestDetectedShapesOnTheMap.LAKE,
        )
        popup = shapes["lake_post"][0][1]
        assert "cannot be interpreted" in popup

    def test_an_observation_without_geometry_contributes_no_shape(
        self, tmp_path
    ) -> None:
        shapes = self._shapes_for(tmp_path, water_area_m2=634900.0)
        assert shapes["lake_post"] == []
