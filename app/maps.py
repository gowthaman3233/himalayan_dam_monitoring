"""Folium map building for the dashboard.

Marker styling is kept as a pure function so it can be tested without
rendering anything, and so the one rule that matters is enforced in a single
place: **a status colour never carries meaning alone**. Every marker ships its
symbol and its level text in the tooltip and popup, because MONITOR and HIGH
RISK sit adjacent in the status palette and measure a normal-vision Delta E of
13.6 -- close enough that colour alone is not a safe channel (see
``app.charts``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from app.charts import INSUFFICIENT_COLOUR, STATUS_LIGHT
from utils.logging import get_logger

log = get_logger(__name__)

#: Folium's built-in marker colours are a fixed vocabulary, so the status
#: palette is mapped onto its nearest names for the pin itself; the exact hex
#: is used for the circle overlay, where arbitrary colour is allowed.
FOLIUM_COLOUR = {
    "NORMAL": "green",
    "MONITOR": "orange",
    "HIGH RISK INDICATORS": "orange",
    "CRITICAL INDICATORS - verification recommended": "red",
}

LEVEL_SYMBOL = {
    "NORMAL": "\N{LARGE GREEN CIRCLE}",
    "MONITOR": "\N{LARGE YELLOW CIRCLE}",
    "HIGH RISK INDICATORS": "\N{LARGE ORANGE CIRCLE}",
    "CRITICAL INDICATORS - verification recommended": "\N{LARGE RED CIRCLE}",
}
INSUFFICIENT_SYMBOL = "\N{MEDIUM WHITE CIRCLE}"

#: Centre of the map when no site has coordinates. Nepal's rough centre, used
#: only as a fallback view -- never stored, never treated as a measurement.
FALLBACK_CENTRE = (28.2, 84.0)


@dataclass(frozen=True)
class MarkerStyle:
    """How one site is drawn, and the text that must accompany it."""

    colour: str
    folium_colour: str
    symbol: str
    label: str

    @property
    def tooltip(self) -> str:
        """Symbol and words together -- never the colour alone."""
        return f"{self.symbol} {self.label}"


def marker_style(level: str | None, *, insufficient_data: bool = False) -> MarkerStyle:
    """Styling for a site at a given indicator level.

    A NORMAL level resting on insufficient data is drawn grey, not green, and
    labelled as such -- the same withholding applied in :mod:`analysis.risk`
    and :mod:`app.charts`. A HIGH or CRITICAL level keeps its colour whatever
    the coverage, because muting a real alarm is the worse failure.
    """
    if not level:
        return MarkerStyle(
            colour=INSUFFICIENT_COLOUR,
            folium_colour="gray",
            symbol=INSUFFICIENT_SYMBOL,
            label="No assessment",
        )

    if insufficient_data and level == "NORMAL":
        return MarkerStyle(
            colour=INSUFFICIENT_COLOUR,
            folium_colour="gray",
            symbol=INSUFFICIENT_SYMBOL,
            label=f"{level} (insufficient data)",
        )

    return MarkerStyle(
        colour=STATUS_LIGHT.get(level, INSUFFICIENT_COLOUR),
        folium_colour=FOLIUM_COLOUR.get(level, "gray"),
        symbol=LEVEL_SYMBOL.get(level, INSUFFICIENT_SYMBOL),
        label=level,
    )


def map_centre(sites: Sequence[dict[str, Any]]) -> tuple[float, float]:
    """The mean position of sites that have one, or a fallback view."""
    located = [
        (float(s["lat"]), float(s["lon"]))
        for s in sites
        if s.get("lat") is not None and s.get("lon") is not None
    ]
    if not located:
        return FALLBACK_CENTRE
    return (
        sum(lat for lat, _ in located) / len(located),
        sum(lon for _, lon in located) / len(located),
    )


def site_popup_html(site: dict[str, Any], style: MarkerStyle, disclaimer: str) -> str:
    """Popup content for one site, disclaimer included.

    The disclaimer travels with every rendered warning surface, not only the
    page footer -- a popup can be screenshotted and shared on its own.
    """
    rows = [
        ("Site", site.get("site_code", "?")),
        ("Type", site.get("site_type", "?")),
        ("Indicator", style.tooltip),
    ]
    if site.get("water_area_m2") is not None:
        rows.append(("Water area", f"{float(site['water_area_m2']):,.0f} m²"))
    if site.get("trend"):
        rows.append(("Trend", site["trend"]))
    if site.get("first_detected"):
        rows.append(("First detected", site["first_detected"]))

    body = "".join(
        f"<tr><td style='padding-right:8px;color:#52514e'>{name}</td>"
        f"<td><b>{value}</b></td></tr>"
        for name, value in rows
    )
    return (
        f"<div style='font-family:sans-serif;font-size:13px'>"
        f"<table>{body}</table>"
        f"<div style='margin-top:6px;font-size:11px;color:#52514e'>{disclaimer}</div>"
        f"</div>"
    )


#: Styling for the detected shapes, as {layer: (colour, fill, weight)}.
#:
#: Deliberately distinct from the status palette in ``app.charts``: a shape
#: says *what was detected*, a marker says *how concerned to be*, and using one
#: palette for both would imply a lake is a warning level.
SHAPE_STYLE = {
    "lake_post": ("#1f6feb", True, 2),
    "lake_pre": ("#8aa4c8", False, 2),
    "landslide": ("#8a5a2b", True, 2),
    "blockage": ("#b3261e", True, 3),
    "stream": ("#5a8fa8", False, 2),
}


def _wkt_to_geojson(wkt: str) -> dict[str, Any] | None:
    """A WKT geometry as GeoJSON, or ``None`` if it cannot be parsed.

    Returns ``None`` rather than raising: a dashboard that will not open
    because one stored geometry is malformed is less useful than one that
    draws the rest and logs the problem.
    """
    try:
        from shapely import wkt as shapely_wkt
        from shapely.geometry import mapping

        return mapping(shapely_wkt.loads(wkt))
    except Exception as exc:  # noqa: BLE001 - any parse failure is the same here
        log.warning("could not draw a stored geometry: %s", exc)
        return None


def add_shape_layer(
    site_map: Any,
    geometries: Sequence[tuple[str, str]],
    *,
    name: str,
    style: str,
    show: bool = True,
) -> int:
    """Draw one toggleable layer of WKT geometries.

    Args:
        geometries: ``(wkt, popup text)`` pairs.
        style: a key of :data:`SHAPE_STYLE`.

    Returns:
        How many were drawn. A geometry that fails to parse is skipped and
        logged, so the count can be below the number supplied.
    """
    import folium

    colour, fill, weight = SHAPE_STYLE[style]
    group = folium.FeatureGroup(name=name, show=show)
    drawn = 0
    for wkt, popup in geometries:
        if not wkt:
            continue
        shape = _wkt_to_geojson(wkt)
        if shape is None:
            continue
        folium.GeoJson(
            shape,
            style_function=lambda _f, c=colour, f=fill, w=weight: {
                "color": c,
                "weight": w,
                "fillColor": c,
                "fillOpacity": 0.35 if f else 0.0,
            },
            tooltip=popup or name,
        ).add_to(group)
        drawn += 1
    if drawn:
        group.add_to(site_map)
    return drawn


def build_site_map(
    sites: Sequence[dict[str, Any]],
    *,
    disclaimer: str,
    zoom_start: int = 9,
    shapes: dict[str, Sequence[tuple[str, str]]] | None = None,
):
    """A Folium map of the sites, each marker carrying symbol and label.

    Args:
        shapes: optional detected geometry to draw beneath the markers, as
            ``{style key: [(wkt, popup), ...]}`` using the keys of
            :data:`SHAPE_STYLE`. Markers say how concerned to be; shapes say
            what was detected and where, which is the question a reader
            actually has when a site reads CRITICAL.
    """
    import folium

    centre = map_centre(sites)
    site_map = folium.Map(location=list(centre), zoom_start=zoom_start, tiles=None)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(site_map)
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri World Imagery",
        name="Satellite",
    ).add_to(site_map)

    # Shapes first, so the status markers sit on top of them and stay
    # clickable: a reader needs the level before the outline.
    LAYER_NAMES = {
        "stream": "Stream network",
        "landslide": "New landslide",
        "lake_pre": "Water before the event",
        "lake_post": "Barrier lake",
        "blockage": "Blockage candidate",
    }
    for style, label in LAYER_NAMES.items():
        entries = (shapes or {}).get(style) or []
        if entries:
            drawn = add_shape_layer(
                site_map, entries, name=label, style=style,
                # The pre-event outline is drawn but hidden: it is reference
                # for judging growth, not the thing being reported.
                show=(style != "lake_pre"),
            )
            log.info("drew %d %s geometr(y|ies)", drawn, label.lower())

    plotted = 0
    for site in sites:
        if site.get("lat") is None or site.get("lon") is None:
            log.info("site %s has no coordinates and is not mapped",
                     site.get("site_code"))
            continue
        style = marker_style(
            site.get("level"), insufficient_data=bool(site.get("insufficient_data"))
        )
        position = [float(site["lat"]), float(site["lon"])]
        folium.CircleMarker(
            location=position,
            radius=9,
            color=style.colour,
            fill=True,
            fill_color=style.colour,
            fill_opacity=0.85,
            weight=2,
            tooltip=f"{site.get('site_code', '?')} — {style.tooltip}",
            popup=folium.Popup(
                site_popup_html(site, style, disclaimer), max_width=320
            ),
        ).add_to(site_map)
        plotted += 1

    folium.LayerControl().add_to(site_map)
    log.info("mapped %d of %d site(s)", plotted, len(sites))
    return site_map
