"""Streamlit dashboard.

Run with::

    streamlit run app/dashboard.py

Reads the monitoring database written by the pipeline and answers, per site,
the eleven questions of brief Section 14. The answers themselves are built in
:mod:`app.site_view`, which has no Streamlit dependency; this module only
arranges them on a page.

Two things this file is careful about:

* **The disclaimer is unconditional.** It sits in the sidebar, above the site
  detail, and inside every map popup -- not only in a footer that a screenshot
  would crop away.
* **Nothing unavailable is rendered as a blank.** An empty cell reads as
  "nothing to report", which is a different claim from "we could not
  measure this". Every missing answer carries its reason.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from analysis.risk import LEVELS
from app.charts import area_series_figure, factor_contributions_figure, status_colour
from app.maps import build_site_map, marker_style
from app.site_view import build_site_view
from config.loader import load_config, repo_root
from database.db import Database, rows_to_dicts

DEFAULT_DB = Path("outputs") / "phase_db_demo.sqlite"


@st.cache_resource
def _config():
    return load_config(load_env=False)


def _open_database(path: Path) -> Database | None:
    if not path.exists():
        return None
    database = Database(path)
    database.connect()
    return database


def _site_rows(database: Database) -> list[dict[str, Any]]:
    """Sites with their latest assessment folded in, for the map and table."""
    rows = []
    for site in rows_to_dicts(database.sites()):
        risk = database.latest_risk_assessment(site["id"])
        observations = database.observations(site["id"])
        site["level"] = risk["level"] if risk else None
        site["score"] = risk["score"] if risk else None
        site["data_coverage"] = risk["data_coverage"] if risk else None
        site["insufficient_data"] = bool(risk["insufficient_data"]) if risk else False
        site["water_area_m2"] = (
            observations[-1]["water_area_m2"] if observations else None
        )
        site["n_observations"] = len(observations)
        rows.append(site)
    return rows


def _shapes(database: Database) -> dict[str, list[tuple[str, str]]]:
    """The stored geometry, as layers for the map.

    A level tells a reader how concerned to be; it does not tell them WHERE.
    These are the shapes behind it: the lake that is being measured, the
    landslide that produced the blockage, and the blockage itself.

    Each lake popup carries the search distance that bounded its area. Without
    it the number is uninterpretable -- the same lake measured over 500 m and
    3,000 m of channel differs threefold -- which is why the column exists.
    """
    lake_post: list[tuple[str, str]] = []
    lake_pre: list[tuple[str, str]] = []
    landslide: list[tuple[str, str]] = []
    blockage: list[tuple[str, str]] = []

    for site in rows_to_dicts(database.sites()):
        observations = rows_to_dicts(database.observations(site["id"]))
        measured = [o for o in observations if o.get("geometry")]
        for index, obs in enumerate(measured):
            area = obs.get("water_area_m2")
            bound = obs.get("search_distance_m")
            popup = (
                f"{site.get('site_code', '?')} &mdash; {obs.get('obs_date', '?')}"
                + (f"<br>{float(area):,.0f} m&sup2;" if area is not None else "")
                + (
                    f"<br>within {float(bound):,.0f} m upstream "
                    f"(a lower bound: a longer search gives a larger lake)"
                    if bound is not None
                    else "<br>search distance not recorded, so the area "
                         "cannot be interpreted"
                )
                + f"<br>{obs.get('value_type', '?')}"
            )
            # The earliest outline is the baseline the rest is judged against.
            target = lake_pre if index == 0 and len(measured) > 1 else lake_post
            target.append((obs["geometry"], popup))

        for event in rows_to_dicts(database.landslide_events(site["id"])):
            if not event.get("geometry"):
                continue
            area = event.get("area_m2")
            landslide.append((
                event["geometry"],
                f"{site.get('site_code', '?')} &mdash; new landslide"
                + (f"<br>{float(area):,.0f} m&sup2;" if area is not None else "")
                + f"<br>{event.get('pre_date', '?')} to {event.get('post_date', '?')}"
                + f"<br>{event.get('value_type', '?')}",
            ))

        if site.get("geometry"):
            confidence = site.get("confidence")
            blockage.append((
                site["geometry"],
                f"{site.get('site_code', '?')} &mdash; {site.get('site_type', '?')}"
                + (
                    f"<br>confidence {float(confidence):.3f}"
                    if confidence is not None else ""
                ),
            ))

    return {
        "lake_post": lake_post,
        "lake_pre": lake_pre,
        "landslide": landslide,
        "blockage": blockage,
    }


def main() -> None:
    st.set_page_config(
        page_title="Himalayan landslide-dam monitoring",
        page_icon="\N{GLOBE WITH MERIDIANS}",
        layout="wide",
    )
    cfg = _config()

    # ---- sidebar --------------------------------------------------------- #
    st.sidebar.title("Monitoring prototype")
    st.sidebar.warning(cfg.project.disclaimer)

    db_path = Path(
        st.sidebar.text_input(
            "Monitoring database",
            value=str(DEFAULT_DB),
            help="SQLite file written by a pipeline run.",
        )
    )
    resolved = db_path if db_path.is_absolute() else repo_root() / db_path
    database = _open_database(resolved)

    st.title("Landslide-dam and barrier-lake monitoring")
    st.caption(
        f"{cfg.project.name} · v{cfg.project.version} · "
        "research decision-support prototype"
    )

    if database is None:
        st.info(
            f"No database at `{resolved}`. Run the pipeline to create one, or "
            "point the sidebar at an existing file."
        )
        st.stop()

    sites = _site_rows(database)
    if not sites:
        st.info("The database holds no sites yet.")
        st.stop()

    # ---- overview -------------------------------------------------------- #
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Sites")
        from streamlit_folium import st_folium

        st_folium(
            build_site_map(
                sites,
                disclaimer=cfg.project.disclaimer,
                shapes=_shapes(database),
            ),
            height=460,
            use_container_width=True,
            returned_objects=[],
        )

    with right:
        st.subheader("Indicator levels")
        counts = {level: 0 for level in LEVELS}
        for site in sites:
            if site["level"] in counts:
                counts[site["level"]] += 1
        for level, count in counts.items():
            style = marker_style(level)
            st.markdown(
                f"<div style='padding:4px 0'>"
                f"<span style='display:inline-block;width:12px;height:12px;"
                f"border-radius:50%;background:{status_colour(level)};"
                f"margin-right:8px'></span>"
                f"{style.symbol} <b>{level}</b> — {count}</div>",
                unsafe_allow_html=True,
            )
        st.caption(
            "Levels are indicators, not predictions. The system never states "
            "that a dam will fail, or when."
        )

    st.divider()

    # ---- per-site detail -------------------------------------------------- #
    codes = [s["site_code"] for s in sites]
    chosen = st.selectbox("Site", codes)
    site = next(s for s in sites if s["site_code"] == chosen)

    risk_row = database.latest_risk_assessment(site["id"])
    risk = dict(risk_row) if risk_row else None
    if risk:
        risk["factors"] = json.loads(risk["factors_json"])

    estimates = database.depth_volume_estimates(site["id"])
    observations = rows_to_dicts(database.observations(site["id"]))
    events = rows_to_dicts(database.landslide_events(site["id"]))

    view = build_site_view(
        site=site,
        disclaimer=cfg.project.disclaimer,
        landslide_event=events[-1] if events else None,
        blockage=(
            {"site_type": site["site_type"], "confidence": site.get("confidence")}
            if "Dam" in str(site.get("site_type", ""))
            else None
        ),
        latest_observation=observations[-1] if observations else None,
        depth_estimate=dict(estimates[-1]) if estimates else None,
        risk=risk,
        sources=sorted(
            {
                f"{o['sensor']} {o['obs_date']}"
                for o in observations
                if o.get("sensor")
            }
        ),
    )

    style = marker_style(
        site.get("level"), insufficient_data=bool(site.get("insufficient_data"))
    )
    st.markdown(f"### {view.site_code} — {style.symbol} {style.label}")
    st.warning(cfg.project.disclaimer)

    if site.get("insufficient_data"):
        st.error(
            "INSUFFICIENT DATA — this level rests on less than the configured "
            "minimum share of the evidence. Absence of a measurement is not "
            "evidence of safety."
        )

    answers, charts = st.columns([3, 2])

    with answers:
        st.subheader("What is known about this site")
        for answer in view.answers:
            marker = "" if answer.available else " ⚠"
            st.markdown(
                f"**{answer.question}**{marker}  \n"
                f"{answer.value}"
                + (f"  \n<span style='color:#52514e'>{answer.detail}</span>"
                   if answer.detail else "")
                + (f"  \n<span style='color:#b45309'>{answer.caveat}</span>"
                   if answer.caveat else ""),
                unsafe_allow_html=True,
            )
        st.caption(
            "Every value carries its type: observed, classified, estimated, "
            "empirical, derived or unavailable."
        )

    with charts:
        st.subheader("Lake area")
        if observations:
            st.plotly_chart(
                area_series_figure(observations), width="stretch"
            )
        else:
            st.info("No observations recorded for this site.")

        if risk and risk.get("factors"):
            st.subheader("Indicator factors")
            st.plotly_chart(
                factor_contributions_figure(risk["factors"]),
                width="stretch",
            )

    with st.expander("All answers as a table"):
        st.dataframe(view.as_dicts(), width="stretch")

    with st.expander("Provenance"):
        runs = rows_to_dicts(
            database.connect().execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
        )
        st.dataframe(runs, width="stretch")
        st.caption(
            "Every stored value carries the run that produced it, with that "
            "run's configuration hash and code version."
        )


if __name__ == "__main__":
    main()
