from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from rizq.backtest.engine import run_backtest
from rizq.backtest.schemas import BacktestConfig, Signal


def make_bars(ticker: str, start: date, ohlc: list[tuple[float, float]]) -> pd.DataFrame:
    sessions = [start + timedelta(days=i) for i in range(len(ohlc))]
    opens = [o for o, _ in ohlc]
    closes = [c for _, c in ohlc]
    return pd.DataFrame(
        {
            "ticker": [ticker] * len(ohlc),
            "session_date": pd.to_datetime(sessions),
            "open": opens,
            "high": [max(o, c) * 1.01 for o, c in ohlc],
            "low": [min(o, c) * 0.99 for o, c in ohlc],
            "close": closes,
            "volume": [1_000_000] * len(ohlc),
        }
    )


class ScriptedSignal:
    name = "scripted"

    def __init__(self, script: dict[tuple[str, date], str]):
        self.script = script

    def __call__(self, asof: date, bars: pd.DataFrame) -> Signal | None:
        ticker = str(bars["ticker"].iloc[-1])
        action = self.script.get((ticker, asof))
        if action is None:
            return None
        return Signal(
            ticker=ticker,
            asof=asof,
            action=action,  # type: ignore[arg-type]
            reasons=[f"scripted {action}"],
        )


def _default_cfg() -> BacktestConfig:
    return BacktestConfig(initial_capital=100_000.0, slippage_bps=10.0, position_pct=0.10)


def test_simple_buy_and_sell_roundtrip() -> None:
    start = date(2024, 1, 1)
    bars = make_bars(
        "AMD",
        start,
        [(100.0, 100.0), (110.0, 110.0), (115.0, 115.0), (120.0, 120.0)],
    )
    sessions = [start + timedelta(days=i) for i in range(4)]
    script = ScriptedSignal({("AMD", sessions[0]): "enter_long", ("AMD", sessions[2]): "exit_long"})

    result = run_backtest(
        signal=script,
        tickers=["AMD"],
        sessions=sessions,
        bars_loader=lambda _t: bars,
        cfg=_default_cfg(),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.ticker == "AMD"
    assert trade.entry_date == sessions[1]
    assert trade.exit_date == sessions[3]
    assert trade.qty == 100
    assert trade.entry_price == pytest.approx(110.11)
    assert trade.exit_price == pytest.approx(119.88)
    assert trade.pnl == pytest.approx(977.0)
    assert trade.pnl_pct == pytest.approx((119.88 / 110.11) - 1.0)
    assert trade.bars_held == 2
    assert result.equity_curve[-1].equity == pytest.approx(100_977.0)


def test_slippage_is_symmetric_on_flat_prices() -> None:
    start = date(2024, 1, 1)
    bars = make_bars("AMD", start, [(100.0, 100.0)] * 4)
    sessions = [start + timedelta(days=i) for i in range(4)]
    script = ScriptedSignal({("AMD", sessions[0]): "enter_long", ("AMD", sessions[2]): "exit_long"})

    result = run_backtest(
        signal=script,
        tickers=["AMD"],
        sessions=sessions,
        bars_loader=lambda _t: bars,
        cfg=_default_cfg(),
    )

    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(100.10)
    assert trade.exit_price == pytest.approx(99.90)
    assert trade.pnl == pytest.approx((99.90 - 100.10) * 100)


def test_ragged_start_does_not_crash() -> None:
    full_start = date(2024, 1, 1)
    sessions = [full_start + timedelta(days=i) for i in range(4)]
    bars = make_bars("ASTS", sessions[2], [(50.0, 50.0), (55.0, 55.0)])

    script = ScriptedSignal({("ASTS", sessions[2]): "enter_long"})

    result = run_backtest(
        signal=script,
        tickers=["ASTS"],
        sessions=sessions,
        bars_loader=lambda _t: bars,
        cfg=_default_cfg(),
    )

    assert len(result.equity_curve) == 4
    assert result.equity_curve[0].equity == pytest.approx(100_000.0)
    assert result.equity_curve[1].equity == pytest.approx(100_000.0)


def test_insufficient_cash_skips_buy() -> None:
    start = date(2024, 1, 1)
    bars = make_bars("AMD", start, [(100.0, 100.0)] * 3)
    sessions = [start + timedelta(days=i) for i in range(3)]
    script = ScriptedSignal({("AMD", sessions[0]): "enter_long"})

    result = run_backtest(
        signal=script,
        tickers=["AMD"],
        sessions=sessions,
        bars_loader=lambda _t: bars,
        cfg=BacktestConfig(initial_capital=10.0, slippage_bps=10.0, position_pct=0.10),
    )

    assert result.trades == []
    assert result.equity_curve[-1].equity == pytest.approx(10.0)


def test_no_double_enter_while_holding() -> None:
    start = date(2024, 1, 1)
    bars = make_bars(
        "AMD",
        start,
        [(100.0, 100.0), (110.0, 110.0), (115.0, 115.0), (120.0, 120.0)],
    )
    sessions = [start + timedelta(days=i) for i in range(4)]
    script = ScriptedSignal(
        {("AMD", sessions[0]): "enter_long", ("AMD", sessions[2]): "enter_long"}
    )

    result = run_backtest(
        signal=script,
        tickers=["AMD"],
        sessions=sessions,
        bars_loader=lambda _t: bars,
        cfg=_default_cfg(),
    )

    assert result.trades == []
    expected_equity = (100_000.0 - 100 * 110.11) + 100 * 120.0
    assert result.equity_curve[-1].equity == pytest.approx(expected_equity)


def test_exit_without_position_is_noop() -> None:
    start = date(2024, 1, 1)
    bars = make_bars("AMD", start, [(100.0, 100.0)] * 3)
    sessions = [start + timedelta(days=i) for i in range(3)]
    script = ScriptedSignal({("AMD", sessions[0]): "exit_long"})

    result = run_backtest(
        signal=script,
        tickers=["AMD"],
        sessions=sessions,
        bars_loader=lambda _t: bars,
        cfg=_default_cfg(),
    )

    assert result.trades == []
    assert result.equity_curve[-1].equity == pytest.approx(100_000.0)


def test_signal_on_last_session_does_not_fill() -> None:
    start = date(2024, 1, 1)
    bars = make_bars("AMD", start, [(100.0, 100.0)] * 3)
    sessions = [start + timedelta(days=i) for i in range(3)]
    script = ScriptedSignal({("AMD", sessions[-1]): "enter_long"})

    result = run_backtest(
        signal=script,
        tickers=["AMD"],
        sessions=sessions,
        bars_loader=lambda _t: bars,
        cfg=_default_cfg(),
    )

    assert result.trades == []
    assert result.equity_curve[-1].equity == pytest.approx(100_000.0)


def test_bars_held_uses_ticker_own_history_not_union_index() -> None:
    """Regression: bars_held must count the position ticker's own bars between entry
    and exit, not the index delta in the union sessions list."""
    start = date(2024, 1, 1)
    sessions = [start + timedelta(days=i) for i in range(7)]
    a_dates = [sessions[0], sessions[1], sessions[2], sessions[4], sessions[5], sessions[6]]
    a_bars = pd.DataFrame(
        {
            "ticker": ["A"] * 6,
            "session_date": pd.to_datetime(a_dates),
            "open": [100.0] * 6,
            "high": [101.0] * 6,
            "low": [99.0] * 6,
            "close": [100.0] * 6,
            "volume": [1_000_000] * 6,
        }
    )
    b_bars = make_bars("B", start, [(100.0, 100.0)] * 7)
    bars_by_ticker = {"A": a_bars, "B": b_bars}
    script = ScriptedSignal({("A", sessions[0]): "enter_long", ("A", sessions[5]): "exit_long"})

    result = run_backtest(
        signal=script,
        tickers=["A", "B"],
        sessions=sessions,
        bars_loader=lambda t: bars_by_ticker[t],
        cfg=_default_cfg(),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_date == sessions[1]
    assert trade.exit_date == sessions[6]
    assert trade.bars_held == 4


def test_point_in_time_correctness() -> None:
    start = date(2024, 1, 1)
    bars = make_bars("AMD", start, [(100.0 + i, 100.0 + i) for i in range(5)])
    sessions = [start + timedelta(days=i) for i in range(5)]

    seen: list[tuple[date, date]] = []

    class PeekingSignal:
        name = "peeking"

        def __call__(self, asof: date, bars: pd.DataFrame) -> Signal | None:
            max_date = bars["session_date"].max().date()
            seen.append((asof, max_date))
            assert max_date <= asof, f"Signal saw bars beyond asof: {max_date} > {asof}"
            return None

    run_backtest(
        signal=PeekingSignal(),
        tickers=["AMD"],
        sessions=sessions,
        bars_loader=lambda _t: bars,
        cfg=_default_cfg(),
    )

    assert len(seen) == 5
    assert all(max_date == asof for asof, max_date in seen)
