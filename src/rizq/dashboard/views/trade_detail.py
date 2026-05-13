from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rizq.backtest.schemas import Trade
from rizq.dashboard.loaders import load_bars_for_trade


def render(trade: Trade) -> None:
    st.subheader(f"Trade detail · {trade.ticker}")

    cols = st.columns(5)
    cols[0].metric("Entry", f"${trade.entry_price:.2f}")
    cols[1].metric("Exit", f"${trade.exit_price:.2f}" if trade.exit_price else "—")
    cols[2].metric("P&L", f"${trade.pnl:,.2f}" if trade.pnl is not None else "—")
    cols[3].metric("P&L %", f"{(trade.pnl_pct or 0) * 100:.2f}%")
    cols[4].metric("Bars Held", trade.bars_held)

    if trade.exit_reason:
        st.caption(f"Exit reason: {trade.exit_reason}")
    if trade.reasons:
        st.caption("Reasons: " + " · ".join(trade.reasons))

    if trade.exit_date is None:
        st.info("Trade is still open; no chart available.")
        return

    bars = load_bars_for_trade(trade.ticker, trade.entry_date, trade.exit_date)
    if bars.empty:
        st.warning(f"No bars available for {trade.ticker}.")
        return

    bars = bars.sort_values("session_date").reset_index(drop=True)
    bars["sma50"] = bars["close"].rolling(50).mean()
    bars["sma200"] = bars["close"].rolling(200).mean()

    pad = pd.Timedelta(days=45)
    lo = pd.Timestamp(trade.entry_date) - pad
    hi = pd.Timestamp(trade.exit_date) + pad
    visible = bars[(bars["session_date"] >= lo) & (bars["session_date"] <= hi)]

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=visible["session_date"],
            open=visible["open"],
            high=visible["high"],
            low=visible["low"],
            close=visible["close"],
            name=trade.ticker,
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=visible["session_date"],
            y=visible["sma50"],
            name="SMA50",
            line={"color": "#ff7f0e", "width": 1.5},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=visible["session_date"],
            y=visible["sma200"],
            name="SMA200",
            line={"color": "#2ca02c", "width": 1.5},
        )
    )
    fig.add_vline(
        x=pd.Timestamp(trade.entry_date),
        line_dash="dash",
        line_color="green",
        annotation_text="entry",
        annotation_position="top",
    )
    fig.add_vline(
        x=pd.Timestamp(trade.exit_date),
        line_dash="dash",
        line_color="red",
        annotation_text="exit",
        annotation_position="top",
    )
    fig.update_layout(
        height=520,
        xaxis_rangeslider_visible=False,
        title=f"{trade.ticker}  ·  {trade.entry_date} → {trade.exit_date}",
        margin={"t": 50, "b": 30, "l": 60, "r": 30},
    )
    st.plotly_chart(fig, width="stretch")
