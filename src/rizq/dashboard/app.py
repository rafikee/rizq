from __future__ import annotations

from pathlib import Path

import streamlit as st

from rizq.dashboard.loaders import list_result_files, load_result
from rizq.dashboard.views import (
    equity_curve,
    summary,
    ticker_contribution,
    trade_detail,
    trades_table,
)

DEFAULT_PATH = Path("tests/golden/sma_50_200_cross_2021_2025.json")
SEARCH_DIRS = [Path("tests/golden"), Path("data/backtests")]


def _resolve_selection() -> Path | None:
    with st.sidebar:
        st.header("Result file")
        candidates: list[Path] = []
        for d in SEARCH_DIRS:
            candidates.extend(list_result_files(d))
        candidate_strs = [str(c) for c in candidates]

        default_idx = (
            candidate_strs.index(str(DEFAULT_PATH)) if str(DEFAULT_PATH) in candidate_strs else 0
        )

        if candidate_strs:
            picked = st.selectbox("Pick a result", candidate_strs, index=default_idx)
        else:
            picked = None
            st.caption("No files found in tests/golden or data/backtests.")

        custom = st.text_input("Or enter a custom path", "")
        chosen = custom.strip() or picked
        return Path(chosen) if chosen else None


def main() -> None:
    st.set_page_config(page_title="Rizq — Backtest Dashboard", layout="wide")
    st.title("Rizq — Backtest Dashboard")

    selection = _resolve_selection()
    if selection is None or not selection.exists():
        st.warning(
            "No result file selected. Run `uv run rizq backtest <signal> ... --out <path>.json` "
            "or `--golden` to create one."
        )
        return

    result = load_result(selection)
    st.caption(
        f"{result.signal_name}  ·  {result.start} → {result.end}  ·  "
        f"{', '.join(result.tickers)}  ·  loaded {selection}"
    )

    summary.render(result)
    st.divider()
    equity_curve.render(result)
    st.divider()
    ticker_contribution.render(result)
    st.divider()

    st.subheader("Trades")
    st.caption("Click a row to see the candlestick chart with SMA50/SMA200 around entry and exit.")
    selected = trades_table.render(result)
    st.divider()

    if selected is None:
        st.info("Select a trade above to see the detail view.")
    else:
        trade_detail.render(selected)
