# Binance Spot Grid + AI-Trader Platform

> Local-only automated trading bot for **Binance Spot (no leverage)**. Classical grid engine plus an **AI-Trader** layer driven by any OpenAI-compatible LLM, designed to run **24/7 unattended** with strict risk discipline. Built as both a usable personal tool and a demoable platform for quant-system interviews.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-encrypted-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Frontend](https://img.shields.io/badge/Frontend-Vite%20%2B%20TS%20%2B%20Tailwind-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Tests](https://img.shields.io/badge/Tests-193%20passing-brightgreen?logo=pytest&logoColor=white)](#testing)
[![License](https://img.shields.io/badge/License-MIT-lightgrey)](#license)
[![Exchange](https://img.shields.io/badge/Exchange-Binance%20Spot-F0B90B?logo=binance&logoColor=white)](https://www.binance.com/)

A full-stack quantitative-trading workbench that runs entirely on your machine. A **classical grid engine** posts bids/asks across a price band and profits from oscillation; on top of it sits an **AI-Trader** service that polls an LLM each tick, asks for `buy / sell / hold`, and runs the response through **six sequential risk guards** before any order is placed. Live trading is opt-in, gated by a typed confirmation phrase, and starts at deliberately conservative caps. Replayable backtests emit a static HTML report you can hand a recruiter without a build step.

## ✨ What's shipped

| Area | What it does | Tests |
|---|---|---|
| **Grid Engine** | Classic spot grid with lifecycle, persistence to the `Order` table, WebSocket-driven market data | covered by service integration tests |
| **AI-Trader** | LLM-driven decisions, 6 hard risk guards, 4-phase live rollout (`testnet → live demo → live full`) | `tests/integration/test_ai_trader_*.py` |
| **Paper/Live isolation** (P0-1) | `AIDecision.is_paper` column partitions paper P&L from the live daily counters — paper losses cannot trip the live `daily_loss_cap` | `tests/integration/test_paper_live_isolation.py` |
| **Background scheduler** (P0-2) | `AITraderScheduler` drives `tick()` at `poll_interval_sec` with a 30s per-tick timeout, exception-tolerant, cleanly stoppable | `tests/integration/test_ai_trader_scheduler.py` |
| **Structured logs + trace_id** (P0-3) | Every log line is single-line JSON with `ts / level / logger / message / trace_id`. Each tick binds a fresh id so a bug reported weeks later is `grep trace_id=<id>` away | `tests/unit/test_trace_and_logging.py` |
| **FallbackLLM** (P0-4) | Multi-provider LLM chain. Trips to next provider on HTTP error / empty response / parse failure (model degradation included). Active provider visible via `/status` | `tests/unit/test_fallback_llm.py` |
| **Windows Service wrapper** (P0-4) | `scripts/windows_service.py` runs uvicorn as a supervised subprocess under the SCM, auto-restart on crash, terminate-then-kill on stop | `tests/unit/test_windows_service.py` |
| **Backtest engine** (P0-5) | `ReplayLLM` replays stored `AIDecision.raw_response` at zero LLM cost. `HistoricalBroker` answers the Broker interface from frozen K-lines + a virtual ledger. Runner emits a framework-free HTML report to `docs/backtests/` | `tests/unit/test_backtest.py` |

## 🧱 Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                          FastAPI + Vite/TS                         │
│   Dashboard  ·  Grids  ·  Orders  ·  AI Trader  ·  Settings        │
└────────────────────────────┬───────────────────────────────────────┘
                             │  REST + WebSocket + Bearer token
┌────────────────────────────▼───────────────────────────────────────┐
│                       AITraderScheduler  (P0-2)                    │
│   polls tick() at poll_interval_sec · 30s timeout · recovers      │
└────────────────────────────┬───────────────────────────────────────┘
                             │
┌────────────────────────────▼───────────────────────────────────────┐
│                  Singleton: AITraderService                       │
│   state machine: idle ──start──▶ running ──trip──▶ paused/error   │
│                       ◀──reset── stopped    ◀──emergency_stop──   │
│                                                                     │
│   tick(symbols):  ┌─────────────────────────────────────────────┐ │
│   trace_id bound  │ context.gather (4 fields) ─▶ prompt          │ │
│                   │         │                       │            │ │
│                   │         ▼                       ▼            │ │
│                   │   price + klines +      system + user msgs   │ │
│                   │   balances + orders                           │ │
│                   └─────────┬────────────────────────────────────┘ │
│                             ▼                                     │
│       FallbackLLM.chat (P0-4) ─▶ parser ─▶ guards.run_all() ─▶ ... │
│       [primary]─fallback─[secondary]─...   6 sequential guards     │
│       trips on HTTP / empty / parse failure                       │
└────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
                    Binance Spot API (no leverage)
```

Risk guards in order (`app/services/ai_trader/guards.py::run_all`, short-circuit on first failure):
1. `schema_valid` — action ∈ {buy, sell, hold}, types sane
2. `per_order_cap` — `qty * price ≤ max_order_quote_usdt`
3. `position_cap` — current base × price + buy notional ≤ `max_position_per_symbol_usdt`
4. `daily_loss_cap` — `pnl_today ≥ daily_loss_cap_usdt` (routes status to `paused`)
5. `daily_trade_cap` — `trades_today < daily_max_trades` (routes status to `paused`)
6. `symbol_exclusive` — no open GridTrader orders for this symbol (prevents stacking)

## 🚀 Quick start (Windows)

1. Clone this repo (or open `D:/bian`).
2. Double-click `run.bat`. Browser opens to `http://localhost:5173`.
3. First time: follow the API-key setup wizard. Keys are stored encrypted in the **OS keyring** (Windows Credential Manager), never in `.env` or the repo.

For 24/7 unattended operation (auto-start on boot, restart on crash):

```cmd
pip install pywin32
python scripts/windows_service.py install
python scripts/windows_service.py start
```

## 🧪 Testing

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pytest -q
```

Current suite: **193 tests** across `tests/unit/` and `tests/integration/`.

For the AI Trader backtest demo:

```bash
pytest tests/unit/test_backtest.py -v
# Then: docs/backtests/backtest-YYYYMMDD-HHMMSS-xxxxxx.html
```

## 📊 Backtest demo

Run the backtest against recorded live decisions:

```python
from app.backtest.runner import run_backtest

result = run_backtest(
    klines_by_symbol={"BTCUSDT": klines},
    symbol_info={"BTCUSDT": exchange_info},
    ai_decision_rows=aidecision_rows,  # from AIDecision table
    symbols=["BTCUSDT"],
    report_dir="docs/backtests/",
)
print(result.report_path)  # framework-free HTML, opens offline
```

The report contains summary tiles (final equity / total return / Sharpe / max DD / win rate), an ASCII equity curve, and the last 50 fills. Recruiter-friendly: click the link, the page renders, no build step.

## 🛡️ Risk philosophy

- **Never request margin / futures / options** — spot only, hard-coded into the system prompt and the parser.
- **Six sequential guards** short-circuit on the first failure. Guards 4 and 5 also trip the service into `paused` state; guards 2 and 3 reject per-tick only.
- **Live-arming gate** — flipping `testnet=false` does NOT by itself arm live trading. `armed_for_live_at` is set only when the operator types the exact phrase `I UNDERSTAND REAL MONEY`. The phrase is required on `POST /start` (first arming) and `POST /reset` (recovery when already armed), per `app/services/ai_trader/service.py`.
- **Conservative live tier** — arming the service for live caps per-order ≤ 20 USDT, per-symbol ≤ 200 USDT, daily loss ≥ -10 USDT, daily trades ≤ 10. Raising these caps is a separate explicit step.
- **Paper/live isolation** (P0-1) — paper-trading rows carry `is_paper=True` and the daily counters filter by environment. A bad paper morning cannot halt live trading.
- **FallbackLLM** (P0-4) — single-provider LLM is the biggest 24h risk. The chain trips on HTTP error, empty response, AND parse failure (model degradation). `wiring_ok` and `active_provider_url` are exposed via `/status`.

## 🗺️ Roadmap

The CEO plan (`docs/superpowers/`) defines three tiers of work. This branch ships **all of P0** — the production-readiness foundation. The remaining items (P1+ P2+) build breadth.

| Tier | Status | Items |
|---|---|---|
| **P0 — Production foundation** | ✅ shipped | paper/live isolation · background scheduler · JSON logs + trace_id · FallbackLLM · Windows Service · backtest HTML |
| **P1 — Multi-source signals** | ⏳ next | SignalSource abstraction + Health · Regime (funding / OI) · Technicals (8 indicators) · PaperBroker |
| **P2 — Demo surface** | ⏳ | News signal (CryptoPanic, default off) · Metrics dashboard with [Backtest][Paper][Live] tabs |
| **P3 — Hardening** | ⏳ | Local Bearer token auth · Daily DB backup · Audit log privacy |

Plan source: `docs/superpowers/plans/2026-09-01-ai-trader.md`, design spec `docs/superpowers/specs/2026-09-01-ai-trader-design.md`.

## 🧰 Reference projects

The `借鉴/` directory at one point held nine cloned open-source projects used as reference. They are intentionally **not tracked** in this repo — see `.gitignore` (`借鉴/` line) — and stay on your local disk for study only. License attribution is preserved in each cloned subdirectory's own `_LICENSE_NOTES.md` file.

## ⚠️ Disclaimer

This software is for **educational and personal use only**. Cryptocurrency trading carries significant financial risk. The author is not responsible for any losses incurred while using this tool. Always start on **testnet**, run for at least 24 hours, and never trade with funds you cannot afford to lose. Do **not** enable Withdrawals on any API key you paste into the Settings page.
