from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd

from rizq.backtest.schemas import Signal


class SignalFunction(Protocol):
    """Contract every signal function in rizq must satisfy.

    `bars` is the per-ticker DataFrame filtered to rows where session_date <= asof.
    The harness enforces this — signal authors never get to see the future.
    """

    name: str

    def __call__(self, asof: date, bars: pd.DataFrame) -> Signal | None: ...
