from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from rizq.config import Settings
from rizq.data.schemas import Bar

log = structlog.get_logger(__name__)

DEFAULT_DATASET = "XNAS.ITCH"
DEFAULT_SCHEMA = "ohlcv-1d"

REQUIRED_COLUMNS = {"ticker", "session_date", "open", "high", "low", "close", "volume"}


def write_curated_bars(
    df: pd.DataFrame,
    curated_zone: Path,
    observed_at: datetime | None = None,
) -> dict[str, int]:
    """Write normalized daily bars to the curated zone, partitioned by ticker.

    Expects columns: ticker, session_date, open, high, low, close, volume.
    """
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame missing required columns: {sorted(missing)}")
    if df.empty:
        return {}

    when = observed_at or datetime.now()

    out = df.copy()
    out["session_date"] = pd.to_datetime(out["session_date"]).dt.normalize()
    out["as_of"] = out["session_date"]
    out["observed_at"] = when
    out["adjusted"] = False

    first = out.iloc[0]
    Bar(
        ticker=str(first["ticker"]),
        session_date=pd.Timestamp(first["session_date"]).date(),
        open=float(first["open"]),
        high=float(first["high"]),
        low=float(first["low"]),
        close=float(first["close"]),
        volume=int(first["volume"]),
        as_of=pd.Timestamp(first["session_date"]).date(),
        observed_at=when,
    )

    bars_dir = curated_zone / "bars"
    counts: dict[str, int] = {}
    for ticker, group in out.groupby("ticker"):
        ticker_str = str(ticker)
        ticker_dir = bars_dir / f"ticker={ticker_str}"
        ticker_dir.mkdir(parents=True, exist_ok=True)
        path = ticker_dir / "data.parquet"
        group.drop(columns=["ticker"]).to_parquet(path, index=False)
        counts[ticker_str] = len(group)
        log.info(
            "curated_bars_written",
            ticker=ticker_str,
            rows=len(group),
            path=str(path),
        )

    return counts


def _normalize_databento_response(df: pd.DataFrame) -> pd.DataFrame:
    """Map a Databento ohlcv-1d DataFrame to our curated columns.

    With `pretty_ts=True`, `ts_event` arrives as the DataFrame index rather than a column.
    """
    if "symbol" not in df.columns:
        raise RuntimeError(
            f"Databento response missing 'symbol' column. Got: {list(df.columns)}. "
            "Did you forget map_symbols=True or set the wrong dataset?"
        )

    flat = df.reset_index() if "ts_event" not in df.columns else df
    if "ts_event" not in flat.columns:
        raise RuntimeError(
            f"Databento response missing 'ts_event'. "
            f"Columns: {list(df.columns)}, index: {df.index.name!r}."
        )

    return pd.DataFrame(
        {
            "ticker": flat["symbol"].astype(str).values,
            "session_date": pd.to_datetime(flat["ts_event"]).dt.normalize().values,
            "open": flat["open"].astype(float).values,
            "high": flat["high"].astype(float).values,
            "low": flat["low"].astype(float).values,
            "close": flat["close"].astype(float).values,
            "volume": flat["volume"].astype("int64").values,
        }
    )


def fetch_databento_daily(
    tickers: list[str],
    start: date,
    end: date,
    api_key: str,
    dataset: str = DEFAULT_DATASET,
    raw_archive_dir: Path | None = None,
    client: Any | None = None,
) -> pd.DataFrame:
    """Fetch daily bars from Databento and return a normalized DataFrame."""
    if client is None:
        import databento as db

        client = db.Historical(api_key)

    log.info(
        "databento_fetch_start",
        dataset=dataset,
        symbols=tickers,
        start=start.isoformat(),
        end=end.isoformat(),
    )
    response = client.timeseries.get_range(
        dataset=dataset,
        schema=DEFAULT_SCHEMA,
        symbols=tickers,
        start=start.isoformat(),
        end=end.isoformat(),
    )

    if raw_archive_dir is not None:
        raw_archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = raw_archive_dir / f"{dataset}_{start.isoformat()}_{end.isoformat()}.dbn.zst"
        response.to_file(str(archive_path))
        log.info("raw_archived", path=str(archive_path))

    df = response.to_df(pretty_ts=True, price_type="float")
    return _normalize_databento_response(df)


def ingest_daily_bars(
    tickers: list[str],
    start: date,
    end: date,
    settings: Settings,
    dataset: str = DEFAULT_DATASET,
) -> dict[str, int]:
    if not settings.databento_api_key:
        raise ValueError("DATABENTO_API_KEY is not set; cannot ingest from Databento")

    df = fetch_databento_daily(
        tickers=tickers,
        start=start,
        end=end,
        api_key=settings.databento_api_key,
        dataset=dataset,
        raw_archive_dir=settings.raw_zone / "databento",
    )
    return write_curated_bars(df, settings.curated_zone)
