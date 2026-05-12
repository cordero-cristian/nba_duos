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
SEASON = "2025-26"
NBA_STATS_HEADERS = {
    "Host": "stats.nba.com",
    "Connection": "keep-alive",
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Accept-Language": "en-US,en;q=0.9",
}


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
                headers=NBA_STATS_HEADERS,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            df = lineups.get_data_frames()[0].copy()
            return df
        except Exception as exc:  # network/API instability on cold start
            last_error = exc
            if attempt == REQUEST_RETRIES:
                break
            sleep_seconds = (BACKOFF_BASE_SECONDS**attempt) + random.uniform(0.1, 0.5)
            time.sleep(sleep_seconds)

    raise RuntimeError(
        f"Failed to fetch NBA duo data for season {season} after {REQUEST_RETRIES} attempts."
    ) from last_error


@st.cache_data(ttl=60 * 60, show_spinner=False)
def fetch_duos_cached(season="2025-26"):
    return fetch_duos(season=season)


def confidence_bucket(poss: float) -> str:
    if poss >= 1800:
        return "High"
    if poss >= 1000:
        return "Medium"
    return "Low"


def build_duo_bubble_chart(df: pd.DataFrame, season: str) -> None:
    st.title("Best NBA 2-Man Games")
    st.subheader("Ranking NBA player pairs by on-court impact when they share the floor")
    st.caption(
        "A duo is exactly two players on the same team. Rankings below are regular-season 2-man lineup impact estimates."
    )

    with st.expander("How this ranking works", expanded=True):
        st.markdown(
            """
            - **Primary ranking metric:** `Duo Score = Net Rating × (Possessions / (Possessions + 1200))`.
            - **Why this metric:** Net Rating captures impact per 100 possessions; the sample-size factor down-weights tiny samples.
            - **Data scope:** NBA **Regular Season**, selected season only.
            - **Reliability cues:** confidence is based on shared possessions (`High >= 1800`, `Medium >= 1000`, else `Low`).
            - **Tie-breaks:** higher Duo Score first, then higher possessions, then higher minutes.
            """
        )

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        min_poss = st.slider("Min possessions together", 0, 3000, 1000, step=100)

    with col2:
        min_min = st.slider("Min minutes together", 0, 1200, 400, step=50)

    with col3:
        label_top_n = st.slider("Label top N duos", 0, 50, 15, step=5)

    col4, col5, col6 = st.columns([1, 2, 1])

    with col4:
        teams = ["ALL"] + sorted(df["TEAM_ABBREVIATION"].unique().tolist())
        team = st.selectbox("Team filter", teams)

    with col5:
        search = st.text_input("Search duo (player name)", "")

    with col6:
        confidence_filter = st.multiselect(
            "Confidence",
            options=["High", "Medium", "Low"],
            default=["High", "Medium", "Low"],
        )

    dff = df.copy()
    dff = dff[(dff["POSS"] >= min_poss) & (dff["MIN"] >= min_min)].copy()

    if team != "ALL":
        dff = dff[dff["TEAM_ABBREVIATION"] == team].copy()

    if search.strip():
        dff = dff[dff["GROUP_NAME"].str.contains(search, case=False, na=False)].copy()

    dff["CONFIDENCE"] = dff["POSS"].apply(confidence_bucket)
    if confidence_filter:
        dff = dff[dff["CONFIDENCE"].isin(confidence_filter)].copy()

    if dff.empty:
        st.warning("No duos match your filters. Lower the minimum possessions/minutes or broaden confidence filters.")
        return

    k = 1200
    dff["DUO_SCORE"] = dff["NET_RATING"] * (dff["POSS"] / (dff["POSS"] + k))
    dff["PAIR"] = dff["GROUP_NAME"].str.replace(" : ", " + ", regex=False)

    st.markdown("### Top 5 NBA 2-Man Duos")
    st.caption(f"Season: {season} · Regular Season · Active filters applied")
    top5 = dff.sort_values(["DUO_SCORE", "POSS", "MIN"], ascending=False).head(5)
    st.dataframe(
        top5[["PAIR", "TEAM_ABBREVIATION", "DUO_SCORE", "NET_RATING", "POSS", "MIN", "CONFIDENCE"]],
        width="stretch",
        hide_index=True,
    )

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

    top_ids = set(dff.nlargest(label_top_n, "DUO_SCORE")["GROUP_ID"].tolist())
    if focus_duo != "None":
        top_ids |= set(dff[dff["GROUP_NAME"] == focus_duo]["GROUP_ID"].tolist())

    dff["LABEL"] = dff.apply(
        lambda r: r["PAIR"] if r["GROUP_ID"] in top_ids else "",
        axis=1,
    )

    fig = px.scatter(
        dff,
        x="POSS",
        y="NET_RATING",
        size="MIN",
        color=color_col,
        text="LABEL",
        hover_name="PAIR",
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
            "CONFIDENCE": True,
            "LABEL": False,
            "GROUP_ID": False,
            "GROUP_NAME": False,
        },
        labels={
            "POSS": "Possessions Together",
            "NET_RATING": "Net Rating (per 100 possessions)",
            "MIN": "Minutes Together",
        },
        height=720,
    )

    fig.update_traces(textposition="top center", textfont_size=11, marker=dict(opacity=0.75))
    fig.add_hline(y=0, line_dash="dash", opacity=0.4)
    fig.add_vline(x=min_poss, line_dash="dash", opacity=0.25)
    fig.update_layout(title="NBA 2-Man Game Rankings — Impact vs Sample Size", legend_title="Team")

    st.plotly_chart(fig, use_container_width=True)
    st.markdown("### Offense vs Defense (after filters)")
    st.caption("Top-left is best: higher offense, lower defense (points allowed). Bubble size = possessions.")

    fig2 = px.scatter(
        dff,
        x="OFF_RATING",
        y="DEF_RATING",
        size="POSS",
        color=color_col,
        hover_name="PAIR",
        hover_data={
            "TEAM_ABBREVIATION": True,
            "MIN": ":.0f",
            "POSS": ":.0f",
            "OFF_RATING": ":.1f",
            "DEF_RATING": ":.1f",
            "NET_RATING": ":.1f",
            "DUO_SCORE": ":.2f",
            "CONFIDENCE": True,
            "GROUP_ID": False,
            "GROUP_NAME": False,
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
        dff.sort_values(["DUO_SCORE", "POSS", "MIN"], ascending=False)[
            ["TEAM_ABBREVIATION", "PAIR", "CONFIDENCE", "MIN", "POSS", "OFF_RATING", "DEF_RATING", "NET_RATING", "DUO_SCORE"]
        ].head(25),
        width="stretch",
        hide_index=True,
    )


def run_app() -> None:
    try:
        with st.spinner("Loading NBA 2-man duo data from NBA stats..."):
            df = fetch_duos_cached(SEASON)
    except RuntimeError as exc:
        st.error("Could not load NBA duo data right now.")
        st.info(
            "The NBA stats API may be temporarily unavailable or blocked from this environment. "
            "Try reloading in a minute or running the API test script locally."
        )
        st.exception(exc)
        return

    build_duo_bubble_chart(df, season=SEASON)


if __name__ == "__main__":
    run_app()
