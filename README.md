# rizq

Semi-autonomous swing trading engine. See `trading_engine.md` for the design spec.

## Setup (local)

```bash
brew install uv
cp .env.example .env  # fill in Alpaca paper keys
uv sync
uv run rizq health    # smoke-test config + Alpaca paper connection
uv run uvicorn rizq.api:app --reload
```

## Deploy

Push to `main` on GitHub. The build workflow:
1. Builds a `linux/arm64` image.
2. Pushes `ghcr.io/rafikee/rizq:latest` and `:<sha>`.
3. Triggers Coolify on baradapi to pull and redeploy.

Required GitHub secrets:
- `COOLIFY_API_TOKEN`
- `COOLIFY_RIZQ_UUID`  (the app UUID Coolify assigns when you create the app)

Required Coolify env vars (set in Coolify's UI, not in the repo):
- `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`
- `ALPACA_BASE_URL=https://paper-api.alpaca.markets`
- `RIZQ_MODE=paper`

Coolify must mount a persistent volume at `/data`.
