from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from rizq.config import Settings


class Signal(BaseModel):
    ticker: str
    asof: date
    action: Literal["enter_long", "exit_long"]
    reasons: list[str]
    flags: list[str] = Field(default_factory=list)


class Order(BaseModel):
    order_id: str
    trade_id: str
    placed_asof: date
    side: Literal["buy", "sell"]
    qty: int
    intended_price: float


class Fill(BaseModel):
    fill_id: str
    order_id: str
    fill_date: date
    fill_price: float
    qty: int


class Trade(BaseModel):
    trade_id: str
    ticker: str
    entry_date: date
    exit_date: date | None = None
    entry_price: float
    exit_price: float | None = None
    qty: int
    pnl: float | None = None
    pnl_pct: float | None = None
    bars_held: int | None = None
    exit_reason: str | None = None
    reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


class BacktestConfig(BaseModel):
    initial_capital: float
    slippage_bps: float
    position_pct: float

    @classmethod
    def from_settings(cls, settings: Settings) -> BacktestConfig:
        return cls(
            initial_capital=settings.backtest_initial_capital,
            slippage_bps=settings.backtest_slippage_bps,
            position_pct=settings.backtest_position_pct,
        )


class EquityPoint(BaseModel):
    date: date
    equity: float
    invested: bool = False


class BacktestResult(BaseModel):
    signal_name: str
    start: date
    end: date
    tickers: list[str]
    config: BacktestConfig
    equity_curve: list[EquityPoint]
    trades: list[Trade]
    metrics: dict[str, float]
