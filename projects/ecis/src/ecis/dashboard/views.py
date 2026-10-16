"""Extra Streamlit tabs for forecast, correlation, confidence, and impact."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ecis.dashboard.data import get_signals, get_signals_with_outcomes


def render_forecast(layout: dict, colors: dict) -> None:
    st.subheader("Next-call forecast")
    try:
        from ecis.prediction.log import list_predictions
        from ecis.extraction.correlation import list_correlations

        rows = list_predictions()
    except Exception as exc:
        st.warning(str(exc))
        return
    if not rows:
        st.info("No predictions yet. Run `--predict`.")
        return
    df = pd.DataFrame(rows)
    latest = df.sort_values("as_of_date").groupby("ticker").tail(1)
    st.dataframe(latest.drop(columns=["features_json"], errors="ignore"), use_container_width=True)

    try:
        pairs = list_correlations(0)
        sector = {}
        for p in pairs:
            sector.setdefault(p["ticker_a"], []).append(p["coefficient"])
        latest = latest.copy()
        latest["sector_agree"] = latest["ticker"].map(
            lambda t: "aligned" if abs(sum(sector.get(t, [0])) / max(len(sector.get(t, [1])), 1)) > 0.3 else "diverges"
        )
    except Exception:
        pass

    st.subheader("Prediction vs actual")
    hist = df.dropna(subset=["actual_direction"]) if "actual_direction" in df.columns else df
    if hist.empty:
        st.info("Actuals appear after the next extract + `--score-predictions`.")
        return
    hist = hist.copy()
    hist["correct"] = hist["predicted_direction"] == hist["actual_direction"]
    fig = px.scatter(
        hist, x="as_of_date", y="ticker", color="correct",
        hover_data=["predicted_direction", "actual_direction", "predicted_confidence"],
        color_discrete_map={True: colors["raised"], False: colors["lowered"]},
    )
    fig.update_layout(**layout, title="Prediction timeline")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_correlation(layout: dict) -> None:
    st.subheader("Guidance correlation")
    lag = st.radio("Lag", [0, 1], format_func=lambda v: "same quarter" if v == 0 else "one quarter", horizontal=True)
    try:
        from ecis.extraction.correlation import leading_indicators, list_correlations

        rows = list_correlations(lag)
    except Exception as exc:
        st.warning(str(exc))
        return
    if not rows:
        st.info("Run `--correlate` after several tickers have history.")
        return
    df = pd.DataFrame(rows)
    tickers = sorted(set(df["ticker_a"]) | set(df["ticker_b"]))
    matrix = pd.DataFrame(0.0, index=tickers, columns=tickers)
    for _, row in df.iterrows():
        matrix.loc[row["ticker_a"], row["ticker_b"]] = row["coefficient"]
        matrix.loc[row["ticker_b"], row["ticker_a"]] = row["coefficient"]
    fig = px.imshow(matrix, color_continuous_scale="Tealrose", zmin=-1, zmax=1, aspect="auto")
    fig.update_layout(**layout, title="Pairwise guidance correlation")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.dataframe(df, use_container_width=True, height=240)
    leaders = leading_indicators()
    if leaders:
        st.subheader("Leading / lagging")
        st.dataframe(pd.DataFrame(leaders), use_container_width=True)


def render_confidence(layout: dict, colors: dict) -> None:
    st.subheader("Confidence distribution")
    df = get_signals(limit=10000)
    if df.empty or "confidence_raw" not in df.columns:
        st.info("No signals.")
        return
    fig = go.Figure()
    fig.add_histogram(x=df["confidence_raw"], name="raw", marker_color=colors["accent"], opacity=0.7)
    if "confidence_calibrated" in df.columns:
        fig.add_histogram(
            x=df["confidence_calibrated"].dropna(), name="calibrated",
            marker_color=colors["accent2"], opacity=0.6,
        )
    fig.update_layout(**layout, barmode="overlay", title="Raw vs calibrated confidence")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    if "surprise_score" in df.columns and df["surprise_score"].notna().any():
        st.subheader("Surprise vs confidence")
        fig2 = px.scatter(
            df.dropna(subset=["surprise_score"]),
            x="confidence_raw", y="surprise_score", color="direction",
        )
        fig2.update_layout(**layout)
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    try:
        from ecis.scoring.scorer import score_by_confidence_tier, score_by_speaker

        st.subheader("By confidence tier")
        st.dataframe(pd.DataFrame(score_by_confidence_tier()), use_container_width=True)
        st.subheader("By speaker role")
        st.dataframe(pd.DataFrame(score_by_speaker()), use_container_width=True)
    except Exception:
        pass


def render_impact(layout: dict, colors: dict) -> None:
    st.subheader("Market impact")
    merged = get_signals_with_outcomes()
    if merged.empty:
        st.info("Resolve outcomes first.")
        return
    if "reaction_magnitude" in merged.columns:
        fig = px.scatter(
            merged.dropna(subset=["reaction_magnitude"]),
            x="confidence_raw", y="reaction_magnitude", color="direction",
            title="Confidence vs reaction magnitude",
        )
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    if "drift_5d" in merged.columns and "correct" in merged.columns:
        fig2 = px.histogram(
            merged.dropna(subset=["drift_5d", "correct"]),
            x="drift_5d", color="correct", barmode="overlay",
            title="Pre-call 5-day drift",
        )
        fig2.update_layout(**layout)
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
    try:
        from ecis.scoring.scorer import score_impact_weighted

        st.json(score_impact_weighted())
    except Exception:
        pass

    ling = get_signals(limit=5000)
    cols = [c for c in ("flesch_kincaid", "hedging_index", "fls_density", "tone_shift") if c in ling.columns]
    if cols and ling[cols].notna().any().any():
        st.subheader("Linguistic profiles")
        agg = ling.groupby("ticker")[cols].mean().reset_index()
        st.dataframe(agg, use_container_width=True)


def render_quality() -> None:
    st.subheader("Data completeness")
    try:
        from ecis.quality.completeness import report_completeness

        rows = report_completeness()
    except Exception as exc:
        st.warning(str(exc))
        return
    if not rows:
        st.info("No tickers in the registry yet.")
        return
    st.dataframe(pd.DataFrame(rows).drop(columns=["notes"], errors="ignore"), use_container_width=True)
    try:
        from ecis.db.init_db import get_connection

        conn = get_connection("agents")
        drift = [dict(r) for r in conn.execute(
            "SELECT feature, metric, value, created_at FROM drift_alerts ORDER BY created_at DESC LIMIT 20"
        ).fetchall()]
        conn.close()
        if drift:
            st.subheader("Recent drift alerts")
            st.dataframe(pd.DataFrame(drift), use_container_width=True)
    except Exception:
        pass

