# Binance Spot Grid Trading Platform

> Local-only automated grid trading bot for **Binance Spot (no leverage)** with an optional **AI-Trader** layer driven by any OpenAI-compatible LLM. Designed for learning and personal use, with a **4-phase testnet → live rollout** and **six hard risk guards**.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-encrypted-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Frontend](https://img.shields.io/badge/Frontend-Vite%20%2B%20TS%20%2B%20Tailwind-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Tests](https://img.shields.io/badge/Tests-129%20passing-brightgreen?logo=pytest&logoColor=white)](#testing)
[![License](https://img.shields.io/badge/License-MIT-lightgrey)](#license)
[![Exchange](https://img.shields.io/badge/Exchange-Binance%20Spot-F0B90B?logo=binance&logoColor=white)](https://www.binance.com/)

A full-stack quantitative-trading workbench that runs entirely on your machine. The classical **grid engine** posts bids/asks across a price band and profits from oscillation; on top of it sits an **AI-Trader** service that polls an LLM each tick, asks for `buy / sell / hold`, and runs the response through **six sequential risk guards** before any order is placed. Live trading is opt-in, gated by a typed confirmation phrase, and starts at deliberately conservative position caps.

## ✨ Features

- **Grid Engine** — classic spot grid with lifecycle, persistence to the `Order` table, and WebSocket-driven market data.
- **AI-Trader** — OpenAI-compatible LLM client (DeepSeek / OpenAI / Moonshot / …) with prompt building, JSON parser, and 6 hard guards.
- **Risk Guards** (`run_all`, short-circuit on first failure): `schema_valid` → `per_order_cap` → `position_cap` → `daily_loss_cap` → `daily_trade_cap` → `symbol_exclusive`.
- **4-Phase Rollout** — Testnet (default) → Live-demo (conservative caps) → Live-full (normal caps). Flipping `testnet=false` alone **does not** arm live trading — a separate typed confirmation is required.
- **State Machine** — `idle → running → {paused | stopped | error}` with `POST /pause`, `/resume`, `/emergency-stop`, `/reset`.
- **Encrypted Credentials** — API keys live in the **OS keyring** (Windows Credential Manager), never in `.env`, logs, or commits.
- **Setup Wizard** — first-run flow that verifies the broker connection before letting the bot touch anything.
- **Web Dashboard** — Vite + TypeScript + Tailwind UI at `http://localhost:5173`.

## 🧱 Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                         Frontend (Vite + TS)                       │
│   Dashboard  ·  Grids  ·  Orders  ·  AI Trader  ·  Settings        │
└────────────────────────────┬───────────────────────────────────────┘
                             │  REST + WebSocket
┌────────────────────────────▼───────────────────────────────────────┐
│                          FastAPI backend                           │
│  routers/  →  services/  →  broker/binance.py  →  SQLite (app.db)  │
│                                                                    │
│  ┌──────────────┐    every 60s    ┌────────────────────────────┐   │
│  │ AI Trader    │ ──────────────► │  6 Guards (short-circuit)  │   │
│  │ service.py   │ ◄────────────── │  → buy / sell / hold       │   │
│  └──────────────┘   parsed JSON   └────────────────────────────┘   │
│                                                                    │
│  ┌──────────────┐                                                  │
│  │ Grid Engine  │  posts limit orders across the price band       │
│  └──────────────┘                                                  │
└────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
                    Binance Spot API (no leverage)
```

## 📑 Table of Contents

- [Quick Start](#quick-start-windows)
- [Configuration](#configuration)
- [Testing](#testing)
- [Architecture & Layout](#architecture)
- [AI Trader — Cold-Start](#ai-trader)
- [Testnet → Live Rollout](#enabling-on-testnet-recommended-first) · [Phase 2 Live-demo](#phase-2--live-demo-conservative-tier) · [Phase 3 Live-full](#phase-3--live-full-raise-caps-to-normal-tier)
- [Emergency Stop & Recovery](#emergency-stop-and-recovery)
- [Six Risk Guards](#six-hard-risk-guards-run-in-order-short-circuit-at-first-failure)
- [Credential Storage](#credential-storage)
- [Reference Projects](#reference-projects)
- [License](#license)

## Quick start (Windows)

1. Clone this repo (or open `D:/bian`).
2. Double-click `run.bat`.
3. Browser opens to `http://localhost:5173` — first time, follow the API key setup wizard.

## Configuration

Settings are stored encrypted in `data/app.db` (via OS keyring). Configure via the UI's **Settings** page; no plaintext keys live in this repo.

## Testing

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pytest -q
```

## Reference projects

The `借鉴/` directory contains 9 open-source projects used as reference. See `借鉴/<repo>/_LICENSE_NOTES.md` for license details per project.

## AI Trader

> **Status:** The backend (`/api/ai-trader/*`) is implemented per `docs/superpowers/specs/2026-09-01-ai-trader-design.md` and tested (129 unit + integration tests passing). The mock UI page is rendered; treating its buttons as illustrative until they are wired to the backend.

### Cold-start state

Right now the OS keyring holds Binance credentials but **no** LLM credentials, so a fresh start reports:

```bash
curl http://localhost:8000/api/ai-trader/status
# → broker_wired: true, llm_wired: false, wiring_ok: false
# → armed_for_live_at: null,  status: idle,  poll_interval_sec: 60
curl -i 'http://localhost:8000/api/ai-trader/dry-run?symbol=BTCUSDT'
# → HTTP/1.1 503  {"detail":"trader_not_wired"}
```

The first step of any hands-on run is wiring LLM credentials. `wiring_ok` only flips to `true` once **both** `broker_wired` and `llm_wired` are `true` — `wiring_ok` is a derived property, not a stored flag.

### Enabling on Testnet (recommended first)

1. **Settings → LLM Configuration.** Provide `Base URL` + `API Key` (any OpenAI-compatible endpoint works: DeepSeek, OpenAI, Moonshot, …). `Model` is optional. Save. The card's badges now read `llm_wired true`.
2. **Settings → API key & Secret.** With `Testnet = on`, paste your Binance testnet API key + secret. Save. Run **Test connection** to confirm.
3. **Open the AI Trader tab.** Review the risk caps displayed in the Risk caps card. Defaults (testnet tier): per-order 50 USDT, per-symbol 500 USDT, daily loss -30 USDT, daily trades 20, symbols `["BTCUSDT"]`, poll 60 s. Edit them via:

   ```bash
   curl -X PUT http://localhost:8000/api/ai-trader/settings \
     -H 'content-type: application/json' \
     -d '{"max_order_quote_usdt": 50, "max_position_per_symbol_usdt": 500, "daily_loss_cap_usdt": -30, "daily_max_trades": 20, "symbols": ["BTCUSDT"]}'
   ```

   `daily_loss_cap_usdt` must be **strictly negative**; `max_order_quote_usdt` and `max_position_per_symbol_usdt` must be **> 0**; `daily_max_trades >= 1`; `poll_interval_sec >= 1`. The router rejects values that would invert a guard.
4. **Click ENABLE AI TRADER.** The service starts polling every 60 s. `GET /api/ai-trader/status` now shows `status: running`.
5. **Watch Logs / Decisions:**

   ```bash
   curl 'http://localhost:8000/api/ai-trader/decisions?limit=50'
   ```

   For the first 30 minutes, watch for `outcome ∈ {placed, rejected, no_trade, error}`.
6. **Let it run 24 h.** Verify P&L stays within caps and no trip fires. Adjust caps only if you have a reason; the defaults are already conservative for testnet.

### Live mode (after Testnet success)

**Design contract: flipping `settings.testnet` from true to false does NOT by itself arm live trading.** Arming is always a separate, explicit act. Each phase below must be advanced deliberately by a human.

#### Phase 0 — Dry-run

Already covered by the wiring work above. Once `wiring_ok: true` you can run:

```bash
curl 'http://localhost:8000/api/ai-trader/dry-run?symbol=BTCUSDT'
```

It does one LLM round-trip + guard preview, **never** places an order, **never** persists an `AIDecision`. The response includes `ok`, `parsed`, and `guard_verdict`.

#### Phase 1 — Testnet (≥ 24 h with no daily-cap trips)

Already documented above. Acceptance: no `daily_loss_cap_hit` / `daily_trades_cap_hit` in the Decisions log for a full day; P&L stays within caps; `placed` orders are reproducible from their `prompt` + `raw_response`.

#### Phase 2 — Live demo (conservative tier)

1. Confirm Phase 1 ran ≥ 24 h with no daily-cap trips.
2. Save real Binance API credentials in **Settings → API key & Secret**, **Testnet = off**. **Do not enable Withdrawals on the Binance API key** — enable trading only. The Settings page never exposes the secret in plaintext; it lives in OS keyring (`binance-spot-grid-bot`, slug `api_secret`).
3. Open the AI Trader tab. Click **ENABLE AI TRADER** — the UI raises a confirmation dialog asking for the exact phrase `I UNDERSTAND REAL MONEY` (case-sensitive, no trimming). Typing it arms the service for live **and downgrades caps to the conservative live tier**:
   - per-order ≤ 20 USDT, per-symbol ≤ 200 USDT
   - daily loss ≥ -10 USDT (i.e. cap is -10, not -30)
   - daily trades ≤ 10

   Implemented in `app/services/ai_trader/service.py` via `min(...)` / `max(...)` — raising before arming makes no difference; arming always reduces caps. This is deliberate. All four caps above are downgraded together at arm time, and a cap you already set **stricter** than the conservative tier is left as-is (arming never raises one).
4. The same confirmation is required on **`POST /api/ai-trader/reset`** when the service is armed for live. From `stopped` or `error`, reset without the phrase is refused with `409 live_arming_required`. When `armed_for_live_at` is null (testnet), reset takes no confirmation — recovering from a transient LLM outage must not demand a real-money incantation.

   ```bash
   curl -X POST http://localhost:8000/api/ai-trader/start \
     -H 'content-type: application/json' \
     -d '{"confirm_text": "I UNDERSTAND REAL MONEY"}'
   ```

5. Run Phase 2 for ≥ 7 days with no `emergency_stop` and no `status=error`. Review the Decisions log daily.

#### Phase 3 — Live full (raise caps to normal tier)

After ≥ 7 days of Phase 2 with no emergency-stop trips:

```bash
curl -X PUT http://localhost:8000/api/ai-trader/settings \
  -H 'content-type: application/json' \
  -d '{"max_order_quote_usdt": 50, "max_position_per_symbol_usdt": 500, "daily_loss_cap_usdt": -30, "daily_max_trades": 20}'
```

Normal-tier defaults: per-order 50 USDT, per-symbol 500 USDT, daily loss -30 USDT, daily trades 20. Raise by **one cap at a time**; never relax the daily loss cap below the value Phase 2 had proven safe.

### Emergency stop and recovery

The service has five states: `idle`, `running`, `paused`, `stopped`, `error`. Transitions:

| From | Trigger | To |
|---|---|---|
| idle | `POST /start` | running |
| running | guard 4 (`daily_loss_cap_hit`) or guard 5 (`daily_trades_cap_hit`) | **paused** (auto, tripwire) |
| running | 5 consecutive LLM errors | **error** (auto, tripwire) |
| running | `POST /emergency-stop` | stopped |
| running | `POST /pause` | paused |
| paused / error | `POST /resume` | running |
| stopped / error | `POST /reset` | idle |

The tripwire transitions are the ones an operator actually hits:

- **Daily loss / trades cap hit** → status becomes `paused`, `status_reason` is `daily_loss_cap_hit` or `daily_trades_cap_hit`. Wait until the next UTC midnight for counters to roll, then `POST /resume` — or `POST /emergency-stop` first if you want a hard freeze.
- **5 consecutive LLM errors** → status becomes `error`, `status_reason` is `consecutive_llm_errors:N`. The tick loop stops doing work entirely: `tick()` returns immediately while `status != "running"`, so no LLM call is made, no market context is gathered, and no decision rows are written until the service is recovered. Investigate the LLM service, then `POST /reset` to clear.
- **`POST /emergency-stop`** → status becomes `stopped`, `status_reason` is `emergency_stopped`. Irreversible from the API side; `POST /reset` is the only way back to `idle`.

Recovery endpoints, in plain curl:

```bash
# Free a real-money-capable service from stopped/error. The body is required
# only when armed_for_live_at is set; in testnet the body can be omitted.
curl -X POST http://localhost:8000/api/ai-trader/reset \
  -H 'content-type: application/json' \
  -d '{"confirm_text": "I UNDERSTAND REAL MONEY"}'

# Resume a paused/error service (no confirmation needed).
curl -X POST http://localhost:8000/api/ai-trader/resume
```

### Six hard risk guards (run in order, short-circuit at first failure)

Inside `app/services/ai_trader/guards.py::run_all`, each tick evaluates:

| # | Guard | Pass condition |
|---|---|---|
| 1 | `schema_valid` | `action ∈ {buy, sell, hold}`; types sane |
| 2 | `per_order_cap` | `qty * price ≤ max_order_quote_usdt` (holds skipped) |
| 3 | `position_cap` | current base × price + buy notional ≤ `max_position_per_symbol_usdt` (sells always pass) |
| 4 | `daily_loss_cap` | `pnl_today ≥ daily_loss_cap_usdt` — fire routes status to `paused` |

Note on `pnl_today` in `/api/ai-trader/status`: it is a cash-flow proxy (revenue of today's `placed` sells minus cost of today's `placed` buys), not realised net P&L — commissions (Binance spot taker ~0.1%) are not subtracted, and cost is the order's price rather than the eventual fill average — so the response carries `pnl_basis: "cash_flow_unadjusted_for_fees"` to make that explicit.
| 5 | `daily_trade_cap` | `trades_today < daily_max_trades` — fire routes status to `paused` |
| 6 | `symbol_exclusive` | no open GridTrader orders for this symbol — keeps AI Trader and GridTrader from stacking on the same pair |

The first failure short-circuits `run_all` and the decision is recorded as `outcome: rejected`. Guards 2 and 3 reject per-tick only; guards 4 and 5 also trip the service.

### Credential storage

All secrets go through OS keyring (Windows Credential Manager). Service name: `binance-spot-grid-bot`. Slugs:

| Slug | Used for |
|---|---|
| `api_key` | Binance API key |
| `api_secret` | Binance API secret |
| `llm_base_url` | LLM endpoint base URL |
| `llm_api_key` | LLM API key |
| `llm_model` | LLM model name (optional) |

Precedence on lookup (`app/main.py` lifespan): keyring first, then `app.config` (`pydantic-settings` reading `.env`), then empty. The Settings UI is the only sanctioned write path — never paste keys into a chat, a log, a commit, or any file in the repo.

## License

MIT — see `LICENSE`. The bundled `借鉴/` reference projects retain their original licenses; consult each subfolder before redistribution.

## ⚠️ Disclaimer

This software is for **educational and personal use only**. Cryptocurrency trading carries significant financial risk. The author is not responsible for any losses incurred while using this tool. Always start on **testnet**, run for at least 24 hours, and never trade with funds you cannot afford to lose. Do **not** enable Withdrawals on any API key you paste into the Settings page.