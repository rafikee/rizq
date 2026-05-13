from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rizq.backtest.schemas import BacktestResult


def render(result: BacktestResult) -> None:
    df = _aggregate(result)
    if df.empty:
        st.info("No trades to attribute.")
        return

    df_sorted = df.sort_values("total_pnl", ascending=True)
    colors = ["#d62728" if v < 0 else "#2ca02c" for v in df_sorted["total_pnl"]]

    fig = go.Figure(
        go.Bar(
            x=df_sorted["total_pnl"],
            y=df_sorted["ticker"],
            orientation="h",
            marker={"color": colors},
            text=[f"${v:,.0f}" for v in df_sorted["total_pnl"]],
            textposition="auto",
            hovertemplate="%{y}: $%{x:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title="P&L by Ticker",
        xaxis_title="Net P&L ($)",
        yaxis_title=None,
        height=360,
        margin={"t": 50, "b": 30, "l": 60, "r": 30},
    )
    st.plotly_chart(fig, width="stretch")

    display = df.sort_values("total_pnl", ascending=False).reset_index(drop=True)
    display["win_rate"] = display["win_rate"] * 100
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            "total_pnl": st.column_config.NumberColumn("Total P&L", format="$%.2f"),
            "win_rate": st.column_config.NumberColumn("Win Rate", format="%.1f%%"),
            "avg_win": st.column_config.NumberColumn("Avg Win", format="$%.2f"),
            "avg_loss": st.column_config.NumberColumn("Avg Loss", format="$%.2f"),
        },
    )


def _aggregate(result: BacktestResult) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for ticker in result.tickers:
        trades = [t for t in result.trades if t.ticker == ticker]
        pnls = [t.pnl or 0.0 for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        rows.append(
            {
                "ticker": ticker,
                "total_pnl": float(sum(pnls)),
                "trades": len(trades),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": (len(wins) / len(trades)) if trades else 0.0,
                "avg_win": (sum(wins) / len(wins)) if wins else 0.0,
                "avg_loss": (sum(losses) / len(losses)) if losses else 0.0,
            }
        )
    return pd.DataFrame(rows)
