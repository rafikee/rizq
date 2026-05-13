from __future__ import annotations

from datetime import date

import pandas as pd

from rizq.backtest.schemas import Signal


class SmaCrossSignal:
    """50/200 SMA golden-cross long-only.

    Fires `enter_long` on the bar where SMA50 crosses above SMA200, and
    `exit_long` on the inverse. No stops, no targets — that's Phase 4.
    """

    name = "sma_50_200_cross"

    fast_window = 50
    slow_window = 200

    def __call__(self, asof: date, bars: pd.DataFrame) -> Signal | None:
        if len(bars) < self.slow_window + 1:
            return None

        closes = bars["close"]
        fast = closes.rolling(self.fast_window).mean()
        slow = closes.rolling(self.slow_window).mean()

        today = float(fast.iloc[-1] - slow.iloc[-1])
        yesterday = float(fast.iloc[-2] - slow.iloc[-2])
        if pd.isna(today) or pd.isna(yesterday):
            return None

        ticker = str(bars["ticker"].iloc[-1])

        if yesterday <= 0 < today:
            return Signal(
                ticker=ticker,
                asof=asof,
                action="enter_long",
                reasons=["SMA50 crossed above SMA200"],
            )
        if yesterday >= 0 > today:
            return Signal(
                ticker=ticker,
                asof=asof,
                action="exit_long",
                reasons=["SMA50 crossed below SMA200"],
            )
        return None


sma_cross = SmaCrossSignal()
