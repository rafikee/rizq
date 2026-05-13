from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from rizq.backtest.engine import run_backtest
from rizq.backtest.schemas import BacktestConfig
from rizq.backtest.signals.sma_cross import sma_cross
from rizq.config import get_settings
from rizq.data.query import get_bars, get_sessions

GOLDEN_PATH = Path("tests/golden/sma_50_200_cross_2021_2025.json")
TICKERS = ["ASTS", "MVST", "IREN", "MU", "AMD", "IOT", "HIMS", "TTD"]
START = date(2021, 1, 1)
END = date(2025, 12, 31)
DATA_START = date(2020, 1, 1)
TOLERANCE = 1e-6


def _curated_zone_populated() -> bool:
    settings = get_settings()
    return any((settings.curated_zone / "bars").glob("ticker=*/data.parquet"))


pytestmark = pytest.mark.skipif(
    not _curated_zone_populated(),
    reason="Curated zone empty; run `rizq ingest bars` before this test",
)


def _run() -> dict[str, object]:
    settings = get_settings()
    sessions = get_sessions(TICKERS, START, END, settings.curated_zone)

    def loader(ticker: str):  # type: ignore[no-untyped-def]
        return get_bars(ticker, DATA_START, END, settings.curated_zone, adjusted=True)

    result = run_backtest(
        signal=sma_cross,
        tickers=TICKERS,
        sessions=sessions,
        bars_loader=loader,
        cfg=BacktestConfig.from_settings(settings),
    )
    return result.model_dump(mode="json")


def test_golden_fixture_exists() -> None:
    assert GOLDEN_PATH.exists(), (
        f"Missing golden fixture at {GOLDEN_PATH}. "
        "Regenerate with `rizq backtest sma_50_200_cross "
        "--start 2021-01-01 --end 2025-12-31 "
        "--tickers ASTS,MVST,IREN,MU,AMD,IOT,HIMS,TTD --golden`."
    )


def test_metrics_match_golden() -> None:
    fixture = json.loads(GOLDEN_PATH.read_text())
    fresh = _run()

    for key, expected in fixture["metrics"].items():
        actual = fresh["metrics"][key]
        assert actual == pytest.approx(expected, rel=TOLERANCE, abs=TOLERANCE), (
            f"metric drift on {key}: expected {expected}, got {actual}"
        )


def test_trades_match_golden() -> None:
    fixture = json.loads(GOLDEN_PATH.read_text())
    fresh = _run()

    fixture_trades = fixture["trades"]
    fresh_trades = fresh["trades"]

    assert len(fresh_trades) == len(fixture_trades), (
        f"trade count drift: expected {len(fixture_trades)}, got {len(fresh_trades)}"
    )

    numeric_keys = ["entry_price", "exit_price", "pnl", "pnl_pct"]
    exact_keys = ["trade_id", "ticker", "entry_date", "exit_date", "qty", "bars_held"]

    for i, (expected, actual) in enumerate(zip(fixture_trades, fresh_trades, strict=True)):
        for key in exact_keys:
            assert actual[key] == expected[key], (
                f"trade #{i} {key} drift: expected {expected[key]}, got {actual[key]}"
            )
        for key in numeric_keys:
            assert actual[key] == pytest.approx(expected[key], rel=TOLERANCE, abs=TOLERANCE), (
                f"trade #{i} {key} drift: expected {expected[key]}, got {actual[key]}"
            )


def test_equity_curve_endpoints_match_golden() -> None:
    fixture = json.loads(GOLDEN_PATH.read_text())
    fresh = _run()

    assert fresh["equity_curve"][0]["equity"] == pytest.approx(
        fixture["equity_curve"][0]["equity"], rel=TOLERANCE
    )
    assert fresh["equity_curve"][-1]["equity"] == pytest.approx(
        fixture["equity_curve"][-1]["equity"], rel=TOLERANCE
    )
    assert len(fresh["equity_curve"]) == len(fixture["equity_curve"])
