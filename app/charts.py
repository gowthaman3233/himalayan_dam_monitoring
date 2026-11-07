"""Charts for the dashboard.

Data preparation is kept separate from rendering so that the parts carrying
the project's integrity rules can be tested without a browser. The rule that
matters most here:

    **A gap must break the line.**

A line chart joins consecutive points, so plotting a lake-area series with the
cloudy dates simply left out draws a straight segment across the gap. That
segment is a visual interpolation -- exactly what Section 7.8 forbids -- and it
is drawn in the place a reader is most likely to read growth from. So gaps are
carried through as ``None`` and ``connectgaps`` is set ``False``.

On colour
---------
Indicator levels use the **status** palette (good / warning / serious /
critical), which is reserved and never reused for a data series. The palette
validator reports FAILs against it on the light surface -- warning at 1.79:1
and the warning/serious pair at a normal-vision Delta E of 13.6. Those are
documented properties of a status palette rather than defects to fix: the
prescribed mitigation is that a status colour never carries meaning alone, and
here every level is rendered with its symbol **and** its text, in both the
chart and the map. MONITOR and HIGH RISK being adjacent hues is the reason the
text label is not optional.

Neither chart ships a categorical palette: the area series is a single series
(the title names it, so no legend), and the factor chart is one measure across
categories, which is also one colour.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

from utils.logging import get_logger

log = get_logger(__name__)

#: Status palette, fixed. Never reused for a data series.
STATUS_LIGHT = {
    "NORMAL": "#0ca30c",
    "MONITOR": "#fab219",
    "HIGH RISK INDICATORS": "#ec835a",
    "CRITICAL INDICATORS - verification recommended": "#d03b3b",
}
#: The same four steps; they clear 3:1 on the dark surface.
STATUS_DARK = dict(STATUS_LIGHT)

#: Shown when a NORMAL level rests on too little evidence (see analysis.risk).
INSUFFICIENT_COLOUR = "#8a8a85"

#: Single-series blue, categorical slot 1.
SERIES_LIGHT = "#2a78d6"
SERIES_DARK = "#3987e5"

SURFACE_LIGHT = "#fcfcfb"
SURFACE_DARK = "#1a1a19"
INK_LIGHT = "#0b0b0b"
INK_DARK = "#f0efec"
MUTED_LIGHT = "#52514e"
MUTED_DARK = "#c3c2b7"


def status_colour(level: str, *, insufficient_data: bool = False, dark: bool = False) -> str:
    """The status colour for an indicator level.

    ``insufficient_data`` returns a neutral grey for a NORMAL level, matching
    the symbol withholding in :mod:`analysis.risk`: a green dot derived from a
    tenth of the evidence is false reassurance. A HIGH or CRITICAL level keeps
    its colour, because muting a real alarm is the worse failure.
    """
    table = STATUS_DARK if dark else STATUS_LIGHT
    if insufficient_data and level == "NORMAL":
        return INSUFFICIENT_COLOUR
    return table.get(level, MUTED_DARK if dark else MUTED_LIGHT)


@dataclass(frozen=True)
class SeriesPoint:
    """One point in a plotted series. ``area_m2`` is ``None`` for a gap."""

    obs_date: date
    area_m2: float | None
    reason: str | None = None


def series_with_gaps(
    observations: Sequence[Any],
) -> tuple[list[date], list[float | None], list[str]]:
    """Split observations into x, y and hover text, **preserving gaps**.

    Accepts anything with ``obs_date`` and ``area_m2`` -- an
    :class:`analysis.change.AreaObservation`, a
    :class:`detection.barrier_lake.LakeObservation`, or a database row -- and
    returns ``y`` with ``None`` wherever the area is missing.

    The ``None`` is the whole point: it is what makes the rendered line break
    instead of drawing a straight segment across a date nobody observed.
    """
    ordered = sorted(observations, key=_obs_date)
    dates = [_obs_date(o) for o in ordered]
    areas = [_obs_area(o) for o in ordered]

    labels: list[str] = []
    for observation, area in zip(ordered, areas):
        if area is None:
            reason = _obs_reason(observation) or "no valid observation"
            labels.append(f"{_obs_date(observation)}: gap — {reason}")
        else:
            labels.append(f"{_obs_date(observation)}: {area:,.0f} m²")
    return dates, areas, labels


def _obs_date(observation: Any) -> date:
    value = getattr(observation, "obs_date", None)
    if value is None and isinstance(observation, dict):
        value = observation.get("obs_date")
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


def _obs_area(observation: Any) -> float | None:
    value = getattr(observation, "area_m2", "__missing__")
    if value == "__missing__":
        value = (
            observation.get("area_m2", observation.get("water_area_m2"))
            if isinstance(observation, dict)
            else None
        )
    return None if value is None else float(value)


def _obs_reason(observation: Any) -> str | None:
    value = getattr(observation, "reason", None)
    if value is None and isinstance(observation, dict):
        value = observation.get("reason")
    return value


def area_series_figure(
    observations: Sequence[Any],
    *,
    title: str = "Lake area over time",
    dark: bool = False,
):
    """A single-series line of lake area, with gaps left open.

    No legend: one series, named by the title. Markers are large enough to
    read individually (the project's series are short), and the hover layer is
    on by default so each point's value -- or its gap reason -- is reachable.
    """
    import plotly.graph_objects as go

    dates, areas, labels = series_with_gaps(observations)
    surface = SURFACE_DARK if dark else SURFACE_LIGHT
    ink = INK_DARK if dark else INK_LIGHT
    muted = MUTED_DARK if dark else MUTED_LIGHT
    colour = SERIES_DARK if dark else SERIES_LIGHT

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=dates,
            y=areas,
            mode="lines+markers",
            line=dict(color=colour, width=2),
            marker=dict(color=colour, size=9),
            # The rule this module exists for: never bridge a gap.
            connectgaps=False,
            hovertext=labels,
            hoverinfo="text",
            name="Lake area",
            showlegend=False,
        )
    )
    gaps = sum(1 for a in areas if a is None)
    subtitle = f"{len(areas) - gaps} observation(s)" + (
        f", {gaps} gap(s) — not interpolated" if gaps else ""
    )
    figure.update_layout(
        title=dict(text=f"{title}<br><sub>{subtitle}</sub>", font=dict(color=ink)),
        paper_bgcolor=surface,
        plot_bgcolor=surface,
        font=dict(color=muted),
        xaxis=dict(title="Date", showgrid=False, linecolor=muted),
        yaxis=dict(title="Area (m²)", gridcolor=muted, griddash="dot", zeroline=False),
        margin=dict(l=60, r=20, t=70, b=50),
        hovermode="x unified",
    )
    return figure


def factor_contributions_figure(
    factors: Sequence[dict[str, Any]],
    *,
    title: str = "What the indicator level rests on",
    dark: bool = False,
):
    """Horizontal bars of each risk factor's contribution.

    One measure across categories, so one colour -- not a categorical palette.
    Unavailable factors are shown at zero length with their reason in the
    label, so a missing factor is visibly missing rather than absent from the
    chart entirely.
    """
    import plotly.graph_objects as go

    ordered = sorted(
        factors, key=lambda f: (f.get("contribution") or 0.0), reverse=True
    )
    names, values, labels = [], [], []
    for factor in ordered:
        available = bool(factor.get("available"))
        names.append(factor.get("name", "?"))
        values.append(float(factor.get("contribution") or 0.0))
        labels.append(
            f"{factor.get('value', '?')} (weight {factor.get('weight', 0):g})"
            if available
            else f"not measured — {factor.get('reason') or 'no reason recorded'}"
        )

    surface = SURFACE_DARK if dark else SURFACE_LIGHT
    ink = INK_DARK if dark else INK_LIGHT
    muted = MUTED_DARK if dark else MUTED_LIGHT
    colour = SERIES_DARK if dark else SERIES_LIGHT

    figure = go.Figure(
        go.Bar(
            x=values,
            y=names,
            orientation="h",
            marker=dict(color=colour),
            hovertext=labels,
            hoverinfo="text",
            text=labels,
            textposition="outside",
            showlegend=False,
        )
    )
    figure.update_layout(
        title=dict(text=title, font=dict(color=ink)),
        paper_bgcolor=surface,
        plot_bgcolor=surface,
        font=dict(color=muted),
        xaxis=dict(title="Contribution", gridcolor=muted, griddash="dot"),
        yaxis=dict(autorange="reversed"),
        margin=dict(l=180, r=140, t=60, b=50),
    )
    return figure
