from __future__ import annotations

import pandas as pd
import streamlit as st

from rizq.backtest.schemas import BacktestResult, Trade


def render(result: BacktestResult) -> Trade | None:
    if not result.trades:
        st.info("No trades.")
        return None

    df = pd.DataFrame(
        [
            {
                "trade_id": t.trade_id,
                "ticker": t.ticker,
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "qty": t.qty,
                "pnl": t.pnl,
                "pnl_pct": (t.pnl_pct or 0) * 100,
                "bars_held": t.bars_held,
                "exit_reason": t.exit_reason,
            }
            for t in result.trades
        ]
    )

    event = st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "entry_price": st.column_config.NumberColumn("Entry", format="$%.2f"),
            "exit_price": st.column_config.NumberColumn("Exit", format="$%.2f"),
            "pnl": st.column_config.NumberColumn("P&L", format="$%.2f"),
            "pnl_pct": st.column_config.NumberColumn("P&L %", format="%.2f%%"),
        },
    )

    rows: list[int] = event.selection.rows  # type: ignore[attr-defined]
    if rows:
        return result.trades[rows[0]]
    return None
