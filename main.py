import random
import time

import pandas as pd
import plotly.express as px
import streamlit as st
from nba_api.stats.endpoints import LeagueDashLineups
from nba_api.stats.library.parameters import MeasureTypeDetailedDefense, PerModeDetailed


REQUEST_TIMEOUT_SECONDS = 20
REQUEST_RETRIES = 4
BACKOFF_BASE_SECONDS = 1.2


def fetch_duos(season="2025-26"):
    last_error = None

    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            lineups = LeagueDashLineups(
                group_quantity=2,
                per_mode_detailed=PerModeDetailed.per_100_possessions,
                measure_type_detailed_defense=MeasureTypeDetailedDefense.advanced,
                season=season,
                season_type_all_star="Regular Season",
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            df = lineups.get_data_frames()[0].copy()
            return df
        except Exception as exc:  # network/API instability on cold start
            last_error = exc
            if attempt == REQUEST_RETRIES:
                break
            sleep_seconds = (BACKOFF_BASE_SECONDS ** attempt) + random.uniform(0.1, 0.5)
            time.sleep(sleep_seconds)

    raise RuntimeError(
        f"Failed to fetch NBA duo data for season {season} after {REQUEST_RETRIES} attempts."
    ) from last_error


@st.cache_data(ttl=60 * 60, show_spinner=False)
def fetch_duos_cached(season="2025-26"):
    return fetch_duos(season=season)


def build_duo_bubble_chart(df: pd.DataFrame) -> None:
    st.title("NBA Duo Analyzer")
    st.caption("Bubble chart: possessions vs net rating (bubble size = minutes).")

    # ---- filters
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        min_poss = st.slider("Min possessions together", 0, 3000, 1000, step=100)

    with col2:
        min_min = st.slider("Min minutes together", 0, 1200, 400, step=50)

    with col3:
        label_top_n = st.slider("Label top N duos", 0, 50, 15, step=5)

    col4, col5 = st.columns([1, 2])

    with col4:
        teams = ["ALL"] + sorted(df["TEAM_ABBREVIATION"].unique().tolist())
        team = st.selectbox("Team filter", teams)

    with col5:
        search = st.text_input("Search duo (player name)", "")

    # ---- base filtering
    dff = df.copy()
    dff = dff[(dff["POSS"] >= min_poss) & (dff["MIN"] >= min_min)].copy()

    if team != "ALL":
        dff = dff[dff["TEAM_ABBREVIATION"] == team].copy()

    if search.strip():
        dff = dff[dff["GROUP_NAME"].str.contains(search, case=False, na=False)].copy()

    if dff.empty:
        st.warning("No duos match your filters. Lower the minimum possessions/minutes.")
        return

    # ---- scoring
    k = 1200
    dff["DUO_SCORE"] = dff["NET_RATING"] * (dff["POSS"] / (dff["POSS"] + k))

    # Highlight selection
    focus_duo = st.selectbox(
        "Highlight a duo (optional)",
        ["None"] + dff.sort_values("DUO_SCORE", ascending=False)["GROUP_NAME"].head(100).tolist(),
    )

    if focus_duo != "None":
        dff["HIGHLIGHT"] = "Other"
        dff.loc[dff["GROUP_NAME"] == focus_duo, "HIGHLIGHT"] = "Selected"
        color_col = "HIGHLIGHT"
    else:
        color_col = "TEAM_ABBREVIATION"

    # ---- labeling
    top_ids = set(dff.nlargest(label_top_n, "DUO_SCORE")["GROUP_ID"].tolist())
    if focus_duo != "None":
        top_ids |= set(dff[dff["GROUP_NAME"] == focus_duo]["GROUP_ID"].tolist())

    dff["LABEL"] = dff.apply(
        lambda r: r["GROUP_NAME"] if r["GROUP_ID"] in top_ids else "",
        axis=1,
    )

    # ---- chart
    fig = px.scatter(
        dff,
        x="POSS",
        y="NET_RATING",
        size="MIN",
        color=color_col,
        text="LABEL",
        hover_name="GROUP_NAME",
        hover_data={
            "TEAM_ABBREVIATION": True,
            "MIN": ":.0f",
            "POSS": ":.0f",
            "OFF_RATING": ":.1f",
            "DEF_RATING": ":.1f",
            "NET_RATING": ":.1f",
            "TS_PCT": ":.3f",
            "EFG_PCT": ":.3f",
            "TM_TOV_PCT": ":.3f",
            "PACE": ":.1f",
            "DUO_SCORE": ":.2f",
            "LABEL": False,
            "GROUP_ID": False,
        },
        labels={
            "POSS": "Possessions Together",
            "NET_RATING": "Net Rating (per 100 possessions)",
            "MIN": "Minutes Together",
        },
        height=720,
    )

    fig.update_traces(
        textposition="top center",
        textfont_size=11,
        marker=dict(opacity=0.75),
    )

    fig.add_hline(y=0, line_dash="dash", opacity=0.4)
    fig.add_vline(x=min_poss, line_dash="dash", opacity=0.25)

    fig.update_layout(
        title="NBA Duos — Impact vs Sample Size",
        legend_title="Team",
        margin=dict(l=40, r=40, t=80, b=40),
    )

    st.plotly_chart(fig, use_container_width=True)
    st.markdown("### Offense vs Defense (after filters)")
    st.caption("Top-left is best: higher offense, lower defense (points allowed). Bubble size = possessions.")

    fig2 = px.scatter(
        dff,
        x="OFF_RATING",
        y="DEF_RATING",
        size="POSS",
        color=color_col,
        hover_name="GROUP_NAME",
        hover_data={
            "TEAM_ABBREVIATION": True,
            "MIN": ":.0f",
            "POSS": ":.0f",
            "OFF_RATING": ":.1f",
            "DEF_RATING": ":.1f",
            "NET_RATING": ":.1f",
            "DUO_SCORE": ":.2f",
            "GROUP_ID": False,
        },
        labels={
            "OFF_RATING": "Off Rating",
            "DEF_RATING": "Def Rating (lower is better)",
            "POSS": "Possessions Together",
        },
        height=600,
    )

    fig2.update_yaxes(autorange="reversed")

    fig2.update_traces(marker=dict(opacity=0.75))
    st.plotly_chart(fig2, use_container_width=True)

    st.download_button(
        "Download filtered duos as CSV",
        dff.to_csv(index=False).encode("utf-8"),
        file_name="nba_duos_filtered.csv",
        mime="text/csv",
    )

    st.markdown("### Top Duos (after filters)")
    st.dataframe(
        dff.sort_values("DUO_SCORE", ascending=False)[
            ["TEAM_ABBREVIATION", "GROUP_NAME", "MIN", "POSS", "OFF_RATING", "DEF_RATING", "NET_RATING", "DUO_SCORE"]
        ].head(25),
        width="stretch",
    )


with st.spinner("Loading duo data from NBA stats..."):
    df = fetch_duos_cached("2025-26")

build_duo_bubble_chart(df)
