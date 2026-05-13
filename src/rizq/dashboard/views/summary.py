from __future__ import annotations

import streamlit as st

from rizq.backtest.schemas import BacktestResult


def render(result: BacktestResult) -> None:
    m = result.metrics
    row1 = st.columns(5)
    row1[0].metric("Final Equity", f"${m.get('final_equity', 0):,.0f}")
    row1[1].metric("Total Return", f"{m.get('total_return', 0) * 100:.1f}%")
    row1[2].metric("CAGR", f"{m.get('cagr', 0) * 100:.1f}%")
    row1[3].metric("Max Drawdown", f"{m.get('max_drawdown', 0) * 100:.1f}%")
    row1[4].metric("Trades", f"{int(m.get('num_trades', 0))}")

    row2 = st.columns(5)
    row2[0].metric("Sharpe", f"{m.get('sharpe', 0):.2f}")
    row2[1].metric("Invested Sharpe", f"{m.get('invested_sharpe', 0):.2f}")
    row2[2].metric("Time in Market", f"{m.get('time_in_market', 0) * 100:.1f}%")
    row2[3].metric("Hit Rate", f"{m.get('hit_rate', 0) * 100:.1f}%")
    row2[4].metric("Expectancy/Trade", f"{m.get('expectancy_pct', 0) * 100:.2f}%")
