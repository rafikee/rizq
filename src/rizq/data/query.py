from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

BAR_COLUMNS = ["ticker", "session_date", "open", "high", "low", "close", "volume"]


def get_bars(
    ticker: str,
    start: date,
    end: date,
    curated_zone: Path,
    adjusted: bool = False,
) -> pd.DataFrame:
    """Return daily bars for `ticker` in [start, end], sorted ascending.

    With `adjusted=True`, splits are applied at query time (back-adjusted prices,
    forward-adjusted volume). Dividends are ignored in Phase 1.
    """
    bars_glob = str(curated_zone / "bars" / "**" / "*.parquet")
    con = duckdb.connect(":memory:")
    try:
        raw = con.execute(
            f"""
            SELECT ticker, session_date, open, high, low, close, volume
            FROM read_parquet('{bars_glob}', hive_partitioning=true)
            WHERE ticker = ? AND session_date BETWEEN ? AND ?
            ORDER BY session_date ASC
            """,
            [ticker, start, end],
        ).df()

        if raw.empty or not adjusted:
            return raw[BAR_COLUMNS] if not raw.empty else raw

        splits = _load_splits(con, ticker, curated_zone)
        return _apply_splits(raw, splits)[BAR_COLUMNS]
    finally:
        con.close()


def get_sessions(
    tickers: list[str],
    start: date,
    end: date,
    curated_zone: Path,
) -> list[date]:
    """Return the sorted union of session dates across `tickers` in [start, end]."""
    bars_glob = str(curated_zone / "bars" / "**" / "*.parquet")
    placeholders = ",".join(["?"] * len(tickers))
    con = duckdb.connect(":memory:")
    try:
        df = con.execute(
            f"""
            SELECT DISTINCT session_date
            FROM read_parquet('{bars_glob}', hive_partitioning=true)
            WHERE ticker IN ({placeholders})
              AND session_date BETWEEN ? AND ?
            ORDER BY session_date ASC
            """,
            [*tickers, start, end],
        ).df()
    finally:
        con.close()
    return [pd.Timestamp(ts).date() for ts in df["session_date"]]


_split_warning_emitted = False


def _load_splits(con: duckdb.DuckDBPyConnection, ticker: str, curated_zone: Path) -> pd.DataFrame:
    actions_path = curated_zone / "corporate_actions" / "data.parquet"
    if not actions_path.exists():
        global _split_warning_emitted
        if not _split_warning_emitted:
            import structlog

            structlog.get_logger(__name__).warning(
                "adjusted_requested_but_no_corporate_actions",
                path=str(actions_path),
                note="Returning unadjusted prices. Ingest corporate actions before Phase 5.",
            )
            _split_warning_emitted = True
        return pd.DataFrame(columns=["effective_date", "split_ratio"])
    return con.execute(
        f"""
        SELECT effective_date, split_ratio
        FROM read_parquet('{actions_path}')
        WHERE ticker = ? AND kind = 'split' AND split_ratio IS NOT NULL
        ORDER BY effective_date DESC
        """,
        [ticker],
    ).df()


def _apply_splits(bars: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    if splits.empty:
        return bars
    out = bars.copy()
    for _, row in splits.iterrows():
        eff = pd.Timestamp(row["effective_date"])
        ratio = float(row["split_ratio"])
        mask = out["session_date"] < eff
        out.loc[mask, ["open", "high", "low", "close"]] /= ratio
        out.loc[mask, "volume"] = (out.loc[mask, "volume"] * ratio).astype("int64")
    return out
