from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from rizq.backtest.schemas import BacktestResult
from rizq.config import get_settings
from rizq.data.query import get_bars


def load_result(path: Path) -> BacktestResult:
    """Load a backtest result JSON file.

    Strips CLI-added presentation keys (`_generated_at`, `equity_curve_monthly`)
    before validating against the canonical schema.
    """
    raw = json.loads(path.read_text())
    raw.pop("_generated_at", None)
    raw.pop("equity_curve_monthly", None)
    return BacktestResult.model_validate(raw)


def load_bars_for_trade(
    ticker: str,
    entry_date: date,
    exit_date: date,
    pad_days: int = 30,
) -> pd.DataFrame:
    """Bars around a trade, with enough lookback to compute SMA200 from the left edge."""
    settings = get_settings()
    start = entry_date - timedelta(days=365 + pad_days * 2)
    end = exit_date + timedelta(days=pad_days * 2)
    return get_bars(ticker, start, end, settings.curated_zone, adjusted=True)


def list_result_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))
