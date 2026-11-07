"""Per-site report generation: HTML via Jinja2, PDF via WeasyPrint or Chromium.

Brief, Section 4 names ``jinja2`` + ``weasyprint`` (HTML -> PDF), and Phase 13's
gate is a PDF report for one site.

Why there are two PDF engines
-----------------------------
WeasyPrint installs cleanly with pip on this machine but cannot import:
it binds to GTK/Pango native libraries that Windows does not ship, and the
import fails with ``cannot load library 'libgobject-2.0-0'``. That is the
documented Windows situation for WeasyPrint, not a fault of this project and
not the Smart App Control problem recorded elsewhere -- installing the GTK
runtime is a system-wide change that belongs to the machine's owner, not to a
build script.

So the PDF step is engine-agnostic. ``weasyprint`` is preferred when it
imports; otherwise the HTML is printed by **headless Chromium** (Edge or
Chrome, both already present on Windows), which needs no installation. The
engine used is recorded on the result, because a report should be able to say
how it was made.

The HTML itself is always produced, by Jinja2 alone. If no PDF engine is
available the HTML report is still a complete deliverable, and
:func:`generate_site_report` says so rather than failing silently.

The answers are not rebuilt here
--------------------------------
Report content comes from :func:`app.site_view.build_site_view`, the same
function the dashboard uses. A report and a dashboard that answered the same
question differently would be worse than either alone, so there is one
implementation and both render it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from utils.logging import get_logger

log = get_logger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"
SITE_TEMPLATE = "site_report.html"

#: Candidate headless browsers, in preference order. Edge ships with Windows.
CHROMIUM_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)

LEVEL_COLOUR = {
    "NORMAL": "#0ca30c",
    "MONITOR": "#fab219",
    "HIGH RISK INDICATORS": "#ec835a",
    "CRITICAL INDICATORS - verification recommended": "#d03b3b",
}
LEVEL_SYMBOL = {
    "NORMAL": "\N{LARGE GREEN CIRCLE}",
    "MONITOR": "\N{LARGE YELLOW CIRCLE}",
    "HIGH RISK INDICATORS": "\N{LARGE ORANGE CIRCLE}",
    "CRITICAL INDICATORS - verification recommended": "\N{LARGE RED CIRCLE}",
}
INSUFFICIENT_COLOUR = "#8a8a85"
INSUFFICIENT_SYMBOL = "\N{MEDIUM WHITE CIRCLE}"


class NoPDFEngineError(RuntimeError):
    """Neither WeasyPrint nor a headless Chromium could be used."""


@dataclass(frozen=True)
class ReportResult:
    """What was written, and how."""

    html_path: Path
    pdf_path: Path | None
    pdf_engine: str | None
    pdf_error: str | None = None

    @property
    def has_pdf(self) -> bool:
        return self.pdf_path is not None and self.pdf_path.exists()

    def describe(self) -> str:
        if self.has_pdf:
            return f"HTML {self.html_path.name}, PDF {self.pdf_path.name} via {self.pdf_engine}"
        return f"HTML {self.html_path.name}; no PDF ({self.pdf_error})"


def weasyprint_available() -> bool:
    """Whether WeasyPrint can actually be used, not merely imported by pip."""
    try:
        import weasyprint  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment-dependent
        log.debug("weasyprint unavailable: %s", exc)
        return False
    return True


def find_chromium() -> Path | None:
    """A headless Chromium to print with, or ``None``."""
    for candidate in CHROMIUM_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path
    for name in ("msedge", "chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def render_site_html(
    *,
    site: dict[str, Any],
    answers: Sequence[Any],
    disclaimer: str,
    project_name: str,
    project_version: str,
    level: str | None = None,
    risk: dict[str, Any] | None = None,
    factors: Sequence[dict[str, Any]] | None = None,
    observations: Sequence[dict[str, Any]] | None = None,
    sources: Sequence[str] | None = None,
    config_hash: str | None = None,
    code_version: str | None = None,
    insufficient_data: bool = False,
) -> str:
    """Render the site report to an HTML string."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template(SITE_TEMPLATE)

    # A NORMAL level on thin evidence is grey, not green -- the same
    # withholding applied in analysis.risk, app.charts and app.maps. A report
    # is one more surface that may be read alone.
    if insufficient_data and level == "NORMAL":
        colour, symbol = INSUFFICIENT_COLOUR, INSUFFICIENT_SYMBOL
    else:
        colour = LEVEL_COLOUR.get(level or "", INSUFFICIENT_COLOUR)
        symbol = LEVEL_SYMBOL.get(level or "", INSUFFICIENT_SYMBOL)

    return template.render(
        site=site,
        answers=[a if isinstance(a, dict) else a.as_dict() for a in answers],
        disclaimer=disclaimer,
        project_name=project_name,
        project_version=project_version,
        level=level or "No assessment",
        level_colour=colour,
        level_symbol=symbol,
        risk=risk,
        factors=list(factors or []),
        observations=list(observations or []),
        sources_text="; ".join(sources) if sources else "not recorded",
        config_hash=config_hash,
        code_version=code_version,
        insufficient_data=insufficient_data,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def html_to_pdf(
    html_path: Path, pdf_path: Path, *, engine: str = "auto", timeout: int = 120
) -> str:
    """Convert an HTML file to PDF, returning the engine actually used.

    Args:
        engine: ``auto`` prefers WeasyPrint and falls back to Chromium;
            ``weasyprint`` or ``chromium`` force one.

    Raises:
        NoPDFEngineError: if the requested engine, or every engine under
            ``auto``, is unavailable. The HTML is already written by then, so
            the caller still has a report.
    """
    html_path, pdf_path = Path(html_path), Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    if engine in {"auto", "weasyprint"} and weasyprint_available():
        from weasyprint import HTML

        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        log.info("wrote %s with weasyprint", pdf_path.name)
        return "weasyprint"

    if engine == "weasyprint":
        raise NoPDFEngineError(
            "weasyprint was requested but cannot be used: it needs GTK/Pango "
            "native libraries that are not installed on this machine"
        )

    if engine in {"auto", "chromium"}:
        browser = find_chromium()
        if browser is not None:
            # --headless=new is required for print-to-pdf on current builds.
            # The output path must be ABSOLUTE: the browser resolves a
            # relative one against its own working directory, not ours, and
            # reports only "cannot find the path specified" when it fails.
            command = [
                str(browser),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=5000",
                f"--print-to-pdf={pdf_path.resolve()}",
                "--print-to-pdf-no-header",
                html_path.resolve().as_uri(),
            ]
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout
            )
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                log.info("wrote %s with headless %s", pdf_path.name, browser.stem)
                return f"chromium ({browser.stem})"
            raise NoPDFEngineError(
                f"headless {browser.stem} produced no PDF "
                f"(exit {result.returncode}): {result.stderr[:300]}"
            )

    raise NoPDFEngineError(
        "no PDF engine available: weasyprint cannot load its native libraries "
        "and no Chromium-based browser was found. The HTML report is still "
        "written and is a complete deliverable."
    )


def generate_site_report(
    *,
    site: dict[str, Any],
    answers: Sequence[Any],
    disclaimer: str,
    project_name: str,
    project_version: str,
    out_dir: Path,
    engine: str = "auto",
    **context: Any,
) -> ReportResult:
    """Write an HTML report and, where possible, a PDF beside it.

    A missing PDF engine is reported on the result rather than raised: the
    HTML is a complete report, and a monitoring run should not fail because a
    rendering library is absent.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = str(site.get("site_code", "site")).replace("/", "-")

    html = render_site_html(
        site=site,
        answers=answers,
        disclaimer=disclaimer,
        project_name=project_name,
        project_version=project_version,
        **context,
    )
    html_path = out_dir / f"{stem}_report.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_path = out_dir / f"{stem}_report.pdf"
    try:
        used = html_to_pdf(html_path, pdf_path, engine=engine)
    except NoPDFEngineError as exc:
        log.warning("no PDF written: %s", exc)
        result = ReportResult(html_path, None, None, pdf_error=str(exc))
    else:
        result = ReportResult(html_path, pdf_path, used)

    log.info("report for %s: %s", stem, result.describe())
    return result


def site_report_from_database(
    database: Any,
    site_code: str,
    cfg: Any,
    *,
    out_dir: Path,
    engine: str = "auto",
) -> ReportResult:
    """Build a site's report straight from the monitoring database."""
    from app.site_view import build_site_view
    from config.loader import config_hash
    from database.db import code_version, rows_to_dicts

    row = database.site(site_code)
    if row is None:
        raise KeyError(f"no site {site_code!r} in the database")
    site = dict(row)

    risk_row = database.latest_risk_assessment(site["id"])
    risk = dict(risk_row) if risk_row else None
    factors = json.loads(risk["factors_json"]) if risk else []

    observations = rows_to_dicts(database.observations(site["id"]))
    estimates = database.depth_volume_estimates(site["id"])
    events = rows_to_dicts(database.landslide_events(site["id"]))

    view = build_site_view(
        site=site,
        disclaimer=cfg.project.disclaimer,
        landslide_event=events[-1] if events else None,
        latest_observation=observations[-1] if observations else None,
        depth_estimate=dict(estimates[-1]) if estimates else None,
        risk={**risk, "factors": factors} if risk else None,
        sources=sorted(
            {f"{o['sensor']} {o['obs_date']}" for o in observations if o.get("sensor")}
        ),
    )

    return generate_site_report(
        site=site,
        answers=view.answers,
        disclaimer=cfg.project.disclaimer,
        project_name=cfg.project.name,
        project_version=cfg.project.version,
        out_dir=out_dir,
        engine=engine,
        level=risk["level"] if risk else None,
        risk=risk,
        factors=factors,
        observations=observations,
        sources=sorted(
            {f"{o['sensor']} {o['obs_date']}" for o in observations if o.get("sensor")}
        ),
        config_hash=config_hash(cfg),
        code_version=code_version(),
        insufficient_data=bool(risk["insufficient_data"]) if risk else False,
    )
