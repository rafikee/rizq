from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class Bar(BaseModel):
    """One daily OHLCV bar for a single ticker, unadjusted as reported.

    Curated-zone rows are always unadjusted. Apply corporate actions at query time
    rather than rewriting stored prices, so historical `as_of` values stay
    point-in-time correct after future splits.
    """

    ticker: str
    session_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    as_of: date
    observed_at: datetime
    adjusted: bool = False


class CorporateAction(BaseModel):
    ticker: str
    effective_date: date
    kind: Literal["split", "dividend", "spinoff"]
    split_ratio: float | None = None
    cash_amount: float | None = None
    observed_at: datetime
