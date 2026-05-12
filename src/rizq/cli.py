import argparse
import sys
from typing import cast

from alpaca.trading.client import TradingClient
from alpaca.trading.models import TradeAccount

from rizq.config import get_settings
from rizq.logging_setup import setup_logging


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


def main() -> int:
    parser = argparse.ArgumentParser(prog="rizq")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health", help="check config + Alpaca paper connectivity")
    args = parser.parse_args()

    if args.cmd == "health":
        return cmd_health()
    return 1


if __name__ == "__main__":
    sys.exit(main())
