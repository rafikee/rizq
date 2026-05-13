from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from rizq.data.ingest import (
    _normalize_databento_response,
    fetch_databento_daily,
    write_curated_bars,
)


def _sample_curated_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AMD", "AMD", "MU", "MU"],
            "session_date": pd.to_datetime(
                [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 1), date(2024, 1, 2)]
            ),
            "open": [100.0, 101.0, 50.0, 51.0],
            "high": [102.0, 103.0, 52.0, 53.0],
            "low": [99.0, 100.0, 49.0, 50.0],
            "close": [101.0, 102.0, 51.0, 52.0],
            "volume": [1_000_000, 1_100_000, 500_000, 600_000],
        }
    )


def test_write_curated_bars_partitions_by_ticker(tmp_path: Path) -> None:
    counts = write_curated_bars(
        _sample_curated_df(), tmp_path, observed_at=datetime(2026, 5, 13, 12, 0, 0)
    )

    assert counts == {"AMD": 2, "MU": 2}
    assert (tmp_path / "bars" / "ticker=AMD" / "data.parquet").exists()
    assert (tmp_path / "bars" / "ticker=MU" / "data.parquet").exists()

    amd = pd.read_parquet(tmp_path / "bars" / "ticker=AMD" / "data.parquet")
    assert list(amd.columns) == [
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "as_of",
        "observed_at",
        "adjusted",
    ]
    assert len(amd) == 2
    assert (amd["adjusted"] == False).all()  # noqa: E712


def test_write_curated_bars_rejects_missing_columns(tmp_path: Path) -> None:
    df = _sample_curated_df().drop(columns=["volume"])
    with pytest.raises(ValueError, match="missing required columns"):
        write_curated_bars(df, tmp_path)


def test_write_curated_bars_empty_returns_empty_counts(tmp_path: Path) -> None:
    df = _sample_curated_df().iloc[0:0]
    assert write_curated_bars(df, tmp_path) == {}


def _sample_databento_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_event": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "symbol": ["AMD", "AMD"],
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1_000_000, 1_100_000],
            "rtype": [33, 33],
            "publisher_id": [1, 1],
            "instrument_id": [12345, 12345],
        }
    )


def test_normalize_databento_response_maps_columns() -> None:
    normalized = _normalize_databento_response(_sample_databento_df())

    assert list(normalized.columns) == [
        "ticker",
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    assert normalized["ticker"].tolist() == ["AMD", "AMD"]
    assert normalized["close"].tolist() == [101.0, 102.0]


def test_normalize_databento_response_requires_symbol() -> None:
    df = _sample_databento_df().drop(columns=["symbol"])
    with pytest.raises(RuntimeError, match="missing 'symbol'"):
        _normalize_databento_response(df)


def test_fetch_databento_daily_with_mock_client(tmp_path: Path) -> None:
    fake_response = MagicMock()
    fake_response.to_df.return_value = _sample_databento_df()
    fake_response.to_file = MagicMock()

    fake_client: Any = MagicMock()
    fake_client.timeseries.get_range.return_value = fake_response

    df = fetch_databento_daily(
        tickers=["AMD"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 2),
        api_key="x",
        raw_archive_dir=tmp_path,
        client=fake_client,
    )

    fake_client.timeseries.get_range.assert_called_once()
    fake_response.to_file.assert_called_once()
    assert df["ticker"].tolist() == ["AMD", "AMD"]
