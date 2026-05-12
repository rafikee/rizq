from typing import Any, cast

import structlog
from alpaca.trading.client import TradingClient
from alpaca.trading.models import TradeAccount
from fastapi import FastAPI, HTTPException

from rizq import __version__
from rizq.config import get_settings
from rizq.logging_setup import setup_logging

settings = get_settings()
setup_logging(settings.log_level)
log = structlog.get_logger()

app = FastAPI(title="rizq", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": settings.rizq_mode, "version": __version__}


@app.get("/alpaca/health")
def alpaca_health() -> dict[str, Any]:
    try:
        client = TradingClient(
            api_key=settings.alpaca_paper_api_key,
            secret_key=settings.alpaca_paper_secret_key,
            paper=True,
        )
        account = cast(TradeAccount, client.get_account())
    except Exception as e:
        log.error("alpaca_health_failed", error=str(e))
        raise HTTPException(status_code=503, detail=f"alpaca unreachable: {e}") from e

    log.info("alpaca_health_ok", account_id=str(account.id), status=str(account.status))
    return {
        "status": "ok",
        "paper": True,
        "account_status": str(account.status),
        "buying_power": float(account.buying_power or 0),
        "equity": float(account.equity or 0),
    }
