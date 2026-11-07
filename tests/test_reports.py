"""Report generation (brief, Phase 13).

The HTML is always produced by Jinja2 alone, so most of this runs anywhere.
The PDF tests are marked ``slow`` and skip where no engine is available --
which on this machine means headless Edge, because WeasyPrint cannot load its
native libraries on Windows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config.schema import REQUIRED_DISCLAIMER_PHRASE, Config
from database.db import Database
from reports.generate import (
    NoPDFEngineError,
    find_chromium,
    generate_site_report,
    html_to_pdf,
    render_site_html,
    site_report_from_database,
    weasyprint_available,
)

pytestmark = pytest.mark.synthetic

SITE = {"site_code": "ND-001", "site_type": "Potential Landslide Dam"}


def answers() -> list[dict]:
    return [
        {
            "question": "Is there water here?",
            "value": "Yes",
            "value_type": "classified",
            "detail": None,
            "caveat": None,
        },
        {
            "question": "Estimated depth / volume",
            "value": "Unavailable",
            "value_type": "unavailable",
            "detail": "Branch B: DEM records water surface; no bathymetry",
            "caveat": None,
        },
    ]


def render(cfg: Config, **overrides) -> str:
    kwargs = dict(
        site=SITE,
        answers=answers(),
        disclaimer=cfg.project.disclaimer,
        project_name=cfg.project.name,
        project_version=cfg.project.version,
        level="MONITOR",
    )
    kwargs.update(overrides)
    return render_site_html(**kwargs)


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #


class TestHTML:
    def test_the_disclaimer_appears(self, cfg: Config) -> None:
        assert REQUIRED_DISCLAIMER_PHRASE in render(cfg)

    def test_the_disclaimer_appears_more_than_once(self, cfg: Config) -> None:
        """Top, bottom and the page footer: a cropped page keeps it."""
        assert render(cfg).count(REQUIRED_DISCLAIMER_PHRASE) >= 2

    def test_every_answer_reaches_the_page(self, cfg: Config) -> None:
        html = render(cfg)
        for answer in answers():
            assert answer["question"] in html
            assert answer["value"] in html

    def test_value_types_are_shown(self, cfg: Config) -> None:
        """Section 14: which values are observed, classified, estimated..."""
        html = render(cfg)
        assert "classified" in html
        assert "unavailable" in html

    def test_an_unavailable_value_keeps_its_reason(self, cfg: Config) -> None:
        assert "no bathymetry" in render(cfg)

    def test_the_site_code_and_type_are_in_the_heading(self, cfg: Config) -> None:
        html = render(cfg)
        assert "ND-001" in html
        assert "Potential Landslide Dam" in html

    def test_green_is_withheld_for_a_thinly_evidenced_normal(
        self, cfg: Config
    ) -> None:
        """The same rule as the dashboard: a report is read alone too."""
        thin = render(cfg, level="NORMAL", insufficient_data=True)
        confident = render(cfg, level="NORMAL", insufficient_data=False)
        assert "#8a8a85" in thin and "#0ca30c" not in thin
        assert "#0ca30c" in confident

    def test_an_alarm_keeps_its_colour(self, cfg: Config) -> None:
        critical = render(
            cfg,
            level="CRITICAL INDICATORS - verification recommended",
            insufficient_data=True,
        )
        assert "#d03b3b" in critical

    def test_insufficient_data_is_stated_in_words(self, cfg: Config) -> None:
        html = render(cfg, level="NORMAL", insufficient_data=True)
        assert "INSUFFICIENT DATA" in html
        assert "not evidence of safety" in html

    def test_factors_are_listed_with_the_unmeasured_named(self, cfg: Config) -> None:
        html = render(
            cfg,
            factors=[
                {"name": "slope", "available": True, "value": 41.0,
                 "weight": 1.0, "contribution": 0.87},
                {"name": "lake_volume", "available": False,
                 "reason": "DEM records water surface"},
            ],
        )
        assert "slope" in html
        assert "lake_volume" in html
        assert "DEM records water surface" in html

    def test_a_gap_in_the_observation_table_says_so(self, cfg: Config) -> None:
        html = render(
            cfg,
            observations=[
                {"obs_date": "2023-10-19", "sensor": "Sentinel-2",
                 "water_area_m2": 1_600_500.0, "value_type": "derived"},
                {"obs_date": "2023-11-03", "sensor": "Sentinel-2",
                 "water_area_m2": None, "value_type": "unavailable"},
            ],
        )
        assert "gap" in html
        assert "never interpolated" in html

    def test_the_report_says_levels_are_not_predictions(self, cfg: Config) -> None:
        assert "indicators, not predictions" in render(cfg)

    def test_provenance_is_recorded(self, cfg: Config) -> None:
        html = render(cfg, config_hash="abc123def456", code_version=None)
        assert "abc123def456" in html
        assert "not a git working tree" in html

    def test_html_is_escaped(self, cfg: Config) -> None:
        """Autoescape on: a value cannot inject markup."""
        html = render_site_html(
            site={"site_code": "<script>x</script>", "site_type": "t"},
            answers=[],
            disclaimer=cfg.project.disclaimer,
            project_name="p",
            project_version="1",
        )
        assert "<script>x</script>" not in html
        assert "&lt;script&gt;" in html


# --------------------------------------------------------------------------- #
# PDF engines
# --------------------------------------------------------------------------- #


class TestPDFEngines:
    def test_requesting_weasyprint_when_unusable_raises_clearly(
        self, cfg: Config, tmp_path: Path
    ) -> None:
        if weasyprint_available():
            pytest.skip("weasyprint works here, so there is nothing to refuse")
        html_path = tmp_path / "r.html"
        html_path.write_text(render(cfg), encoding="utf-8")
        with pytest.raises(NoPDFEngineError, match="GTK/Pango"):
            html_to_pdf(html_path, tmp_path / "r.pdf", engine="weasyprint")

    def test_a_missing_engine_does_not_lose_the_html(
        self, cfg: Config, tmp_path: Path, monkeypatch
    ) -> None:
        """A report is still a report without a PDF."""
        import reports.generate as generate

        monkeypatch.setattr(generate, "weasyprint_available", lambda: False)
        monkeypatch.setattr(generate, "find_chromium", lambda: None)

        result = generate.generate_site_report(
            site=SITE,
            answers=answers(),
            disclaimer=cfg.project.disclaimer,
            project_name=cfg.project.name,
            project_version=cfg.project.version,
            out_dir=tmp_path,
        )
        assert result.html_path.exists()
        assert not result.has_pdf
        assert result.pdf_error
        assert "complete deliverable" in result.pdf_error

    @pytest.mark.slow
    def test_a_real_pdf_is_produced(self, cfg: Config, tmp_path: Path) -> None:
        """Phase 13's gate: a PDF report for one site."""
        if not weasyprint_available() and find_chromium() is None:
            pytest.skip("no PDF engine on this machine")

        result = generate_site_report(
            site=SITE,
            answers=answers(),
            disclaimer=cfg.project.disclaimer,
            project_name=cfg.project.name,
            project_version=cfg.project.version,
            out_dir=tmp_path,
            level="MONITOR",
        )
        assert result.has_pdf, result.pdf_error
        assert result.pdf_path.read_bytes().startswith(b"%PDF-")
        assert result.pdf_path.stat().st_size > 1000
        assert result.pdf_engine

    @pytest.mark.slow
    def test_the_pdf_carries_the_disclaimer_and_the_reasons(
        self, cfg: Config, tmp_path: Path
    ) -> None:
        """Checked in the rendered PDF, not merely in the HTML it came from."""
        pypdf = pytest.importorskip("pypdf")
        if not weasyprint_available() and find_chromium() is None:
            pytest.skip("no PDF engine on this machine")

        result = generate_site_report(
            site=SITE,
            answers=answers(),
            disclaimer=cfg.project.disclaimer,
            project_name=cfg.project.name,
            project_version=cfg.project.version,
            out_dir=tmp_path,
            level="NORMAL",
            insufficient_data=True,
        )
        assert result.has_pdf, result.pdf_error
        reader = pypdf.PdfReader(str(result.pdf_path))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)

        assert REQUIRED_DISCLAIMER_PHRASE in text
        assert "INSUFFICIENT DATA" in text
        assert "no bathymetry" in text
        assert "ND-001" in text


# --------------------------------------------------------------------------- #
# Straight from the database
# --------------------------------------------------------------------------- #


class TestFromDatabase:
    def populated(self, tmp_path: Path, cfg: Config) -> Database:
        db = Database(tmp_path / "m.sqlite")
        db.initialise()
        site_id = db.upsert_site(
            site_code="ND-009",
            site_type="Potential Landslide Dam",
            lat=27.86,
            lon=86.47,
            confidence=0.8,
        )
        db.add_observation(
            site_id,
            obs_date="2023-10-19",
            sensor="Sentinel-2",
            orbit_or_tile="45RVL",
            value_type="derived",
            water_area_m2=1_600_500.0,
        )
        db.add_depth_volume(
            {
                "site_id": site_id,
                "obs_date": "2023-10-19",
                "branch": "B",
                "wse_m": 4554.7,
                "wse_uncertainty_m": 10.2,
                "mean_depth_m": None,
                "max_depth_m": None,
                "volume_m3": None,
                "volume_low_m3": None,
                "volume_high_m3": None,
                "value_type": "unavailable",
                "method": "brief Section 8 branch logic",
                "notes": "DEM records water surface; no bathymetry",
            }
        )
        return db

    def test_a_report_builds_from_stored_rows(
        self, tmp_path: Path, cfg: Config
    ) -> None:
        db = self.populated(tmp_path, cfg)
        try:
            result = site_report_from_database(
                db, "ND-009", cfg, out_dir=tmp_path / "out"
            )
        finally:
            db.close()
        html = result.html_path.read_text(encoding="utf-8")
        assert "ND-009" in html
        assert "no bathymetry" in html
        assert REQUIRED_DISCLAIMER_PHRASE in html

    def test_an_unknown_site_is_refused(self, tmp_path: Path, cfg: Config) -> None:
        db = self.populated(tmp_path, cfg)
        try:
            with pytest.raises(KeyError, match="no site"):
                site_report_from_database(db, "NOPE", cfg, out_dir=tmp_path / "out")
        finally:
            db.close()

    def test_the_report_and_the_dashboard_cannot_disagree(
        self, tmp_path: Path, cfg: Config
    ) -> None:
        """Both render the same build_site_view output, by construction."""
        from app.site_view import build_site_view

        db = self.populated(tmp_path, cfg)
        try:
            result = site_report_from_database(
                db, "ND-009", cfg, out_dir=tmp_path / "out"
            )
            site = dict(db.site("ND-009"))
            estimates = db.depth_volume_estimates(site["id"])
            view = build_site_view(
                site=site,
                disclaimer=cfg.project.disclaimer,
                depth_estimate=dict(estimates[-1]),
            )
        finally:
            db.close()

        html = result.html_path.read_text(encoding="utf-8")
        for answer in view.answers:
            assert answer.question in html
