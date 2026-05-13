from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rizq.backtest.schemas import BacktestResult


def render(result: BacktestResult) -> None:
    if not result.equity_curve:
        st.info("Empty equity curve.")
        return

    df = pd.DataFrame(
        [{"date": p.date, "equity": p.equity, "invested": p.invested} for p in result.equity_curve]
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["equity"],
            mode="lines",
            name="Equity",
            line={"color": "#1f77b4", "width": 2},
            hovertemplate="%{x|%Y-%m-%d}<br>$%{y:,.0f}<extra></extra>",
        )
    )

    for start_idx, end_idx in _invested_runs(df["invested"].tolist()):
        fig.add_vrect(
            x0=df["date"].iloc[start_idx],
            x1=df["date"].iloc[end_idx],
            fillcolor="rgba(46, 160, 67, 0.10)",
            line_width=0,
            layer="below",
        )

    fig.update_layout(
        title="Equity Curve (shaded = invested)",
        xaxis_title=None,
        yaxis_title="Equity ($)",
        hovermode="x unified",
        height=420,
        margin={"t": 50, "b": 30, "l": 60, "r": 30},
    )
    st.plotly_chart(fig, width="stretch")


def _invested_runs(flags: list[bool]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(flags) - 1))
    return runs
