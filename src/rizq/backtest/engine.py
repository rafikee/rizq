from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import structlog

from rizq.backtest.protocol import SignalFunction
from rizq.backtest.schemas import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    Fill,
    Order,
    Signal,
    Trade,
)

log = structlog.get_logger(__name__)

BarsLoader = Callable[[str], pd.DataFrame]
"""Returns all bars for `ticker` over the backtest window, sorted ascending by session_date.

The DataFrame must have columns: ticker, session_date, open, high, low, close, volume.
session_date is expected to be pandas datetime64[ns]. Prices are adjusted for splits.
"""


@dataclass
class _OpenPosition:
    trade_id: str
    ticker: str
    qty: int
    entry_date: date
    entry_price: float
    reasons: list[str]
    flags: list[str] = field(default_factory=list)


@dataclass
class _PendingOrder:
    order: Order
    signal: Signal


def _bar_on(df: pd.DataFrame, session: date) -> pd.Series | None:
    matches = df[df["session_date"] == pd.Timestamp(session)]
    if matches.empty:
        return None
    return matches.iloc[-1]


def _bars_through(df: pd.DataFrame, session: date) -> pd.DataFrame:
    return df[df["session_date"] <= pd.Timestamp(session)]


def _bar_exists_on(df: pd.DataFrame, session: date) -> bool:
    return bool((df["session_date"] == pd.Timestamp(session)).any())


def _apply_slippage(open_price: float, side: str, slippage_bps: float) -> float:
    factor = 1.0 + (slippage_bps / 10_000.0) * (1 if side == "buy" else -1)
    return open_price * factor


def _mark_to_market(
    cash: float,
    positions: dict[str, _OpenPosition],
    history: dict[str, pd.DataFrame],
    current: date,
) -> float:
    total = cash
    for pos in positions.values():
        bar = _bar_on(history[pos.ticker], current)
        total += pos.qty * (float(bar["close"]) if bar is not None else pos.entry_price)
    return total


def run_backtest(
    signal: SignalFunction,
    tickers: list[str],
    sessions: list[date],
    bars_loader: BarsLoader,
    cfg: BacktestConfig,
    signal_name: str | None = None,
) -> BacktestResult:
    if not sessions:
        raise ValueError("sessions list is empty")

    name = signal_name or signal.name
    tickers = sorted(tickers)
    history: dict[str, pd.DataFrame] = {t: bars_loader(t) for t in tickers}

    cash = cfg.initial_capital
    positions: dict[str, _OpenPosition] = {}
    completed_trades: list[Trade] = []
    pending: list[_PendingOrder] = []
    equity_curve: list[EquityPoint] = []
    fills: list[Fill] = []

    for current in sessions:
        # 1. Execute orders queued on the previous session at today's open.
        for p in pending:
            df = history[p.signal.ticker]
            bar = _bar_on(df, current)
            if bar is None:
                log.warning(
                    "order_dropped_no_bar",
                    ticker=p.signal.ticker,
                    fill_date=current.isoformat(),
                    placed_asof=p.order.placed_asof.isoformat(),
                )
                continue

            open_price = float(bar["open"])
            fill_price = _apply_slippage(open_price, p.order.side, cfg.slippage_bps)

            if p.order.side == "buy":
                cost = fill_price * p.order.qty
                if cost > cash:
                    log.info(
                        "buy_skipped_insufficient_cash",
                        ticker=p.signal.ticker,
                        cost=cost,
                        cash=cash,
                    )
                    continue
                cash -= cost
                positions[p.signal.ticker] = _OpenPosition(
                    trade_id=p.order.trade_id,
                    ticker=p.signal.ticker,
                    qty=p.order.qty,
                    entry_date=current,
                    entry_price=fill_price,
                    reasons=list(p.signal.reasons),
                    flags=list(p.signal.flags),
                )
                fills.append(
                    Fill(
                        fill_id=f"{p.order.order_id}-fill",
                        order_id=p.order.order_id,
                        fill_date=current,
                        fill_price=fill_price,
                        qty=p.order.qty,
                    )
                )
            else:  # sell
                pos = positions.pop(p.signal.ticker, None)
                if pos is None:
                    log.warning("sell_no_position", ticker=p.signal.ticker)
                    continue
                proceeds = fill_price * pos.qty
                cash += proceeds
                pnl = (fill_price - pos.entry_price) * pos.qty
                pnl_pct = (fill_price / pos.entry_price) - 1.0
                ticker_history = history[pos.ticker]
                bars_held = int(
                    (
                        (ticker_history["session_date"] > pd.Timestamp(pos.entry_date))
                        & (ticker_history["session_date"] <= pd.Timestamp(current))
                    ).sum()
                )
                completed_trades.append(
                    Trade(
                        trade_id=pos.trade_id,
                        ticker=pos.ticker,
                        entry_date=pos.entry_date,
                        exit_date=current,
                        entry_price=pos.entry_price,
                        exit_price=fill_price,
                        qty=pos.qty,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        bars_held=bars_held,
                        exit_reason=p.signal.reasons[0] if p.signal.reasons else "exit_long",
                        reasons=pos.reasons + p.signal.reasons,
                        flags=pos.flags + p.signal.flags,
                    )
                )
                fills.append(
                    Fill(
                        fill_id=f"{p.order.order_id}-fill",
                        order_id=p.order.order_id,
                        fill_date=current,
                        fill_price=fill_price,
                        qty=pos.qty,
                    )
                )
        pending = []

        # 2. Compute today's equity once, then evaluate signals as of current's close.
        current_equity = _mark_to_market(cash, positions, history, current)

        for ticker in tickers:
            df = history[ticker]
            if not _bar_exists_on(df, current):
                continue
            bars_to_today = _bars_through(df, current)
            sig = signal(current, bars_to_today)
            if sig is None:
                continue

            today_close = float(bars_to_today["close"].iloc[-1])

            if sig.action == "enter_long":
                if ticker in positions:
                    continue
                target_notional = cfg.position_pct * current_equity
                qty = math.floor(target_notional / today_close)
                if qty < 1:
                    log.info(
                        "enter_skipped_qty_zero",
                        ticker=ticker,
                        equity=current_equity,
                        close=today_close,
                    )
                    continue
                trade_id = f"{ticker}-{current.isoformat()}"
                order = Order(
                    order_id=f"{trade_id}-buy",
                    trade_id=trade_id,
                    placed_asof=current,
                    side="buy",
                    qty=qty,
                    intended_price=today_close,
                )
                pending.append(_PendingOrder(order=order, signal=sig))
            elif sig.action == "exit_long":
                pos = positions.get(ticker)
                if pos is None:
                    continue
                order = Order(
                    order_id=f"{pos.trade_id}-sell",
                    trade_id=pos.trade_id,
                    placed_asof=current,
                    side="sell",
                    qty=pos.qty,
                    intended_price=today_close,
                )
                pending.append(_PendingOrder(order=order, signal=sig))

        # 3. Mark to market at current's close.
        equity_curve.append(
            EquityPoint(
                date=current,
                equity=_mark_to_market(cash, positions, history, current),
                invested=bool(positions),
            )
        )

    metrics = _compute_metrics(equity_curve, completed_trades, cfg.initial_capital)

    return BacktestResult(
        signal_name=name,
        start=sessions[0],
        end=sessions[-1],
        tickers=list(tickers),
        config=cfg,
        equity_curve=equity_curve,
        trades=completed_trades,
        metrics=metrics,
    )


def _compute_metrics(
    equity_curve: list[EquityPoint],
    trades: list[Trade],
    initial_capital: float,
) -> dict[str, float]:
    if not equity_curve:
        return {}

    final_equity = equity_curve[-1].equity
    total_return = (final_equity - initial_capital) / initial_capital

    num_sessions = len(equity_curve)
    years = num_sessions / 252.0
    cagr = (final_equity / initial_capital) ** (1.0 / years) - 1.0 if years > 0 else 0.0

    equities = [p.equity for p in equity_curve]
    daily_returns = [
        (equities[i] / equities[i - 1]) - 1.0
        for i in range(1, len(equities))
        if equities[i - 1] > 0
    ]
    sharpe = _annualized_sharpe(daily_returns)

    invested_returns = [
        (equities[i] / equities[i - 1]) - 1.0
        for i in range(1, len(equities))
        if equities[i - 1] > 0 and equity_curve[i - 1].invested
    ]
    invested_sharpe = _annualized_sharpe(invested_returns)
    time_in_market = sum(1 for p in equity_curve if p.invested) / len(equity_curve)

    peak = equities[0]
    max_dd = 0.0
    for e in equities:
        if e > peak:
            peak = e
        dd = (e - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd

    closed = [t for t in trades if t.pnl is not None]
    wins = [t for t in closed if (t.pnl or 0) > 0]
    losses = [t for t in closed if (t.pnl or 0) <= 0]
    hit_rate = len(wins) / len(closed) if closed else 0.0
    avg_win = sum(t.pnl or 0 for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t.pnl or 0 for t in losses) / len(losses) if losses else 0.0
    expectancy = sum(t.pnl_pct or 0 for t in closed) / len(closed) if closed else 0.0

    return {
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "invested_sharpe": invested_sharpe,
        "time_in_market": time_in_market,
        "num_trades": float(len(closed)),
        "hit_rate": hit_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy_pct": expectancy,
        "final_equity": final_equity,
    }


def _annualized_sharpe(daily_returns: list[float]) -> float:
    if not daily_returns:
        return 0.0
    mean_r = sum(daily_returns) / len(daily_returns)
    var_r = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)
    std_r = math.sqrt(var_r)
    return (mean_r / std_r) * math.sqrt(252) if std_r > 0 else 0.0
