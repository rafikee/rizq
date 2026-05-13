from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from rizq.data.query import _apply_splits, get_bars, get_sessions


def _write_bars(curated: Path, ticker: str, start: date, prices: list[float]) -> None:
    sessions = [start + timedelta(days=i) for i in range(len(prices))]
    df = pd.DataFrame(
        {
            "session_date": pd.to_datetime(sessions),
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1_000_000] * len(prices),
            "as_of": pd.to_datetime(sessions),
            "observed_at": [datetime.now()] * len(prices),
            "adjusted": [False] * len(prices),
        }
    )
    out_dir = curated / "bars" / f"ticker={ticker}"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_dir / "data.parquet", index=False)


def _write_splits(curated: Path, rows: list[dict[str, object]]) -> None:
    out_dir = curated / "corporate_actions"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(out_dir / "data.parquet", index=False)


def test_get_bars_unadjusted_returns_raw_prices(tmp_path: Path) -> None:
    _write_bars(tmp_path, "AMD", date(2024, 1, 1), [100.0, 110.0, 120.0])

    df = get_bars("AMD", date(2024, 1, 1), date(2024, 1, 3), tmp_path, adjusted=False)

    assert len(df) == 3
    assert list(df.columns) == ["ticker", "session_date", "open", "high", "low", "close", "volume"]
    assert df["close"].tolist() == [100.0, 110.0, 120.0]
    assert df["ticker"].iloc[0] == "AMD"


def test_get_bars_filters_by_date_range(tmp_path: Path) -> None:
    _write_bars(tmp_path, "AMD", date(2024, 1, 1), [100.0, 101.0, 102.0, 103.0, 104.0])

    df = get_bars("AMD", date(2024, 1, 2), date(2024, 1, 4), tmp_path)

    assert len(df) == 3
    assert df["close"].tolist() == [101.0, 102.0, 103.0]


def test_get_bars_adjusted_applies_split(tmp_path: Path) -> None:
    _write_bars(tmp_path, "AMD", date(2024, 1, 1), [100.0, 100.0, 100.0, 100.0])
    _write_splits(
        tmp_path,
        [
            {
                "ticker": "AMD",
                "effective_date": date(2024, 1, 3),
                "kind": "split",
                "split_ratio": 2.0,
                "cash_amount": None,
                "observed_at": datetime.now(),
            }
        ],
    )

    df = get_bars("AMD", date(2024, 1, 1), date(2024, 1, 4), tmp_path, adjusted=True)

    assert df["close"].tolist() == pytest.approx([50.0, 50.0, 100.0, 100.0])
    assert df["volume"].tolist() == [2_000_000, 2_000_000, 1_000_000, 1_000_000]


def test_get_bars_missing_ticker_returns_empty(tmp_path: Path) -> None:
    _write_bars(tmp_path, "AMD", date(2024, 1, 1), [100.0])

    df = get_bars("MU", date(2024, 1, 1), date(2024, 1, 5), tmp_path)

    assert df.empty


def test_get_sessions_returns_sorted_union(tmp_path: Path) -> None:
    _write_bars(tmp_path, "AMD", date(2024, 1, 1), [100.0, 100.0])
    _write_bars(tmp_path, "MU", date(2024, 1, 2), [50.0, 50.0])

    sessions = get_sessions(["AMD", "MU"], date(2024, 1, 1), date(2024, 1, 3), tmp_path)

    assert sessions == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]


def test_apply_splits_compounds_multiple_splits() -> None:
    bars = pd.DataFrame(
        {
            "ticker": ["AMD"] * 5,
            "session_date": pd.to_datetime(
                [
                    date(2024, 1, 1),
                    date(2024, 6, 1),
                    date(2024, 6, 2),
                    date(2025, 1, 1),
                    date(2025, 1, 2),
                ]
            ),
            "open": [100.0] * 5,
            "high": [100.0] * 5,
            "low": [100.0] * 5,
            "close": [100.0] * 5,
            "volume": [1_000_000] * 5,
        }
    )
    splits = pd.DataFrame(
        {
            "effective_date": [date(2025, 1, 1), date(2024, 6, 1)],
            "split_ratio": [3.0, 2.0],
        }
    )

    adjusted = _apply_splits(bars, splits)

    assert adjusted["close"].tolist() == pytest.approx(
        [100.0 / 6, 100.0 / 3, 100.0 / 3, 100.0, 100.0]
    )
