from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import cast

from alpaca.trading.client import TradingClient
from alpaca.trading.models import TradeAccount

from rizq.backtest.engine import run_backtest
from rizq.backtest.protocol import SignalFunction
from rizq.backtest.schemas import BacktestConfig, BacktestResult
from rizq.backtest.signals.sma_cross import sma_cross
from rizq.config import get_settings
from rizq.data.ingest import ingest_daily_bars
from rizq.data.query import get_bars, get_sessions
from rizq.logging_setup import setup_logging

SIGNAL_REGISTRY: dict[str, SignalFunction] = {
    sma_cross.name: sma_cross,
}

GOLDEN_FIXTURE_DIR = Path("tests/golden")


def cmd_health() -> int:
    settings = get_settings()
    setup_logging(settings.log_level)

    client = TradingClient(
        api_key=settings.alpaca_paper_api_key,
        secret_key=settings.alpaca_paper_secret_key,
        paper=True,
    )
    account = cast(TradeAccount, client.get_account())
    print(
        f"OK  mode={settings.rizq_mode}  account_status={account.status}  "
        f"equity={account.equity}  buying_power={account.buying_power}"
    )
    return 0


def cmd_ingest_bars(args: argparse.Namespace) -> int:
    settings = get_settings()
    setup_logging(settings.log_level)

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    counts = ingest_daily_bars(
        tickers=tickers, start=start, end=end, settings=settings, dataset=args.dataset
    )
    print(f"Ingested daily bars for {len(counts)} ticker(s) from {args.dataset}:")
    for ticker, n in sorted(counts.items()):
        print(f"  {ticker}: {n} rows")
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    settings = get_settings()
    setup_logging(settings.log_level)

    if args.signal not in SIGNAL_REGISTRY:
        print(f"Unknown signal: {args.signal}. Available: {sorted(SIGNAL_REGISTRY)}")
        return 2
    signal = SIGNAL_REGISTRY[args.signal]

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    data_start = (
        date.fromisoformat(args.data_start) if args.data_start else start - timedelta(days=365)
    )
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    sessions = get_sessions(tickers, start, end, settings.curated_zone)
    if not sessions:
        print("No sessions found in curated zone for the given tickers/range.")
        return 1

    def loader(ticker: str) -> object:
        return get_bars(ticker, data_start, end, settings.curated_zone, adjusted=True)

    cfg = BacktestConfig.from_settings(settings)
    result = run_backtest(
        signal=signal,
        tickers=tickers,
        sessions=sessions,
        bars_loader=loader,  # type: ignore[arg-type]
        cfg=cfg,
    )

    _print_metrics_summary(result)

    if args.golden:
        GOLDEN_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        path = GOLDEN_FIXTURE_DIR / f"{args.signal}_{start.year}_{end.year}.json"
        path.write_text(_serialize_result(result))
        print(f"\nGolden fixture written: {path}")
    elif args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_serialize_result(result))
        print(f"\nResult written: {out}")

    return 0


def _print_metrics_summary(result: BacktestResult) -> None:
    print(f"\n{result.signal_name}  {result.start} -> {result.end}")
    print(f"  tickers: {','.join(result.tickers)}")
    print(f"  trades: {int(result.metrics.get('num_trades', 0))}")
    print(f"  total return: {result.metrics.get('total_return', 0):.2%}")
    print(f"  CAGR: {result.metrics.get('cagr', 0):.2%}")
    print(f"  max drawdown: {result.metrics.get('max_drawdown', 0):.2%}")
    print(f"  Sharpe: {result.metrics.get('sharpe', 0):.2f}")
    print(f"  invested Sharpe: {result.metrics.get('invested_sharpe', 0):.2f}")
    print(f"  time in market: {result.metrics.get('time_in_market', 0):.2%}")
    print(f"  hit rate: {result.metrics.get('hit_rate', 0):.2%}")
    print(f"  final equity: ${result.metrics.get('final_equity', 0):,.2f}")


def _serialize_result(result: BacktestResult) -> str:
    obj = result.model_dump(mode="json")
    obj["_generated_at"] = datetime.now().isoformat()
    obj["equity_curve_monthly"] = _monthly_equity(result)
    return json.dumps(obj, indent=2, sort_keys=True)


def _monthly_equity(result: BacktestResult) -> list[dict[str, object]]:
    if not result.equity_curve:
        return []
    by_month: dict[str, tuple[date, float]] = {}
    for point in result.equity_curve:
        key = f"{point.date.year:04d}-{point.date.month:02d}"
        existing = by_month.get(key)
        if existing is None or point.date > existing[0]:
            by_month[key] = (point.date, point.equity)
    return [{"date": d.isoformat(), "equity": eq} for _, (d, eq) in sorted(by_month.items())]


def main() -> int:
    parser = argparse.ArgumentParser(prog="rizq")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="check config + Alpaca paper connectivity")

    ingest = sub.add_parser("ingest", help="ingest market data into the curated zone")
    ingest_sub = ingest.add_subparsers(dest="ingest_cmd", required=True)
    ingest_bars = ingest_sub.add_parser("bars", help="daily OHLCV bars from Databento")
    ingest_bars.add_argument("--start", required=True, help="start date YYYY-MM-DD")
    ingest_bars.add_argument("--end", required=True, help="end date YYYY-MM-DD")
    ingest_bars.add_argument("--tickers", required=True, help="comma-separated tickers")
    ingest_bars.add_argument(
        "--dataset",
        default="XNAS.ITCH",
        help="Databento dataset (XNAS.ITCH for NASDAQ-listed, XNYS.PILLAR for NYSE)",
    )

    bt = sub.add_parser("backtest", help="run a backtest")
    bt.add_argument("signal", help=f"signal name (one of: {sorted(SIGNAL_REGISTRY)})")
    bt.add_argument("--start", required=True)
    bt.add_argument("--end", required=True)
    bt.add_argument("--tickers", required=True)
    bt.add_argument(
        "--data-start",
        default=None,
        help="data window start (defaults to --start minus 365 days for signal pre-warm)",
    )
    bt.add_argument("--golden", action="store_true", help="write/refresh golden fixture")
    bt.add_argument("--out", help="path to write full result JSON")

    args = parser.parse_args()

    if args.cmd == "health":
        return cmd_health()
    if args.cmd == "ingest" and args.ingest_cmd == "bars":
        return cmd_ingest_bars(args)
    if args.cmd == "backtest":
        return cmd_backtest(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
