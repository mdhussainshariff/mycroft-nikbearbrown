"""ECIS Streamlit Dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ecis.dashboard.data import (
    get_agent_actions,
    get_pending_approvals,
    get_reader_weights,
    get_signals,
    get_signals_with_outcomes,
    get_summary_stats,
    get_ticker_registry,
    get_tickers,
)

_COLORS = {
    "bg": "#0f1419",
    "surface": "#1a222c",
    "surface2": "#243040",
    "ink": "#e8eef4",
    "muted": "#8b9aab",
    "accent": "#3d9b8f",
    "accent2": "#c4a35a",
    "raised": "#3d9b8f",
    "lowered": "#c45c5c",
    "maintained": "#7a8fa3",
    "grid": "#2a3544",
}

_PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans, sans-serif", color=_COLORS["ink"], size=13),
    margin=dict(l=40, r=20, t=48, b=40),
    xaxis=dict(gridcolor=_COLORS["grid"], zeroline=False),
    yaxis=dict(gridcolor=_COLORS["grid"], zeroline=False),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
)


def _metric_cards(stats: dict) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Signals", f"{stats['total_signals']:,}")
    c2.metric("Tickers", stats["total_tickers"])
    c3.metric("Resolved Outcomes", f"{stats['total_outcomes']:,}")


def _direction_chart(by_direction: dict) -> go.Figure | None:
    if not by_direction:
        return None
    labels = list(by_direction.keys())
    values = [by_direction[k] for k in labels]
    colors = [_COLORS.get(k, _COLORS["maintained"]) for k in labels]
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.58,
                marker=dict(colors=colors, line=dict(color=_COLORS["bg"], width=2)),
                textinfo="label+percent",
                textfont=dict(size=12),
            )
        ]
    )
    layout = {**_PLOTLY_LAYOUT, "margin": dict(l=10, r=10, t=40, b=10)}
    fig.update_layout(
        **layout,
        title=dict(text="Direction mix", font=dict(size=16, family="Fraunces")),
        showlegend=False,
        height=280,
    )
    return fig


st.set_page_config(
    page_title="ECIS Dashboard",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.title("ECIS")
st.caption(
    "Earnings Call Intelligence Signals — explore extractions, reader performance, and calibration."
)

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12 = st.tabs([
    "Signal Explorer",
    "Reader Comparison",
    "Model Comparison",
    "Calibration",
    "Agent Activity",
    "Approvals",
    "RAG Query",
    "Forecast",
    "Correlation",
    "Confidence",
    "Impact",
    "Quality",
])

with tab1:
    stats = get_summary_stats()
    _metric_cards(stats)

    left, right = st.columns([1.2, 1])
    with left:
        fig_dir = _direction_chart(stats.get("by_direction") or {})
        if fig_dir:
            st.plotly_chart(fig_dir, use_container_width=True, config={"displayModeBar": False})
    with right:
        st.markdown("##### Filters")
        tickers = get_tickers()
        sel_ticker = st.selectbox("Ticker", ["All"] + tickers, key="sig_ticker")
        sel_direction = st.selectbox(
            "Direction", ["All", "raised", "lowered", "maintained"], key="sig_dir"
        )
        sel_method = st.selectbox(
            "Source",
            ["All", "keyword", "finbert", "llm", "triangulated"],
            key="sig_method",
        )
        sel_model = st.selectbox(
            "Model",
            ["All", "llama", "mistral", "qwen"],
            key="sig_model",
        )

    df = get_signals(
        ticker=sel_ticker if sel_ticker != "All" else None,
        direction=sel_direction if sel_direction != "All" else None,
        source_method=sel_method if sel_method != "All" else None,
        llm_model=sel_model if sel_model != "All" else None,
    )

    if not df.empty:
        display_cols = [
            "signal_id", "ticker", "direction", "confidence_raw",
            "confidence_calibrated", "source_method", "section_label",
            "speaker", "speaker_role", "transcript_date", "llm_model",
            "surprise_score", "hedging_index",
            "low_confidence", "chunk_quality", "trend", "retry_count",
            "supporting_quote",
        ]
        available = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available], use_container_width=True, height=420)

        if st.checkbox("Show reasoning traces"):
            for _, row in df.head(20).iterrows():
                if row.get("reasoning_trace"):
                    with st.expander(
                        f"Signal {row['signal_id']} — {row['ticker']} {row['direction']}"
                    ):
                        st.text(row["reasoning_trace"])
    else:
        st.info("No signals found. Run extraction first.")
with tab2:
    st.subheader("Reader Comparison")
    merged = get_signals_with_outcomes()

    if not merged.empty and "correct" in merged.columns:
        scored = merged.dropna(subset=["correct"])

        if not scored.empty:
            from ecis.scoring.metrics import brier_score, expected_calibration_error

            reader_metrics = []
            for method in scored["source_method"].unique():
                subset = scored[scored["source_method"] == method]
                confs = subset["confidence_raw"].tolist()
                outs = subset["correct"].astype(int).tolist()
                bs = brier_score(confs, outs)
                ece, _ = expected_calibration_error(confs, outs)
                acc = sum(outs) / len(outs) if outs else 0
                reader_metrics.append({
                    "Reader": method,
                    "N Samples": len(outs),
                    "Accuracy": round(acc, 4),
                    "Brier Score": round(bs, 4),
                    "ECE": round(ece, 4),
                })

            metrics_df = pd.DataFrame(reader_metrics)
            st.dataframe(metrics_df, use_container_width=True)

            fig = px.bar(
                metrics_df,
                x="Reader",
                y=["Brier Score", "ECE"],
                barmode="group",
                title="Reader performance",
                color_discrete_sequence=[_COLORS["accent"], _COLORS["accent2"]],
            )
            fig.update_layout(**_PLOTLY_LAYOUT, title_font=dict(family="Fraunces", size=16))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No resolved outcomes yet. Run outcome resolution first.")
    else:
        st.info("No signals with outcomes. Run extraction and outcome resolution first.")

    st.subheader("Current reader weights")
    weights = get_reader_weights()
    if not weights.empty:
        fig_w = px.bar(
            weights,
            x="reader_name",
            y="weight",
            title="Triangulation weights",
            color_discrete_sequence=[_COLORS["accent"]],
        )
        fig_w.update_layout(**_PLOTLY_LAYOUT, title_font=dict(family="Fraunces", size=16))
        st.plotly_chart(fig_w, use_container_width=True, config={"displayModeBar": False})
with tab3:
    st.subheader("Llama vs Mistral vs Qwen")
    try:
        from ecis.scoring.scorer import score_by_llm_model

        model_scores = score_by_llm_model()
    except Exception as exc:
        model_scores = []
        st.warning(f"Could not compute model scores: {exc}")

    if model_scores:
        model_df = pd.DataFrame(model_scores)
        if "murphy" in model_df.columns:
            model_df["reliability"] = model_df["murphy"].apply(
                lambda m: (m or {}).get("reliability")
            )
            model_df["resolution"] = model_df["murphy"].apply(
                lambda m: (m or {}).get("resolution")
            )
            model_df = model_df.drop(columns=["murphy"])
        st.dataframe(model_df, use_container_width=True)

        chart_df = pd.DataFrame(model_scores)
        if not chart_df.empty and "brier" in chart_df.columns:
            fig_m = px.bar(
                chart_df,
                x="llm_model",
                y=["brier", "ece"],
                barmode="group",
                title="Per-model Brier and ECE",
                color_discrete_sequence=[_COLORS["accent"], _COLORS["accent2"]],
            )
            fig_m.update_layout(**_PLOTLY_LAYOUT, title_font=dict(family="Fraunces", size=16))
            st.plotly_chart(fig_m, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info(
            "No per-model scores yet. Run extraction with `--model llama`, "
            "`--model mistral`, `--model qwen`, `--model both`, or `--model all`, "
            "then resolve outcomes."
        )

    try:
        from ecis.scoring.scorer import score_by_trend

        trend_scores = score_by_trend()
    except Exception:
        trend_scores = []
    labelled = [t for t in trend_scores if t.get("n_samples") and t.get("trend") != "unlabelled"]
    if labelled:
        st.subheader("By trend")
        st.dataframe(pd.DataFrame(labelled), use_container_width=True)

    registry = get_ticker_registry()
    if not registry.empty:
        st.subheader("Ticker registry")
        st.dataframe(registry, use_container_width=True, height=280)
with tab4:
    st.subheader("Calibration curves")
    merged = get_signals_with_outcomes()

    if not merged.empty and "correct" in merged.columns:
        scored = merged.dropna(subset=["correct"])

        if not scored.empty:
            from ecis.scoring.metrics import expected_calibration_error

            methods = scored["source_method"].unique().tolist()
            sel_readers = st.multiselect("Select readers", methods, default=list(methods[:3]))
            overlay_models = st.checkbox("Overlay LLM models", value=True, key="cal_models")

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=[0, 1], y=[0, 1], mode="lines",
                name="Perfect",
                line=dict(dash="dash", color=_COLORS["muted"], width=1.5),
            ))

            palette = [_COLORS["accent"], _COLORS["accent2"], _COLORS["lowered"], "#6b8cae"]
            for i, method in enumerate(sel_readers):
                subset = scored[scored["source_method"] == method]
                confs = subset["confidence_raw"].tolist()
                outs = subset["correct"].astype(int).tolist()
                _, bins = expected_calibration_error(confs, outs)
                non_empty = [b for b in bins if b["count"] > 0]
                if non_empty:
                    fig.add_trace(go.Scatter(
                        x=[b["avg_confidence"] for b in non_empty],
                        y=[b["avg_accuracy"] for b in non_empty],
                        mode="lines+markers",
                        name=method,
                        line=dict(color=palette[i % len(palette)], width=2.5),
                        marker=dict(size=9),
                        text=[f"n={b['count']}" for b in non_empty],
                    ))

            if overlay_models and "llm_model" in scored.columns:
                from ecis.config.settings import settings as _settings

                model_palette = {
                    "llama": _COLORS["accent"],
                    "mistral": _COLORS["accent2"],
                    "qwen": "#6b8cae",
                    "finetuned": _COLORS["raised"],
                }
                aliases = scored["llm_model"].dropna().map(_settings.model_alias)
                scored = scored.assign(_alias=aliases)
                for alias, color in model_palette.items():
                    subset = scored[scored["_alias"] == alias]
                    if subset.empty:
                        continue
                    confs = subset["confidence_raw"].tolist()
                    outs = subset["correct"].astype(int).tolist()
                    _, bins = expected_calibration_error(confs, outs)
                    non_empty = [b for b in bins if b["count"] > 0]
                    if non_empty:
                        fig.add_trace(go.Scatter(
                            x=[b["avg_confidence"] for b in non_empty],
                            y=[b["avg_accuracy"] for b in non_empty],
                            mode="lines+markers",
                            name=alias,
                            line=dict(color=color, width=2, dash="dot"),
                            marker=dict(size=8),
                        ))

            base = {k: v for k, v in _PLOTLY_LAYOUT.items() if k not in ("xaxis", "yaxis")}
            fig.update_layout(
                **base,
                title=dict(text="Reliability diagram", font=dict(family="Fraunces", size=16)),
                xaxis_title="Mean predicted confidence",
                yaxis_title="Fraction correct",
                xaxis=dict(range=[0, 1], gridcolor=_COLORS["grid"], zeroline=False),
                yaxis=dict(range=[0, 1], gridcolor=_COLORS["grid"], zeroline=False),
                height=420,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No resolved outcomes for calibration curves.")
    else:
        st.info("No data available for calibration curves.")
with tab5:
    st.subheader("Agent activity")
    agent_filter = st.selectbox(
        "Filter by agent",
        [
            "All",
            "orchestration_agent",
            "learning_graph",
            "vindication_aggregation",
            "recalibrator",
            "watchdog_triangulated",
            "watchdog_llm",
        ],
        key="agent_filter",
    )
    actions = get_agent_actions(
        agent_name=agent_filter if agent_filter != "All" else None
    )
    if not actions.empty:
        st.dataframe(actions, use_container_width=True, height=420)
    else:
        st.info("No agent actions recorded yet.")
with tab6:
    st.subheader("Human-in-the-loop approvals")
    pending = get_pending_approvals()
    if pending.empty:
        st.info("No pending proposals. Watchdog and learning-graph HITL items appear here.")
    else:
        for _, row in pending.iterrows():
            aid = int(row["approval_id"])
            with st.expander(
                f"#{aid} — {row['agent_name']} · {row['action_type']} · {row['created_at']}",
                expanded=True,
            ):
                st.markdown("**Proposal**")
                st.json(row["proposal"] if isinstance(row["proposal"], dict) else {})
                st.markdown("**Evidence**")
                st.json(row["evidence"] if isinstance(row["evidence"], dict) else {})
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Approve", key=f"approve_{aid}", type="primary"):
                        from ecis.db.approvals import resolve_approval

                        try:
                            resolve_approval(aid, approved=True)
                            st.success(f"Approved #{aid}")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                with c2:
                    if st.button("Reject", key=f"reject_{aid}"):
                        from ecis.db.approvals import resolve_approval

                        try:
                            resolve_approval(aid, approved=False)
                            st.warning(f"Rejected #{aid}")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
with tab7:
    st.subheader("Semantic search")
    query_text = st.text_area("Query earnings guidance", height=100)
    tickers = get_tickers()
    rag_cols = st.columns(3)
    with rag_cols[0]:
        rag_ticker = st.selectbox("Ticker", ["All"] + tickers, key="rag_ticker")
    with rag_cols[1]:
        rag_section = st.selectbox(
            "Section", ["All", "prepared_remarks", "qa"], key="rag_section"
        )
    with rag_cols[2]:
        n_results = st.slider("Results", 1, 20, 5)

    if st.button("Search") and query_text:
        try:
            from ecis.embedding.embedder import query_similar

            results = query_similar(
                query_text,
                n_results=n_results,
                ticker=rag_ticker if rag_ticker != "All" else None,
                section_label=rag_section if rag_section != "All" else None,
            )
            if results:
                for i, r in enumerate(results, 1):
                    meta = r["metadata"]
                    dist = r["distance"]
                    with st.expander(
                        f"Result {i} — {meta.get('ticker', '?')} "
                        f"({meta.get('transcript_date', '?')}) "
                        f"[{1 - dist:.3f}]"
                    ):
                        st.markdown(f"**Section:** {meta.get('section_label', '?')}")
                        st.markdown(f"**Speaker:** {meta.get('speaker', 'Unknown')}")
                        st.markdown(f"**Source:** `{meta.get('source_file', '?')}`")
                        st.text(r["text"])
            else:
                st.warning("No results found.")
        except Exception as e:
            st.error(f"Search failed: {e}")
from ecis.dashboard.views import render_confidence, render_correlation, render_forecast, render_impact, render_quality

with tab8:
    render_forecast(_PLOTLY_LAYOUT, _COLORS)
with tab9:
    render_correlation(_PLOTLY_LAYOUT)
with tab10:
    render_confidence(_PLOTLY_LAYOUT, _COLORS)
with tab11:
    render_impact(_PLOTLY_LAYOUT, _COLORS)
with tab12:
    render_quality()
