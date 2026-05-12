# Rizq — Swing Trading Engine

*Rizq* (رزق): provision, sustenance — what is allotted to you. The project is a tool for compounding that provision through disciplined participation in the equity markets, not a get-rich engine.

## Source of truth

`trading_engine.md` (repo root) is the canonical design document. Architecture, layer contracts, philosophy, scope, and the incremental build path all live there. **Always re-read it before proposing structural changes.** If a request conflicts with the spec, surface the conflict instead of silently picking a side — the spec wins by default, but the spec is also a living document and worth updating when reality teaches us better.

Section 19 ("Open Questions") lists decisions explicitly deferred. When work touches one of those, name it — don't quietly pick a default.

---

## Hard rules — these are not negotiable

1. **Paper trading only.** `ALPACA_BASE_URL` must point at the paper endpoint. Live credentials are not stored in this repo and not used by any code path. Any change to broker config requires explicit confirmation from the user, every time.
2. **Never place real orders during development or testing.** Not on paper, not on live. Tests mock the broker. Smoke tests against paper require the user to ask for them by name.
3. **Human approves every transaction in live mode** — without exception, forever, until the user explicitly removes the rule. The Approval Queue (spec §10) is the chokepoint.
4. **No options. No shorting. No leverage beyond what an Alpaca margin account permits on long equity.** These are scope boundaries from spec §2 — do not propose features that violate them.
5. **No live trading code paths exist yet.** When live mode is eventually added, it must be gated behind an explicit config flag *and* a separate credentials file that doesn't exist by default.

---

## How to collaborate with me

I'm a Python developer and a trader, but **learning in both areas**. I want a thoughtful collaborator, not an order-taker.

- **Push back.** On trading approaches, code design, testing strategy, risk management — all of it. If a rule I'm proposing contradicts the spec's philosophy (asymmetric payoffs, cut losses fast, point-in-time correctness, regime as multiplier-not-gate), say so. If a code pattern is going to bite us in six months, say so.
- **Explain the trade-off.** When you push back, give me the alternative and the reason. I'm here to learn, not just to be corrected.
- **Two domains, equal weight.** I need pushback on the *trading* as much as the *coding*. A clean implementation of a bad rule is still a bad rule.
- **Surface open questions early.** If a piece of work depends on something in spec §19 ("Open Questions"), call it out before writing code.

---

## Sub-agents — use them, don't pretend to be them

Five specialized review agents live in `.claude/agents/`. They're read-only and give focused expert pushback. Invoke them by name (or let the harness pick) when their domain comes up.

| Agent | Invoke when |
|---|---|
| `technical-analyst` | designing or modifying technical setup logic, Minervini/Weinstein/VCP rules, RS calculations, entries/stops/targets, base-pattern detection |
| `fundamental-analyst` | designing or modifying CANSLIM screens, fundamental scoring, earnings/sales acceleration logic, financial-statement features |
| `macro-analyst` | designing or modifying the Regime Engine, sector macro scores, breadth/credit/volatility/policy components, regime-conditioned behavior |
| `backtest-auditor` | reviewing backtests, signal evaluation, or anything where look-ahead bias, survivorship bias, or point-in-time correctness could creep in |
| `execution-safety-reviewer` | **mandatory** before any change to broker-facing code, order routing, mode flags, credential handling, or anything that could mutate an Alpaca account |

Each is a *reviewer*, not an implementer. I (main Claude) write the code; they critique it.

---

## Trading principles to honor at all times (spec §3 distilled)

1. **Cut losses fast, let winners run.** Initial stops are rigid; trailing stops are generous. Many small losses are fine; giving back a big winner is not.
2. **Macro gates behavior, not ideas.** The regime engine decides *whether* and *how aggressively* to trade. It does not filter individual stock candidates.
3. **Macro tailwinds amplify conviction**, they don't gate it.
4. **Point-in-time correctness.** Every datum carries `as_of` (when it refers to) and `observed_at` (when we learned it). Backtests use only what was available at decision time.
5. **Stable contracts, disposable implementations.** Schemas (Watchlist Row, ThemeScore, RegimeReading) are versioned. Implementations behind them are free to evolve.
6. **One codebase for live and backtest.** Same signal functions in both. No parallel backtest codepath.
7. **Kill switches are primary features**, not afterthoughts.
8. **Layered human oversight.** Every recommendation carries human-readable `reasons` and `flags`.

---

## Tech stack

Opinionated and chosen — not the only valid picks, but consistent picks. Don't introduce alternatives without flagging it.

- **Python 3.13** (slim base image).
- **uv** for env management and dependency locking. `uv.lock` is committed.
- **ruff** for lint + format. **mypy --strict** for types. **pytest** for tests.
- **pydantic v2** for all schemas (Watchlist Row, ThemeScore, RegimeReading, config) and settings.
- **SQLAlchemy 2.0 + Alembic** for the stateful tables (orders, fills, positions, journal, signals_log, regime_log, audit_log). Backing store: SQLite at `/data/rizq.db` (mounted volume in production).
- **DuckDB + Parquet** for the analytical/feature zones (price history, watchlist snapshots, computed features). Partition Parquet by date.
- **alpaca-py** for the broker (paper).
- **structlog** for structured logging. JSON in production, console-friendly in dev.
- **httpx** for HTTP. **tenacity** for retries on ingestion.
- **Streamlit** for the first dashboard.

---

## Repository structure (target — build incrementally)

```
rizq/
├── trading_engine.md           # source of truth
├── CLAUDE.md
├── .claude/agents/             # sub-agent definitions
├── pyproject.toml              # uv-managed
├── uv.lock
├── Dockerfile
├── .github/workflows/build.yml # → ghcr.io → Coolify
├── .env.example                # never commit a real .env
├── alembic.ini
├── migrations/                 # alembic migrations
├── src/rizq/
│   ├── config/                 # pydantic settings, yaml loaders
│   ├── data/                   # ingestion + storage (raw/curated/feature zones)
│   ├── funnel/                 # per-stock funnel (universe, RS, fundamentals, technical, event scrub)
│   ├── theme/                  # sector/industry macro scores
│   ├── catalyst/               # event stream
│   ├── watchlist/              # Watchlist Row assembly + versioned schema
│   ├── regime/                 # regime engine
│   ├── decision/               # thin orchestrator: filters, sizing, heat, correlation
│   ├── approval/               # approval queue
│   ├── execution/              # broker abstraction (alpaca first)
│   ├── state/                  # SA models, journal, audit
│   ├── backtest/               # uses same signal funcs as live
│   ├── monitoring/             # alerts + dashboard
│   └── cli.py                  # entrypoints
├── tests/
└── scripts/                    # one-off ops scripts
```

Build follows spec §17 phases. Don't sprint ahead — each phase must leave the system in a working state.

---

## Deployment framework (mirrors `nahw`)

Production runs on `baradapi` (Raspberry Pi) under Coolify. The flow:

1. Commit to `main` on GitHub.
2. `.github/workflows/build.yml` builds a `linux/arm64` image, pushes `ghcr.io/rafikee/rizq:latest` and `:<sha>`.
3. Workflow hits Coolify's deploy webhook → Coolify pulls and redeploys.
4. SQLite database is on a `/data` volume that Coolify mounts. Survives redeploys.
5. Secrets are set in Coolify's UI as env vars. Locally they live in `.env` (gitignored).

When building/debugging the deployment side, reference `https://github.com/rafikee/nahw` — its Dockerfile and workflow are the template. The Pi can be inspected directly via `ssh baradapi`.

For local dev: `uv run` everything. SQLite at `./data/rizq.db`. `.env` from `.env.example`.

---

## Reference codebase: `souptrader`

`https://github.com/rafikee/souptrader` is the user's existing trade-performance tracker. **It is not what we're building** — it tracks completed trades; rizq generates and manages them. But it has useful real-world pieces:

- Working Alpaca account integration and credential pattern.
- SQLite schema for trade history (peewee — we use SA, so adapt don't copy).
- Cron-driven update scripts.
- Trading P&L summarization logic.

When relevant, look there before reinventing — but adapt to rizq's conventions. Do not vendor it as a dependency.

---

## Workflow

- **Git**: commit directly to `main`. Keep it simple. No PRs required.
- **Tests**: run `uv run pytest` after meaningful changes. Don't run tests that would hit the broker.
- **Lint/types**: `uv run ruff check`, `uv run ruff format`, `uv run mypy src/` after meaningful changes.
- **Migrations**: every state-table change comes with an Alembic migration. Never edit the DB schema by hand.
- **Versioning the contracts**: when a Watchlist Row / ThemeScore / RegimeReading schema changes, bump its `*_version` and write a migration note in the model docstring.

---

## A note on the model's training data

Modern Python tooling moves fast. Default to checking package versions and docs (`uv pip show <pkg>`, `pyproject.toml`) before writing code for any third-party library — especially `alpaca-py`, `pydantic v2`, `SQLAlchemy 2.0`, and Alembic, all of which have meaningfully different APIs from older majors.

The trading literature (CANSLIM, Minervini, Weinstein, O'Neil) is broadly stable, but specific thresholds in popular write-ups are not gospel — backtest before adopting.
