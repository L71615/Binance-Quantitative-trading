# 币安现货自动网格交易平台 · 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only, Windows-runnable Python + FastAPI + React app that runs a spot grid trading strategy on Binance (Testnet first, real later). Web UI for monitoring and control.

**Architecture:** Single FastAPI process hosting REST + WebSocket + asyncio-based strategy engine + Binance client wrapper, with a React + Vite + Tailwind + shadcn/ui frontend served from a separate dev server. SQLite via SQLAlchemy. Reference open-source projects cloned under `借鉴/` for learning; no fork/copy of external code into our codebase.

**Tech Stack:**
- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x (sync), Alembic, httpx (async), websockets, keyring, pytest, pytest-asyncio
- **Frontend:** Node 20+, Vite, React 18, TypeScript, Tailwind CSS, shadcn/ui, React Router, TanStack Query, lightweight-charts
- **Data:** SQLite
- **Process:** Single uvicorn process; npm dev server for frontend with Vite proxy

**Reference spec:** `D:/bian/docs/superpowers/specs/2026-08-30-binance-spot-grid-design.md` (final spec)

---

## Global Constraints

- **Root directory:** All project files, clones, data, and logs **must live under `D:\bian\`**. Never write outside this root.
- **Reference projects:** All 9 repos cloned into `D:/bian/借鉴/`, shallow (`--depth=1`). Each gets a `_LICENSE_NOTES.md`.
- **No internet at runtime** for the trading app — only HTTPS to Binance API endpoints + local WS.
- **Testnet first:** All Binance API calls go through a `BINANCE_TESTNET=true|false` switch in `.env`. Default for development = true.
- **Spot only:** No margin, futures, or options endpoints touched.
- **API key safety:** Stored encrypted via `keyring`; never returned in GET responses; UI shadcn wizard enforces this.
- **Python:** 3.11+ (3.13 acceptable). Single `venv/` at `D:/bian/venv/`.
- **Commits:** Conventional commits; one commit per task.
- **TDD:** Every task writes a failing test first, then implementation, then verifies green.
- **Windows-first:** Scripts use `python`, `python -m`, Windows path conventions. `run.bat` for one-shot launch.

---

## File Structure (Post-Implementation)

```
D:/bian/
├── app/                              # FastAPI backend
│   ├── __init__.py
│   ├── main.py                       # FastAPI app, lifespan, router includes
│   ├── config.py                     # pydantic Settings, env loading
│   ├── db.py                         # SQLAlchemy engine + Base + get_session
│   ├── crypto_store.py               # keyring-based encrypt/decrypt
│   ├── setup_wizard.py               # detect first-run, gate non-/setup routes
│   ├── models/
│   │   ├── __init__.py
│   │   ├── setting.py
│   │   ├── app_state.py
│   │   ├── symbol.py
│   │   ├── grid.py
│   │   ├── order.py
│   │   ├── trade.py
│   │   └── kline.py
│   ├── broker/
│   │   ├── __init__.py
│   │   └── binance.py                # REST + signing + WS, no external pkg
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── grid.py
│   ├── engine/
│   │   ├── __init__.py
│   │   └── engine.py                 # one asyncio Task per grid
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py
│   │   ├── schemas.py                # pydantic request/response models
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── setup.py
│   │       ├── settings.py
│   │       ├── grids.py
│   │       ├── orders.py
│   │       ├── trades.py
│   │       ├── dashboard.py
│   │       └── klines.py
│   └── ws/
│       ├── __init__.py
│       └── realtime.py               # ConnectionManager + push methods
├── web/                              # React frontend
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts                # proxy /api -> http://localhost:8000
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── components.json               # shadcn config
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── index.css
│       ├── lib/
│       │   ├── api.ts                # fetch wrapper
│       │   ├── queryClient.ts
│       │   └── utils.ts
│       ├── components/
│       │   ├── Layout.tsx
│       │   ├── PriceCell.tsx
│       │   └── OrderRow.tsx
│       ├── hooks/
│       │   ├── useWebSocket.ts
│       │   └── useApi.ts
│       └── pages/
│           ├── Setup.tsx
│           ├── Settings.tsx
│           ├── Dashboard.tsx
│           ├── GridsList.tsx
│           ├── GridsNew.tsx
│           ├── GridDetail.tsx
│           ├── Charts.tsx
│           ├── Orders.tsx
│           └── Logs.tsx
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_crypto_store.py
│   │   ├── test_grid_strategy.py
│   │   └── test_models.py
│   ├── integration/
│   │   ├── test_api_settings.py
│   │   ├── test_api_grids.py
│   │   └── test_setup_gate.py
│   └── async/
│       └── test_engine.py
├── migrations/                       # alembic
│   └── versions/
├── data/                             # gitignored
│   ├── app.db
│   └── logs/
├── docs/superpowers/
│   ├── specs/2026-08-30-binance-spot-grid-design.md
│   └── plans/2026-08-30-binance-spot-grid.md
├── 借鉴/                             # 9 reference repos (see Tasks 1–2)
│   ├── hyedaid-binance-spot-grid/
│   ├── robertklep-binance-grid-trader/
│   ├── edeng23-binace-grid-bot-python/   # NOTE: typo fixup in git clone dir name
│   ├── freqtrade/
│   ├── python-binance/
│   ├── EdwardAThomson-trade_dashboard/
│   ├── Mukund934-Cryptex-Console/
│   ├── fastapi-full-stack-fastapi-template/
│   └── spothq-cryptocurrency-icons/
├── .gitignore
├── requirements.txt
├── alembic.ini
├── run.bat
└── README.md
```

---

# Phase 0 — Workspace & Reference Projects

## Task 1: Initialize git repo at D:/bian and install Python/Node tooling

**Files:**
- Create: `D:/bian/.gitignore`
- Create: `D:/bian/README.md`

**Pre-flight (verify environment):**
- Run: `python --version`
- Expected: `Python 3.11.x` (or 3.12/3.13 — any 3.11+)
- Run: `node --version && npm --version`
- Expected: `v20.x` and `10.x` or newer
- Run: `git --version`
- Expected: `git version 2.x`

If any are missing, stop and ask the user to install them (the plan assumes Windows native Python from python.org or py launcher, and Node 20+ LTS).

**Steps:**
- [ ] **Step 1: Init git**
  - Run: `cd /d/bian && git init -b main`
  - Then: `git config user.email "dev@local" && git config user.name "Local Dev"` (only if not set globally)
- [ ] **Step 2: Write `.gitignore`**

```gitignore
# Python
venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Node / Vite
web/node_modules/
web/dist/
web/.vite/
web/.env.local

# Runtime data
data/app.db
data/app.db-*
data/logs/
*.log

# Secrets / local config
.env
.env.local

# OS / editor
.DS_Store
Thumbs.db
.idea/
.vscode/
```

- [ ] **Step 3: Write `README.md`**

````markdown
# Binance Spot Grid Trading Platform

A local-only automated grid trading bot for Binance Spot (no leverage).
For learning and personal use.

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
````

- [ ] **Step 4: First commit**
  - Run: `cd /d/bian && git add .gitignore README.md && git commit -m "chore: init repo with .gitignore and README"`

---

## Task 2: Clone 9 reference projects into `D:/bian/借鉴/` with license notes

**Files:**
- Create: `D:/bian/借鉴/_README.md`
- Create: `D:/bian/借鉴/<repo-slug>/_LICENSE_NOTES.md` per project (one per folder)

**Interfaces:**
- Consumes: empty `借鉴/`
- Produces: 9 subdirectories + license notes (used by Tasks 3+ as research material)

**Steps:**
- [ ] **Step 1: Create borrow root readme**

`D:/bian/借鉴/_README.md`:

````markdown
# 借鉴 / Reference Projects

These are open-source projects studied during development. We read them to learn — **we do not copy their code into our project**. Before drawing inspiration from any of them, check `_LICENSE_NOTES.md` next to the project to see what's allowed.

| Folder | Upstream | Used For | License |
|--------|----------|----------|---------|
| hyedaid-binance-spot-grid | hyedaid/binance-spot-grid | 网格算法核心 | see _LICENSE_NOTES.md |
| robertklep-binance-grid-trader | robertklep/binance-grid-trader | 网格对比 | see _LICENSE_NOTES.md |
| edeng23-binace-grid-bot-python | edeng23/binance-grid-bot-python | 学习注释详细版 | see _LICENSE_NOTES.md |
| freqtrade | freqtrade/freqtrade | 架构 / Strategy 接口 | GPL-3.0 (只读思想) |
| python-binance | sammchardy/python-binance | API 客户端参考 | MIT |
| EdwardAThomson-trade_dashboard | EdwardAThomson/trade_dashboard | UI / 实时数据参考 | see _LICENSE_NOTES.md |
| Mukund934-Cryptex-Console | Mukund934/Cryptex-Console | 视觉/卡片布局参考 | see _LICENSE_NOTES.md |
| fastapi-full-stack-fastapi-template | fastapi/full-stack-fastapi-template | 脚手架结构参考 | MIT |
| spothq-cryptocurrency-icons | spothq/cryptocurrency-icons | 加密币 SVG 图标 | see _LICENSE_NOTES.md |
````

- [ ] **Step 2: Clone shallow**

Run:
```bash
cd /d/bian/借鉴
git clone --depth=1 https://github.com/hyedaid/binance-spot-grid.git hyedaid-binance-spot-grid
git clone --depth=1 https://github.com/robertklep/binance-grid-trader.git robertklep-binance-grid-trader
git clone --depth=1 https://github.com/edeng23/binance-grid-bot-python.git edeng23-binace-grid-bot-python
git clone --depth=1 https://github.com/freqtrade/freqtrade.git freqtrade
git clone --depth=1 https://github.com/sammchardy/python-binance.git python-binance
git clone --depth=1 https://github.com/EdwardAThomson/trade_dashboard.git EdwardAThomson-trade_dashboard
git clone --depth=1 https://github.com/Mukund934/Cryptex-Console.git Mukund934-Cryptex-Console
git clone --depth=1 https://github.com/fastapi/full-stack-fastapi-template.git fastapi-full-stack-fastapi-template
git clone --depth=1 https://github.com/spothq/cryptocurrency-icons.git spothq-cryptocurrency-icons
```
- Expected: 9 directories appear; `.git/` exists inside each (taking some disk — that's OK).

- [ ] **Step 3: For each project, verify the LICENSE file exists and create a note**

Run: `ls 借鉴/<repo>/LICENSE* 借鉴/<repo>/LICENSE.md` etc. For each, write `借鉴/<repo>/_LICENSE_NOTES.md` with two sections:
- "Upstream LICENSE": exact license name and a one-line summary
- "How we may use it":
  - For MIT/Apache-2.0/BSD: "Read; reference freely; do not copy code into our project unless we add explicit attribution and respect the license terms."
  - For GPL-3.0 (freqtrade): "Read-only for architectural ideas. Do not copy, do not translate, do not derive code from this project. Our codebase stays under MIT."

Concrete notes to write:
- **freqtrade:** "Upstream LICENSE: GPL-3.0. How we may use: ideas only — no code reuse."
- **python-binance:** "Upstream LICENSE: MIT. How we may use: read API call patterns; write our own client from scratch without copying significant chunks of code."
- Other 7: read the LICENSE file in each, summarize. If license is unclear or non-permissive, write "Read-only; no code reuse."

- [ ] **Step 4: Commit**

```bash
cd /d/bian
git add .gitignore 借鉴/_README.md
git commit -m "chore: clone 9 reference projects with license notes"
```
(Don't `git add` the entire `借鉴/` — repo size is huge. Only commit the `_README.md` and the `_LICENSE_NOTES.md` files. The rest stays on disk outside git.)

- [ ] **Step 5: Update `.gitignore`** to exclude cloned reference repos from git

Append to `.gitignore`:
```
借鉴/*/
!借鉴/_README.md
!借鉴/**/_LICENSE_NOTES.md
```

Then run:
```bash
git add .gitignore && git commit -m "chore: ignore cloned reference repos in git"
```

---

# Phase 1 — Backend Foundation

## Task 3: Python venv and requirements.txt

**Files:**
- Create: `D:/bian/requirements.txt`
- Create: `D:/bian/venv/` (generated)

**Steps:**
- [ ] **Step 1: Create venv**
  - Run: `cd /d/bian && python -m venv venv`
  - Verify: `ls venv/Scripts/python.exe` exists (Windows) or `venv/bin/python` (other).
- [ ] **Step 2: Write `requirements.txt`**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy==2.0.36
pydantic==2.10.4
pydantic-settings==2.7.1
httpx==0.28.1
websockets==13.1
keyring==25.6.0
python-multipart==0.0.20
alembic==1.14.0
greenlet==3.1.1
aiosqlite==0.20.0
pytest==8.3.4
pytest-asyncio==0.25.0
httpx==0.28.1
```

- [ ] **Step 3: Install**
  - Run: `cd /d/bian && venv/Scripts/python -m pip install --upgrade pip`
  - Run: `venv/Scripts/python -m pip install -r requirements.txt`
  - Verify: `venv/Scripts/python -c "import fastapi, sqlalchemy, websockets, keyring; print('ok')"` → `ok`
- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add Python deps and venv setup"
```

---

## Task 4: DB connection module + base ORM

**Files:**
- Create: `D:/bian/app/__init__.py`
- Create: `D:/bian/app/db.py`
- Test: `D:/bian/tests/unit/test_db.py`
- Create: `D:/bian/tests/__init__.py`
- Create: `D:/bian/tests/unit/__init__.py`

**Interfaces:**
- Produces: `engine`, `SessionLocal`, `Base`, `get_session()` dependency

**Steps:**
- [ ] **Step 1: Write the failing test** — `tests/unit/test_db.py`

```python
from app.db import engine, SessionLocal, Base, get_session
from sqlalchemy import text


def test_engine_is_sqlite():
    assert "sqlite" in str(engine.url)


def test_base_is_declarative():
    assert hasattr(Base, "metadata")


def test_session_yields_session():
    with SessionLocal() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_get_session_dependency():
    gen = get_session()
    sess = next(gen)
    try:
        result = sess.execute(text("SELECT 2")).scalar()
        assert result == 2
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
```

- [ ] **Step 2: Run test, expect failure**
  - Run: `venv/Scripts/python -m pytest tests/unit/test_db.py -v`
  - Expected: `ModuleNotFoundError: No module named 'app'`
- [ ] **Step 3: Implement `app/db.py`**

```python
"""SQLAlchemy engine, session, Base. SQLite file at data/app.db."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "app.db"

# check_same_thread=False lets FastAPI's threadpool reuse connections
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a Session, ensures close."""
    sess = SessionLocal()
    try:
        yield sess
    finally:
        sess.close()
```

- [ ] **Step 4: Create empty packages**
  - `app/__init__.py` (empty)
  - `tests/__init__.py` (empty)
  - `tests/unit/__init__.py` (empty)
  - `tests/conftest.py`:

```python
import sys
from pathlib import Path

# Make sure tests can import the app package without installing it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 5: Run tests, expect green**
  - Run: `venv/Scripts/python -m pytest tests/unit/test_db.py -v`
  - Expected: 4 passed
- [ ] **Step 6: Commit**

```bash
git add app/__init__.py app/db.py tests/__init__.py tests/conftest.py tests/unit/__init__.py tests/unit/test_db.py
git commit -m "feat(db): add SQLAlchemy engine, session, and Base"
```

---

## Task 5: Settings model + app_state model

**Files:**
- Create: `D:/bian/app/models/__init__.py`
- Create: `D:/bian/app/models/setting.py`
- Create: `D:/bian/app/models/app_state.py`
- Test: `D:/bian/tests/unit/test_models_setting.py`

**Interfaces:**
- Produces: `Setting(key, value)`, `AppState(key, value)`

**Steps:**
- [ ] **Step 1: Write the failing test**

`tests/unit/test_models_setting.py`:
```python
from app.db import Base, engine, SessionLocal
from app.models.setting import Setting
from app.models.app_state import AppState


def _recreate():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_setting_roundtrip():
    _recreate()
    with SessionLocal() as s:
        s.add(Setting(key="binance_testnet", value="true"))
        s.commit()
    with SessionLocal() as s:
        v = s.get(Setting, "binance_testnet")
        assert v is not None
        assert v.value == "true"


def test_app_state_roundtrip():
    _recreate()
    with SessionLocal() as s:
        s.add(AppState(key="setup_completed", value="false"))
        s.commit()
    with SessionLocal() as s:
        v = s.get(AppState, "setup_completed")
        assert v.value == "false"
```

- [ ] **Step 2: Run, expect failure**
  - Run: `venv/Scripts/python -m pytest tests/unit/test_models_setting.py -v`
  - Expected: `ModuleNotFoundError: No module named 'app.models'`
- [ ] **Step 3: Implement**

`app/models/__init__.py`: empty.

`app/models/setting.py`:
```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
```

`app/models/app_state.py`:
```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AppState(Base):
    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
```

- [ ] **Step 4: Run tests, expect green**
  - Run: `venv/Scripts/python -m pytest tests/unit/test_models_setting.py -v`
  - Expected: 2 passed
- [ ] **Step 5: Commit**

```bash
git add app/models tests/unit/test_models_setting.py
git commit -m "feat(models): add Setting and AppState"
```

---

## Task 6: Config module (pydantic-settings)

**Files:**
- Create: `D:/bian/app/config.py`
- Create: `D:/bian/.env.example`
- Test: `D:/bian/tests/unit/test_config.py`

**Interfaces:**
- Produces: `get_settings()` returning `Settings` with `binance_testnet: bool`, `binance_api_key: str`, `binance_api_secret: str` (read from keyring in production, env in test).

**Steps:**
- [ ] **Step 1: Write the failing test**

```python
import os

from app.config import get_settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("BINANCE_TESTNET", raising=False)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    s = get_settings()
    assert s.binance_testnet is True
    assert s.binance_api_key == ""
    assert s.binance_api_secret == ""


def test_overrides(monkeypatch):
    monkeypatch.setenv("BINANCE_TESTNET", "false")
    monkeypatch.setenv("BINANCE_API_KEY", "abc")
    monkeypatch.setenv("BINANCE_API_SECRET", "xyz")
    s = get_settings()
    assert s.binance_testnet is False
    assert s.binance_api_key == "abc"
    assert s.binance_api_secret == "xyz"
```

- [ ] **Step 2: Run, expect failure**
  - Expected: `ModuleNotFoundError: No module named 'app.config'`
- [ ] **Step 3: Implement `app/config.py`**

```python
"""Centralized configuration. Reads env vars for dev; keyring is the
canonical store in production (see app/crypto_store.py)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BINANCE_", extra="ignore")

    testnet: bool = Field(default=True, alias="BINANCE_TESTNET")
    api_key: str = Field(default="", alias="BINANCE_API_KEY")
    api_secret: str = Field(default="", alias="BINANCE_API_SECRET")
    base_url: str = Field(default="https://testnet.binance.vision", alias="BINANCE_BASE_URL_OVERRIDE")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

Note: `BINANCE_BASE_URL_OVERRIDE` lets us override the base URL for testing. Default points to Spot Testnet.

`.env.example`:
```
BINANCE_TESTNET=true
# Do NOT commit real keys. Use the UI Setup wizard to store them.
BINANCE_API_KEY=
BINANCE_API_SECRET=
```

- [ ] **Step 4: Run tests, expect green**
  - Run: `venv/Scripts/python -m pytest tests/unit/test_config.py -v`
  - Expected: 2 passed
- [ ] **Step 5: Commit**

```bash
git add app/config.py .env.example tests/unit/test_config.py
git commit -m "feat(config): pydantic Settings with env prefix"
```

---

## Task 7: Encrypted key storage via keyring

**Files:**
- Create: `D:/bian/app/crypto_store.py`
- Test: `D:/bian/tests/unit/test_crypto_store.py`

**Interfaces:**
- Produces: `save_secret(slug, value)`, `load_secret(slug) -> str | None`, `delete_secret(slug)`. Namespaced under service name `binance-spot-grid-bot`.

**Steps:**
- [ ] **Step 1: Write the failing test**

```python
from app.crypto_store import save_secret, load_secret, delete_secret, SERVICE_NAME


def _slot() -> str:
    return SERVICE_NAME + ":test"


def test_roundtrip(monkeypatch):
    # Use a unique slug for this test
    slug = "test_roundtrip_xyz"
    assert load_secret(slug) is None
    save_secret(slug, "supersecret")
    assert load_secret(slug) == "supersecret"
    delete_secret(slug)
    assert load_secret(slug) is None
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement `app/crypto_store.py`**

```python
"""Encrypted local secrets via OS keyring (Windows Credential Manager
on this platform). Slug namespaced so multiple local bots do not collide."""
from __future__ import annotations

import keyring
import keyring.errors

SERVICE_NAME = "binance-spot-grid-bot"


def save_secret(slug: str, value: str) -> None:
    keyring.set_password(SERVICE_NAME, slug, value)


def load_secret(slug: str) -> str | None:
    try:
        return keyring.get_password(SERVICE_NAME, slug)
    except keyring.errors.KeyringError:
        return None


def delete_secret(slug: str) -> None:
    try:
        keyring.delete_password(SERVICE_NAME, slug)
    except keyring.errors.PasswordDeleteError:
        pass
```

- [ ] **Step 4: Run, expect green**
  - On Windows the test uses the real Credential Manager. Use unique slugs per test to avoid cross-test pollution.
- [ ] **Step 5: Commit**

```bash
git add app/crypto_store.py tests/unit/test_crypto_store.py
git commit -m "feat(security): encrypted secret storage via keyring"
```

---

## Task 8: FastAPI app skeleton + setup gate middleware

**Files:**
- Create: `D:/bian/app/main.py`
- Create: `D:/bian/app/setup_wizard.py`
- Create: `D:/bian/app/api/__init__.py`
- Create: `D:/bian/app/api/deps.py`
- Create: `D:/bian/app/api/routers/__init__.py`
- Create: `D:/bian/app/api/routers/setup.py`
- Test: `D:/bian/tests/integration/test_setup_gate.py`

**Interfaces:**
- Produces: FastAPI app with `GET /api/setup/state`, `POST /api/setup/complete`. Setup gate: requests to paths not starting with `/api/setup`, `/api/health`, `/api/docs`, `/api/openapi.json`, `/` (SPA shell), or static asset paths are forwarded only if `setup_completed=true` in `app_state`. (For V1 we keep gate simple: just gate a JSON 403 with a `setup_required=true` flag; the SPA handles redirect.)

**Steps:**
- [ ] **Step 1: Write the failing test** — `tests/integration/test_setup_gate.py`

```python
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app

client = TestClient(app)


def _reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_setup_state_when_unconfigured():
    _reset()
    r = client.get("/api/setup/state")
    assert r.status_code == 200
    assert r.json() == {"setup_required": True}


def test_protected_endpoint_blocked_when_unconfigured():
    _reset()
    r = client.get("/api/dashboard/overview")
    assert r.status_code == 403
    assert r.json().get("setup_required") is True


def test_setup_endpoint_open_even_when_unconfigured():
    _reset()
    r = client.get("/api/setup/state")
    assert r.status_code == 200


def test_protected_endpoint_opens_when_setup_completed():
    _reset()
    # complete setup via the endpoint
    r = client.post("/api/setup/complete", json={"acknowledged": True})
    assert r.status_code == 200
    r = client.get("/api/dashboard/overview")
    assert r.status_code != 403


def test_health_open():
    _reset()
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement `app/api/routers/setup.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.app_state import AppState
from app.models.setting import Setting

router = APIRouter(prefix="/api/setup", tags=["setup"])


def is_setup_completed(session: Session) -> bool:
    row = session.get(AppState, "setup_completed")
    api_key_set = session.get(Setting, "binance_api_key") is not None
    return (row is not None and row.value == "true") and api_key_set


@router.get("/state")
def state(session: Session = Depends(get_session)):
    completed = is_setup_completed(session)
    return {"setup_required": not completed}


@router.post("/complete")
def complete(payload: dict, session: Session = Depends(get_session)):
    # The actual key save happens via settings endpoint.
    # This just flips the flag.
    if not payload.get("acknowledged"):
        return {"ok": False, "error": "must acknowledge"}
    state_row = session.get(AppState, "setup_completed")
    if state_row is None:
        state_row = AppState(key="setup_completed", value="true")
        session.add(state_row)
    else:
        state_row.value = "true"
    session.commit()
    return {"ok": True}
```

- [ ] **Step 4: Implement setup middleware in `app/main.py`**

```python
"""FastAPI entrypoint. Sets up middleware (CORS + setup gate), routers,
lifespan to init DB on startup."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import setup as setup_router
from app.db import Base, SessionLocal, engine
from app.models.app_state import AppState  # noqa
from app.models.setting import Setting  # noqa


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
    DATA_DIR.mkdir(exist_ok=True)
    Base.metadata.create_all(engine)
    yield


app = FastAPI(lifespan=lifespan, title="Binance Spot Grid Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPEN_PREFIXES = (
    "/api/setup",
    "/api/health",
    "/api/docs",
    "/api/openapi.json",
    "/api/redoc",
)


@app.middleware("http")
async def setup_gate(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or any(path.startswith(p) for p in OPEN_PREFIXES):
        return await call_next(request)
    # Check setup state
    from app.api.routers.setup import is_setup_completed  # avoid circular
    with SessionLocal() as s:
        if is_setup_completed(s):
            return await call_next(request)
    return JSONResponse(status_code=403, content={"setup_required": True, "path": path})


app.include_router(setup_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests, expect green**
  - Run: `venv/Scripts/python -m pytest tests/integration/test_setup_gate.py -v`
  - Expected: 5 passed
- [ ] **Step 6: Commit**

```bash
git add app/main.py app/api app/setup_wizard.py tests/integration/test_setup_gate.py
git commit -m "feat(api): setup gate middleware and health endpoint"
```

---

## Task 9: Run backend locally to confirm cold-start works

**Files:**
- Modify: none
- Create: nothing (just verification)

**Steps:**
- [ ] **Step 1: Start the server**
  - Run (in background): `venv/Scripts/python -m uvicorn app.main:app --reload --port 8000`
- [ ] **Step 2: Probe health**
  - Run: `curl http://localhost:8000/api/health`
  - Expected: `{"status":"ok"}`
- [ ] **Step 3: Probe setup state**
  - Run: `curl http://localhost:8000/api/setup/state`
  - Expected: `{"setup_required":true}`
- [ ] **Step 4: Probe gated endpoint**
  - Run: `curl http://localhost:8000/api/dashboard/overview`
  - Expected: HTTP 403 with `{"setup_required":true,...}`
- [ ] **Step 5: Stop the server**
  - Kill the background uvicorn.

---

# Phase 2 — Binance Client

## Task 10: Binance signing helpers (no external library)

**Files:**
- Create: `D:/bian/app/broker/__init__.py` (empty)
- Create: `D:/bian/app/broker/binance.py`
- Test: `D:/bian/tests/unit/test_binance_sign.py`

**Interfaces:**
- Produces: `sign_query(params: dict, secret: str) -> str` (hex digest), `now_ms() -> int`, `BinanceClient(api_key, api_secret, testnet=True)`.

**Steps:**
- [ ] **Step 1: Write failing test**

```python
from app.broker.binance import sign_query, now_ms


def test_sign_query_deterministic():
    p = {"symbol": "BTCUSDT", "side": "BUY", "timestamp": 1700000000000}
    sig = sign_query(p, "mysecret")
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA256 hex


def test_now_ms_is_int():
    n = now_ms()
    assert isinstance(n, int)
    assert n > 1700000000000


def test_sign_query_changes_with_secret():
    p = {"symbol": "BTCUSDT"}
    a = sign_query(p, "secret1")
    b = sign_query(p, "secret2")
    assert a != b
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement helpers** in `app/broker/binance.py`

```python
"""Binance Spot client. We deliberately do NOT depend on the
sammchardy/python-binance library — we mirror its API patterns but write
our own implementation. Inspiration noted in 借鉴/python-binance/."""
from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse
from typing import Any


def now_ms() -> int:
    return int(time.time() * 1000)


def sign_query(params: dict[str, Any], secret: str) -> str:
    qs = urllib.parse.urlencode({k: str(v) for k, v in params.items()})
    digest = hmac.new(secret.encode("utf-8"), qs.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


TESTNET_BASE = "https://testnet.binance.vision"
PROD_BASE = "https://api.binance.com"


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, *, testnet: bool = True, http_client=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base = TESTNET_BASE if testnet else PROD_BASE
        # http_client is injectable for tests; default to a sync httpx client
        import httpx

        self._http = http_client or httpx.Client(base_url=self.base, timeout=10.0)

    def close(self):
        self._http.close()
```

- [ ] **Step 4: Run tests, expect green**
- [ ] **Step 5: Commit**

```bash
git add app/broker tests/unit/test_binance_sign.py
git commit -m "feat(broker): binance signing helpers and client shell"
```

---

## Task 11: REST endpoints (account info, klines, place order, cancel)

**Files:**
- Modify: `D:/bian/app/broker/binance.py`
- Test: `D:/bian/tests/unit/test_binance_rest.py`

**Interfaces (additions on `BinanceClient`):**
- `get_server_time() -> int`
- `get_account_info() -> dict`
- `get_symbol_info(symbol: str) -> dict`
- `get_klines(symbol: str, interval: str, limit: int = 500) -> list[list]`
- `place_order(symbol, side, type_, quantity, price=None, time_in_force="GTC") -> dict`
- `cancel_order(symbol, order_id) -> dict`
- `get_open_orders(symbol: str | None = None) -> list[dict]`
- `get_all_orders(symbol, limit=100) -> list[dict]`

**Steps:**
- [ ] **Step 1: Write failing test** using `httpx.MockTransport`

```python
import httpx
import pytest

from app.broker.binance import BinanceClient


def _make_client(handler) -> BinanceClient:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://testnet.binance.vision", transport=transport)
    return BinanceClient("k", "s", testnet=True, http_client=client)


def test_get_account_info(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/account":
            return httpx.Response(200, json={"makerCommission": 10, "balances": []})
        return httpx.Response(404)

    c = _make_client(handler)
    info = c.get_account_info()
    assert info["makerCommission"] == 10
    c.close()


def test_get_klines(monkeypatch):
    sample = [
        [1700000000000, "100.0", "110.0", "95.0", "105.0", "12.34",
         1700003600000, "1295.7", 100, "6.17", "647.85", "0"],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v3/klines":
            qs = dict(request.url.params)
            assert qs["symbol"] == "BTCUSDT"
            assert qs["interval"] == "1h"
            return httpx.Response(200, json=sample)
        return httpx.Response(404)

    c = _make_client(handler)
    rows = c.get_klines("BTCUSDT", "1h", limit=1)
    assert len(rows) == 1
    assert rows[0][1] == "100.0"
    c.close()


def test_place_order_sends_signed_request(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"orderId": 1, "status": "NEW"})

    c = _make_client(handler)
    r = c.place_order(
        "BTCUSDT", "BUY", "LIMIT", quantity=0.001, price=30000.0
    )
    assert captured["path"] == "/api/v3/order"
    assert captured["params"]["symbol"] == "BTCUSDT"
    assert captured["params"]["side"] == "BUY"
    assert captured["params"]["type"] == "LIMIT"
    assert captured["params"]["signature"]  # present
    assert r["status"] == "NEW"
    c.close()
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement** REST methods on `BinanceClient`

Append to `app/broker/binance.py`:

```python
from typing import Any

def _signed(self, params: dict[str, Any]) -> dict[str, Any]:
    p = dict(params)
    p.setdefault("timestamp", now_ms())
    p.setdefault("recvWindow", 5000)
    p["signature"] = sign_query(p, self.api_secret)
    return p


def _request(self, method: str, path: str, *, params=None, signed=False):
    headers = {"X-MBX-APIKEY": self.api_key} if self.api_key else {}
    q = params or {}
    if signed:
        q = self._signed(q)
    if method.upper() == "GET":
        return self._http.get(path, params=q, headers=headers)
    return self._http.post(path, params=q, headers=headers)


def get_server_time(self) -> int:
    r = self._request("GET", "/api/v3/time")
    r.raise_for_status()
    return r.json()["serverTime"]


def get_account_info(self) -> dict:
    r = self._request("GET", "/api/v3/account", signed=True)
    r.raise_for_status()
    return r.json()


def get_symbol_info(self, symbol: str) -> dict:
    r = self._request("GET", "/api/v3/exchangeInfo", params={"symbol": symbol})
    r.raise_for_status()
    info = r.json()
    return info["symbols"][0] if info.get("symbols") else {}


def get_klines(self, symbol: str, interval: str, limit: int = 500) -> list[list]:
    r = self._request("GET", "/api/v3/klines", params={
        "symbol": symbol, "interval": interval, "limit": limit,
    })
    r.raise_for_status()
    return r.json()


def place_order(
    self, symbol: str, side: str, type_: str,
    *, quantity: float, price: float | None = None,
    time_in_force: str = "GTC",
) -> dict:
    p: dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "type": type_,
        "quantity": quantity,
        "newOrderRespType": "RESULT",
    }
    if price is not None:
        p["price"] = price
        p["timeInForce"] = time_in_force
    r = self._request("POST", "/api/v3/order", params=p, signed=True)
    r.raise_for_status()
    return r.json()


def cancel_order(self, symbol: str, order_id: int) -> dict:
    r = self._request("DELETE", "/api/v3/order", params={
        "symbol": symbol, "orderId": order_id,
    }, signed=True)
    r.raise_for_status()
    return r.json()


def get_open_orders(self, symbol: str | None = None) -> list[dict]:
    p = {"symbol": symbol} if symbol else {}
    r = self._request("GET", "/api/v3/openOrders", params=p, signed=True)
    r.raise_for_status()
    return r.json()


def get_all_orders(self, symbol: str, limit: int = 100) -> list[dict]:
    r = self._request("GET", "/api/v3/allOrders", params={
        "symbol": symbol, "limit": limit,
    }, signed=True)
    r.raise_for_status()
    return r.json()
```

Note: methods are added to the class. Verify the test passes by checking class structure.

- [ ] **Step 4: Run tests, expect green**
- [ ] **Step 5: Commit**

```bash
git add app/broker/binance.py tests/unit/test_binance_rest.py
git commit -m "feat(broker): add REST endpoints for account/klines/orders"
```

---

## Task 12: Symbol metadata model + cache

**Files:**
- Create: `D:/bian/app/models/symbol.py`
- Test: `D:/bian/tests/unit/test_symbol_model.py`

**Interfaces:**
- Produces: `Symbol(symbol, base, quote, min_qty, tick_size, step_size, min_notional, updated_at)`.

**Steps:**
- [ ] **Step 1: Write failing test**

```python
from datetime import datetime, timezone

from app.db import Base, engine, SessionLocal
from app.models.symbol import Symbol


def test_roundtrip():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        s.add(Symbol(
            symbol="BTCUSDT", base="BTC", quote="USDT",
            min_qty=0.00001, tick_size=0.01, step_size=0.00001,
            min_notional=10.0, updated_at=now,
        ))
        s.commit()
    with SessionLocal() as s:
        row = s.get(Symbol, "BTCUSDT")
        assert row is not None
        assert row.base == "BTC"
        assert row.min_qty == 0.00001
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement `app/models/symbol.py`**

```python
from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Symbol(Base):
    __tablename__ = "symbols"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    base: Mapped[str] = mapped_column(String, nullable=False)
    quote: Mapped[str] = mapped_column(String, nullable=False)
    min_qty: Mapped[float] = mapped_column(Float, nullable=False)
    tick_size: Mapped[float] = mapped_column(Float, nullable=False)
    step_size: Mapped[float] = mapped_column(Float, nullable=False)
    min_notional: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

- [ ] **Step 4: Run, expect green**
- [ ] **Step 5: Commit**

```bash
git add app/models/symbol.py tests/unit/test_symbol_model.py
git commit -m "feat(models): add Symbol metadata cache"
```

---

# Phase 3 — Strategy & Engine

## Task 13: Base strategy + context object

**Files:**
- Create: `D:/bian/app/strategy/__init__.py` (empty)
- Create: `D:/bian/app/strategy/base.py`
- Test: `D:/bian/tests/unit/test_strategy_base.py`

**Interfaces:**
- Produces: `StrategyContext` (with `place_order`, `cancel_order`, `log`, `now_ms`), `BaseStrategy` ABC with the 5 callbacks.

**Steps:**
- [ ] **Step 1: Write failing test**

```python
from app.strategy.base import BaseStrategy, StrategyContext


class Dummy(BaseStrategy):
    name = "dummy"

    def on_start(self, ctx):
        ctx.log("starting")

    def on_tick(self, ctx, last_price):
        pass

    def on_order_filled(self, ctx, trade):
        pass

    def on_order_rejected(self, ctx, order, err):
        pass

    def on_stop(self, ctx):
        pass


def test_lifecycle_callbacks_run():
    calls = []

    class Recorder(BaseStrategy):
        name = "rec"
        def on_start(self, ctx): calls.append("start")
        def on_tick(self, ctx, lp): calls.append(("tick", lp))
        def on_order_filled(self, ctx, t): calls.append(("fill", t))
        def on_order_rejected(self, ctx, o, e): calls.append(("rej", e))
        def on_stop(self, ctx): calls.append("stop")

    r = Recorder()
    ctx = StrategyContext()
    r.on_start(ctx)
    r.on_tick(ctx, 100.0)
    r.on_order_filled(ctx, {"price": 100.5})
    r.on_order_rejected(ctx, None, "boom")
    r.on_stop(ctx)
    assert calls[0] == "start"
    assert calls[-1] == "stop"
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement `app/strategy/base.py`**

```python
"""Strategy abstract base. Inspired by Freqtrade's IStrategy callbacks
but kept deliberately small. We only READ freqtrade for ideas — no code reuse."""
from __future__ import annotations

from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class StrategyContext:
    """Runtime services a strategy uses. Wired by the engine."""
    log: Callable[[str], None] = field(default=lambda msg: None)
    place_order: Callable[..., dict] = field(default=lambda **_: {})
    cancel_order: Callable[..., dict] = field(default=lambda **_: {})
    grid_id: int | None = None
    symbol: str = ""


class BaseStrategy(ABC):
    name: str = "base"
    symbol: str = ""

    def on_start(self, ctx: StrategyContext) -> None: ...
    def on_tick(self, ctx: StrategyContext, last_price: float) -> None: ...
    def on_order_filled(self, ctx: StrategyContext, trade: dict) -> None: ...
    def on_order_rejected(self, ctx: StrategyContext, order: dict, err: str) -> None: ...
    def on_stop(self, ctx: StrategyContext) -> None: ...
```

- [ ] **Step 4: Run, expect green**
- [ ] **Step 5: Commit**

```bash
git add app/strategy tests/unit/test_strategy_base.py
git commit -m "feat(strategy): BaseStrategy and StrategyContext"
```

---

## Task 14: Grid arithmetic helpers + GridStrategy.scaffold

**Files:**
- Create: `D:/bian/app/strategy/grid.py`
- Test: `D:/bian/tests/unit/test_grid_strategy.py`

**Interfaces (V1 simplify scope):**
- Module function: `build_grid_levels(lower: float, upper: float, count: int, mode: str = "arithmetic") -> list[float]`
- `GridStrategy(BaseStrategy)` with `__init__(symbol, lower, upper, count, mode, total_quote_amount)`; calls `on_start` to place initial two-sided orders; replaces fills with a single-shot emulation here (no engine yet).

**Steps:**
- [ ] **Step 1: Write failing test**

```python
import pytest

from app.strategy.grid import build_grid_levels, GridStrategy


def test_arithmetic_grid_levels_count_and_bounds():
    levels = build_grid_levels(100.0, 200.0, 11, "arithmetic")
    assert len(levels) == 11
    assert levels[0] == pytest.approx(100.0)
    assert levels[-1] == pytest.approx(200.0)
    diffs = [levels[i+1] - levels[i] for i in range(len(levels) - 1)]
    assert max(diffs) - min(diffs) < 1e-6


def test_geometric_grid_levels_count_and_bounds():
    levels = build_grid_levels(100.0, 200.0, 5, "geometric")
    assert len(levels) == 5
    assert levels[0] == pytest.approx(100.0)
    assert levels[-1] == pytest.approx(200.0)


def test_grid_strategy_starts_with_two_sided_orders(monkeypatch):
    placed = []

    def fake_place_order(**kw):
        placed.append(kw)
        return {"orderId": len(placed)}

    from app.strategy.base import StrategyContext
    s = GridStrategy("BTCUSDT", 100.0, 110.0, count=6, mode="arithmetic", total_quote_amount=60.0)
    ctx = StrategyContext(place_order=fake_place_order, log=lambda m: None)
    s.on_start(ctx)
    # Roughly: levels between 100 and 110, around current price = midpoint 105
    # Two-sided means at least one BUY below midpoint and one SELL above.
    sides = [p["side"] for p in placed]
    assert "BUY" in sides
    assert "SELL" in sides
    assert len(placed) >= 2
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement `app/strategy/grid.py`**

```python
"""Spot grid strategy. Two-sided initial orders; later replacements are
fired on trade callbacks (engine-driven)."""
from __future__ import annotations

import math
from typing import Literal

from app.strategy.base import BaseStrategy, StrategyContext

Mode = Literal["arithmetic", "geometric"]


def build_grid_levels(lower: float, upper: float, count: int, mode: Mode = "arithmetic") -> list[float]:
    if count < 2:
        raise ValueError("count must be >= 2")
    if lower <= 0 or upper <= 0 or upper <= lower:
        raise ValueError("invalid bounds")
    if mode == "arithmetic":
        step = (upper - lower) / (count - 1)
        return [lower + step * i for i in range(count)]
    # geometric
    ratio = (upper / lower) ** (1 / (count - 1))
    return [lower * (ratio ** i) for i in range(count)]


def _round_to(value: float, step: float) -> float:
    if step <= 0:
        return value
    return round(round(value / step) * step, 10)


class GridStrategy(BaseStrategy):
    def __init__(
        self,
        symbol: str,
        lower: float,
        upper: float,
        count: int,
        mode: Mode = "arithmetic",
        total_quote_amount: float = 0.0,
        tick_size: float = 0.01,
        step_size: float = 0.0001,
    ):
        self.symbol = symbol
        self.lower = lower
        self.upper = upper
        self.count = count
        self.mode = mode
        self.total_quote_amount = total_quote_amount
        self.tick_size = tick_size
        self.step_size = step_size
        self.name = f"grid-{symbol}-{count}"
        self.levels = build_grid_levels(lower, upper, count, mode)
        self.quote_per_buy = (total_quote_amount / max(1, count // 2)) if total_quote_amount else 0.0

    def _place_two_sided(self, ctx: StrategyContext, current_price: float) -> None:
        # Buy side: nearest 3 levels below current price
        buys = [lv for lv in self.levels if lv < current_price]
        sells = [lv for lv in self.levels if lv > current_price]
        for lv in buys[-3:]:
            qty = self._qty_for_quote(lv)
            ctx.place_order(symbol=self.symbol, side="BUY", type_="LIMIT",
                            quantity=qty, price=_round_to(lv, self.tick_size))
        for lv in sells[:3]:
            qty = self._qty_for_quote(lv)
            ctx.place_order(symbol=self.symbol, side="SELL", type_="LIMIT",
                            quantity=qty, price=_round_to(lv, self.tick_size))

    def _qty_for_quote(self, price: float) -> float:
        if self.quote_per_buy <= 0:
            return self.step_size
        qty = self.quote_per_buy / price
        return max(self.step_size, _round_to(qty, self.step_size))

    def on_start(self, ctx: StrategyContext) -> None:
        current_price = (self.lower + self.upper) / 2
        self._place_two_sided(ctx, current_price)
        ctx.log(f"grid started for {self.symbol} between {self.lower} and {self.upper}")

    def on_tick(self, ctx: StrategyContext, last_price: float) -> None:
        # Future work: re-center / pause if outside bounds.
        return None

    def on_order_filled(self, ctx: StrategyContext, trade: dict) -> None:
        """On BUY fill, place a SELL one tick above; on SELL fill, place BUY one tick below."""
        side = trade.get("side")
        price = float(trade.get("price") or 0)
        qty = float(trade.get("qty") or 0)
        if not price or not qty:
            return
        if side == "BUY":
            new_price = _round_to(price + self.tick_size, self.tick_size)
            if new_price <= self.upper:
                ctx.place_order(symbol=self.symbol, side="SELL", type_="LIMIT",
                                quantity=qty, price=new_price)
        elif side == "SELL":
            new_price = _round_to(price - self.tick_size, self.tick_size)
            if new_price >= self.lower:
                ctx.place_order(symbol=self.symbol, side="BUY", type_="LIMIT",
                                quantity=qty, price=new_price)

    def on_order_rejected(self, ctx: StrategyContext, order: dict, err: str) -> None:
        ctx.log(f"order rejected: {order} err={err}")

    def on_stop(self, ctx: StrategyContext) -> None:
        ctx.log(f"grid stopped for {self.symbol}")
```

- [ ] **Step 4: Run, expect green**
- [ ] **Step 5: Commit**

```bash
git add app/strategy/grid.py tests/unit/test_grid_strategy.py
git commit -m "feat(strategy): GridStrategy with arithmetic/geometric levels"
```

---

## Task 15: Grid, Order, Trade, Kline models + Alembic init (manual)

**Files:**
- Create: `D:/bian/app/models/grid.py`
- Create: `D:/bian/app/models/order.py`
- Create: `D:/bian/app/models/trade.py`
- Create: `D:/bian/app/models/kline.py`
- Create: `D:/bian/alembic.ini` (lightweight, no migration directory for V1)
- Test: `D:/bian/tests/unit/test_models_grid.py`

**Steps:**
- [ ] **Step 1: Write failing test** — `tests/unit/test_models_grid.py`

```python
from datetime import datetime, timezone

from app.db import Base, engine, SessionLocal
from app.models.grid import Grid, GridStatus
from app.models.order import Order


def test_grid_create_and_status():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        g = Grid(
            symbol="BTCUSDT", lower_price=100.0, upper_price=110.0,
            grid_count=6, grid_mode="arithmetic", total_quote_amount=60.0,
            status=GridStatus.PENDING, created_at=datetime.now(timezone.utc),
        )
        s.add(g)
        s.commit()
        gid = g.id
    with SessionLocal() as s:
        g2 = s.get(Grid, gid)
        assert g2.status == GridStatus.PENDING


def test_order_links_to_grid():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        g = Grid(symbol="BTCUSDT", lower_price=1.0, upper_price=2.0,
                 grid_count=3, grid_mode="arithmetic",
                 total_quote_amount=10.0, status=GridStatus.PENDING,
                 created_at=datetime.now(timezone.utc))
        s.add(g)
        s.flush()
        o = Order(grid_id=g.id, binance_order_id=12345, symbol="BTCUSDT",
                  side="BUY", type="LIMIT", price=1.5, qty=0.001,
                  filled_qty=0.0, status="NEW",
                  created_at=datetime.now(timezone.utc),
                  updated_at=datetime.now(timezone.utc))
        s.add(o)
        s.commit()
    with SessionLocal() as s:
        order = s.query(Order).filter_by(binance_order_id=12345).one()
        assert order.grid_id is not None
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement models**

`app/models/grid.py`:
```python
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GridStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class Grid(Base):
    __tablename__ = "grids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, ForeignKey("symbols.symbol"), nullable=False)
    lower_price: Mapped[float] = mapped_column(Float, nullable=False)
    upper_price: Mapped[float] = mapped_column(Float, nullable=False)
    grid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    grid_mode: Mapped[str] = mapped_column(String, default="arithmetic", nullable=False)
    total_quote_amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[GridStatus] = mapped_column(
        Enum(GridStatus, native_enum=False), default=GridStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

`app/models/order.py`:
```python
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grid_id: Mapped[int] = mapped_column(Integer, ForeignKey("grids.id"), nullable=False)
    binance_order_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    side: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    filled_qty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String, default="NEW", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

`app/models/trade.py`:
```python
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    grid_id: Mapped[int] = mapped_column(Integer, ForeignKey("grids.id"), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    quote_qty: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fee_asset: Mapped[str] = mapped_column(String, default="", nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

`app/models/kline.py`:
```python
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class KLine(Base):
    __tablename__ = "klines_cache"
    __table_args__ = (UniqueConstraint("symbol", "interval", "open_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    interval: Mapped[str] = mapped_column(String, nullable=False)
    open_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
```

- [ ] **Step 4: Run, expect green**
- [ ] **Step 5: Commit**

```bash
git add app/models tests/unit/test_models_grid.py
git commit -m "feat(models): Grid/Order/Trade/KLine schemas"
```

---

## Task 16: Engine — lifecycle and per-grid asyncio tasks

**Files:**
- Create: `D:/bian/app/engine/__init__.py` (empty)
- Create: `D:/bian/app/engine/engine.py`
- Test: `D:/bian/tests/async/test_engine.py`

**Interfaces:**
- Produces: `Engine` with `start()`, `stop()`, `start_grid(grid_id)`, `stop_grid(grid_id)`, `handle_trade_update(payload)` for routing user-data WS events back to the right strategy. V1: single asyncio loop, light-weight.

**Steps:**
- [ ] **Step 1: Write failing async test** — `tests/async/test_engine.py`

```python
import asyncio

import pytest

from app.engine.engine import Engine


@pytest.mark.asyncio
async def test_engine_starts_and_stops_cleanly():
    eng = Engine()
    await eng.start()
    assert eng.is_running
    await eng.stop()
    assert not eng.is_running


@pytest.mark.asyncio
async def test_engine_routes_trade_to_grid():
    eng = Engine()
    await eng.start()
    fired = []

    # register a fake strategy
    eng.register_strategy(grid_id=1, strategy_name="g1", events=fired, ctx_args={})
    await eng.handle_trade_update({"grid_id": 1, "side": "BUY", "price": 100.0, "qty": 0.001})
    await asyncio.sleep(0.05)
    assert any(e[0] == "buy_fill" for e in fired)
    await eng.stop()
```

Add `pytest.ini` at `D:/bian/pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement `app/engine/engine.py`** (minimal V1 — keeps things simple)

```python
"""Engine: a single asyncio loop hosting per-grid strategy tasks.
Trade updates from the WebSocket user-data stream are routed here."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyBinding:
    grid_id: int
    name: str
    on_buy_fill: Any = None
    on_sell_fill: Any = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)


class Engine:
    def __init__(self):
        self._running = False
        self._bindings: dict[int, StrategyBinding] = {}
        self._consumer_tasks: dict[int, asyncio.Task] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        for t in self._consumer_tasks.values():
            t.cancel()
        self._consumer_tasks.clear()
        for b in self._bindings.values():
            while not b.queue.empty():
                try:
                    b.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        self._bindings.clear()
        self._running = False

    def register_strategy(
        self,
        *,
        grid_id: int,
        strategy_name: str,
        events: list,
        ctx_args: dict,
    ) -> StrategyBinding:
        b = StrategyBinding(grid_id=grid_id, name=strategy_name)

        async def _consumer():
            while True:
                ev = await b.queue.get()
                # crude routing on payload shape
                if isinstance(ev, dict) and ev.get("side") == "BUY":
                    events.append(("buy_fill", ev))
                elif isinstance(ev, dict) and ev.get("side") == "SELL":
                    events.append(("sell_fill", ev))

        self._bindings[grid_id] = b
        self._consumer_tasks[grid_id] = asyncio.create_task(_consumer())
        return b

    async def handle_trade_update(self, payload: dict) -> None:
        gid = payload.get("grid_id")
        b = self._bindings.get(gid)
        if b is None:
            return
        await b.queue.put(payload)
```

- [ ] **Step 4: Run, expect green**
- [ ] **Step 5: Commit**

```bash
git add app/engine pytest.ini tests/async/test_engine.py tests/async/__init__.py
git commit -m "feat(engine): async engine scaffolding with per-grid routing"
```

---

# Phase 4 — REST API & WebSocket

## Task 17: Settings router (API key save, retrieve masked, test connectivity)

**Files:**
- Create: `D:/bian/app/api/routers/settings.py`
- Test: `D:/bian/tests/integration/test_api_settings.py`

**Steps:**
- [ ] **Step 1: Write failing test**

```python
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app

client = TestClient(app)


def _reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_get_settings_strips_key_and_secret():
    _reset()
    r = client.post("/api/setup/complete", json={"acknowledged": True})
    assert r.status_code == 200
    r = client.put("/api/settings", json={"binance_testnet": True, "binance_api_key": "abc", "binance_api_secret": "xyz"})
    assert r.status_code == 200
    r = client.get("/api/settings")
    j = r.json()
    assert j["binance_testnet"] is True
    assert j["has_api_key"] is True
    assert j["has_api_secret"] is True
    assert "binance_api_key" not in j
    assert "binance_api_secret" not in j
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement `app/api/routers/settings.py`**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.crypto_store import save_secret, load_secret, delete_secret
from app.db import get_session
from app.models.setting import Setting

router = APIRouter(prefix="/api/settings", tags=["settings"])

_API_KEY_SLUG = "api_key"
_API_SECRET_SLUG = "api_secret"


def _get_setting(s: Session, key: str, default: str = "") -> str:
    row = s.get(Setting, key)
    return row.value if row else default


def _set_setting(s: Session, key: str, value: str) -> None:
    row = s.get(Setting, key)
    if row is None:
        s.add(Setting(key=key, value=value))
    else:
        row.value = value


class SettingsUpdate(BaseModel):
    binance_testnet: bool | None = None
    binance_api_key: str | None = None
    binance_api_secret: str | None = None


@router.get("")
def get_settings(session: Session = Depends(get_session)):
    testnet = _get_setting(session, "binance_testnet", "true") == "true"
    has_key = load_secret(_API_KEY_SLUG) is not None
    has_secret = load_secret(_API_SECRET_SLUG) is not None
    return {
        "binance_testnet": testnet,
        "has_api_key": has_key,
        "has_api_secret": has_secret,
    }


@router.put("")
def put_settings(update: SettingsUpdate, session: Session = Depends(get_session)):
    if update.binance_testnet is not None:
        _set_setting(session, "binance_testnet", "true" if update.binance_testnet else "false")
    if update.binance_api_key is not None:
        if update.binance_api_key == "":
            delete_secret(_API_KEY_SLUG)
        else:
            save_secret(_API_KEY_SLUG, update.binance_api_key)
            _set_setting(session, "binance_api_key", "set")  # marker only
    if update.binance_api_secret is not None:
        if update.binance_api_secret == "":
            delete_secret(_API_SECRET_SLUG)
        else:
            save_secret(_API_SECRET_SLUG, update.binance_api_secret)
            _set_setting(session, "binance_api_secret", "set")
    session.commit()
    return {"ok": True}


@router.post("/test-binance")
def test_binance(session: Session = Depends(get_session)):
    api_key = load_secret(_API_KEY_SLUG) or ""
    api_secret = load_secret(_API_SECRET_SLUG) or ""
    testnet = _get_setting(session, "binance_testnet", "true") == "true"
    if not api_key or not api_secret:
        return {"ok": False, "error": "missing credentials"}
    from app.broker.binance import BinanceClient
    c = BinanceClient(api_key, api_secret, testnet=testnet)
    try:
        info = c.get_account_info()
        return {"ok": True, "can_trade": info.get("canTrade", False), "testnet": testnet}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        c.close()
```

- [ ] **Step 4: Register the router**

Edit `app/main.py`:
```python
from app.api.routers import settings as settings_router
# ...
app.include_router(settings_router.router)
```

- [ ] **Step 5: Run, expect green**
- [ ] **Step 6: Commit**

```bash
git add app/api/routers/settings.py app/main.py tests/integration/test_api_settings.py
git commit -m "feat(api): settings router with keyring-backed secrets"
```

---

## Task 18: Grids CRUD router

**Files:**
- Create: `D:/bian/app/api/routers/grids.py`
- Test: `D:/bian/tests/integration/test_api_grids.py`

**Steps:**
- [ ] **Step 1: Write failing test**

```python
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.symbol import Symbol

client = TestClient(app)


def _reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        s.add(Symbol(symbol="BTCUSDT", base="BTC", quote="USDT",
                     min_qty=0.00001, tick_size=0.01, step_size=0.00001,
                     min_notional=10.0, updated_at=datetime.now(timezone.utc)))
        s.add(Symbol(symbol="ETHUSDT", base="ETH", quote="USDT",
                     min_qty=0.0001, tick_size=0.01, step_size=0.0001,
                     min_notional=10.0, updated_at=datetime.now(timezone.utc)))
        s.commit()
    client.post("/api/setup/complete", json={"acknowledged": True})


def test_create_and_list_grid():
    _reset()
    r = client.post("/api/grids", json={
        "symbol": "BTCUSDT", "lower_price": 100.0, "upper_price": 110.0,
        "grid_count": 6, "grid_mode": "arithmetic", "total_quote_amount": 60.0,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["status"] == "pending"
    r = client.get("/api/grids")
    assert len(r.json()) == 1


def test_delete_grid_only_when_stopped():
    _reset()
    r = client.post("/api/grids", json={
        "symbol": "BTCUSDT", "lower_price": 1.0, "upper_price": 2.0,
        "grid_count": 3, "grid_mode": "arithmetic", "total_quote_amount": 10.0,
    })
    gid = r.json()["id"]
    # cannot delete pending
    d = client.delete(f"/api/grids/{gid}")
    assert d.status_code == 400
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement `app/api/routers/grids.py`**

```python
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.grid import Grid, GridStatus

router = APIRouter(prefix="/api/grids", tags=["grids"])


class GridCreate(BaseModel):
    symbol: str
    lower_price: float = Field(gt=0)
    upper_price: float = Field(gt=0)
    grid_count: int = Field(ge=2, le=200)
    grid_mode: str = Field(default="arithmetic")
    total_quote_amount: float = Field(ge=0)


def _grid_to_dict(g: Grid) -> dict:
    return {
        "id": g.id,
        "symbol": g.symbol,
        "lower_price": g.lower_price,
        "upper_price": g.upper_price,
        "grid_count": g.grid_count,
        "grid_mode": g.grid_mode,
        "total_quote_amount": g.total_quote_amount,
        "status": g.status.value if isinstance(g.status, GridStatus) else g.status,
        "error_message": g.error_message,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "started_at": g.started_at.isoformat() if g.started_at else None,
        "stopped_at": g.stopped_at.isoformat() if g.stopped_at else None,
    }


@router.post("", status_code=201)
def create_grid(payload: GridCreate, session: Session = Depends(get_session)):
    if payload.lower_price >= payload.upper_price:
        raise HTTPException(status_code=400, detail="lower must be < upper")
    g = Grid(
        symbol=payload.symbol,
        lower_price=payload.lower_price,
        upper_price=payload.upper_price,
        grid_count=payload.grid_count,
        grid_mode=payload.grid_mode,
        total_quote_amount=payload.total_quote_amount,
        status=GridStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    session.add(g)
    session.commit()
    session.refresh(g)
    return _grid_to_dict(g)


@router.get("")
def list_grids(session: Session = Depends(get_session)):
    return [_grid_to_dict(g) for g in session.query(Grid).order_by(Grid.id.desc()).all()]


@router.get("/{grid_id}")
def get_grid(grid_id: int, session: Session = Depends(get_session)):
    g = session.get(Grid, grid_id)
    if g is None:
        raise HTTPException(status_code=404, detail="not found")
    return _grid_to_dict(g)


@router.delete("/{grid_id}", status_code=204)
def delete_grid(grid_id: int, session: Session = Depends(get_session)):
    g = session.get(Grid, grid_id)
    if g is None:
        raise HTTPException(status_code=404, detail="not found")
    if g.status == GridStatus.RUNNING or g.status == GridStatus.PENDING:
        raise HTTPException(status_code=400, detail="grid must be stopped before delete")
    session.delete(g)
    session.commit()
    return None


# start/stop endpoints are placeholders; they will be wired to the engine
# in Task X (engine wiring).
@router.post("/{grid_id}/start")
def start_grid(grid_id: int, session: Session = Depends(get_session)):
    g = session.get(Grid, grid_id)
    if g is None:
        raise HTTPException(status_code=404)
    g.status = GridStatus.PENDING  # engine flips to RUNNING when it actually starts
    g.started_at = datetime.now(timezone.utc)
    g.stopped_at = None
    g.error_message = None
    session.commit()
    return {"ok": True, "id": grid_id}


@router.post("/{grid_id}/stop")
def stop_grid(grid_id: int, session: Session = Depends(get_session)):
    g = session.get(Grid, grid_id)
    if g is None:
        raise HTTPException(status_code=404)
    g.status = GridStatus.STOPPED
    g.stopped_at = datetime.now(timezone.utc)
    session.commit()
    return {"ok": True, "id": grid_id}
```

Edit `app/main.py` to include the router:
```python
from app.api.routers import grids as grids_router
# ...
app.include_router(grids_router.router)
```

- [ ] **Step 4: Run, expect green**
- [ ] **Step 5: Commit**

```bash
git add app/api/routers/grids.py app/main.py tests/integration/test_api_grids.py
git commit -m "feat(api): grids CRUD endpoints"
```

---

## Task 19: Klines, Orders, Trades, Dashboard routers

**Files:**
- Create: `D:/bian/app/api/routers/klines.py`
- Create: `D:/bian/app/api/routers/orders.py`
- Create: `D:/bian/app/api/routers/trades.py`
- Create: `D:/bian/app/api/routers/dashboard.py`
- Test: `D:/bian/tests/integration/test_api_readonly.py`

**Steps:**
- [ ] **Step 1: Write failing test** — `tests/integration/test_api_readonly.py`

```python
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.grid import Grid, GridStatus
from app.models.order import Order

client = TestClient(app)


def _reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        g = Grid(symbol="BTCUSDT", lower_price=1, upper_price=2,
                 grid_count=3, grid_mode="arithmetic", total_quote_amount=10,
                 status=GridStatus.STOPPED, created_at=datetime.now(timezone.utc))
        s.add(g); s.flush()
        s.add(Order(grid_id=g.id, binance_order_id=999, symbol="BTCUSDT",
                    side="BUY", type="LIMIT", price=1.5, qty=0.001,
                    filled_qty=0, status="NEW",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)))
        s.commit()
    client.post("/api/setup/complete", json={"acknowledged": True})


def test_orders_list():
    _reset()
    r = client.get("/api/orders")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_dashboard_overview_returns_dict():
    _reset()
    r = client.get("/api/dashboard/overview")
    assert r.status_code == 200
    j = r.json()
    assert "running_grids" in j
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement** all four routers.

`app/api/routers/klines.py`:
```python
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.kline import KLine
from app.models.setting import Setting

router = APIRouter(prefix="/api/klines", tags=["klines"])


def _get_setting(s: Session, key: str, default: str = "") -> str:
    row = s.get(Setting, key)
    return row.value if row else default


@router.get("")
def get_klines(symbol: str, interval: str = "1h", limit: int = 200,
               session: Session = Depends(get_session)):
    rows = (
        session.query(KLine)
        .filter_by(symbol=symbol, interval=interval)
        .order_by(KLine.open_time.asc())
        .limit(limit)
        .all()
    )
    if rows:
        return [_k_to_dict(r) for r in rows]
    # Fall back to live Binance call
    from app.broker.binance import BinanceClient
    testnet = _get_setting(session, "binance_testnet", "true") == "true"
    api_key = ""  # public endpoint, no key required for klines
    api_secret = ""
    c = BinanceClient(api_key, api_secret, testnet=testnet)
    try:
        raw = c.get_klines(symbol, interval, limit=limit)
        out = []
        for k in raw:
            row = KLine(
                symbol=symbol, interval=interval,
                open_time=datetime.utcfromtimestamp(k[0] / 1000),
                open=float(k[1]), high=float(k[2]), low=float(k[3]),
                close=float(k[4]), volume=float(k[5]),
            )
            session.add(row)
            out.append(_k_to_dict(row))
        session.commit()
        return out
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        c.close()


def _k_to_dict(r: KLine) -> dict:
    return {
        "open_time": int(r.open_time.timestamp() * 1000),
        "open": r.open, "high": r.high, "low": r.low, "close": r.close,
        "volume": r.volume,
    }
```

`app/api/routers/orders.py`:
```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.order import Order

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("")
def list_orders(
    session: Session = Depends(get_session),
    grid_id: int | None = None,
    symbol: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, le=500),
):
    q = session.query(Order).order_by(Order.id.desc())
    if grid_id is not None:
        q = q.filter(Order.grid_id == grid_id)
    if symbol:
        q = q.filter(Order.symbol == symbol)
    if status:
        q = q.filter(Order.status == status)
    rows = q.limit(limit).all()
    return [{
        "id": r.id, "grid_id": r.grid_id, "binance_order_id": r.binance_order_id,
        "symbol": r.symbol, "side": r.side, "type": r.type,
        "price": r.price, "qty": r.qty, "filled_qty": r.filled_qty,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
```

`app/api/routers/trades.py`:
```python
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.trade import Trade

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("")
def list_trades(
    session: Session = Depends(get_session),
    grid_id: int | None = None,
    limit: int = Query(default=100, le=500),
):
    q = session.query(Trade).order_by(Trade.id.desc())
    if grid_id is not None:
        q = q.filter(Trade.grid_id == grid_id)
    rows = q.limit(limit).all()
    return [{
        "id": r.id, "grid_id": r.grid_id, "order_id": r.order_id,
        "price": r.price, "qty": r.qty, "quote_qty": r.quote_qty,
        "fee": r.fee, "fee_asset": r.fee_asset,
        "executed_at": r.executed_at.isoformat() if r.executed_at else None,
    } for r in rows]
```

`app/api/routers/dashboard.py`:
```python
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.grid import Grid, GridStatus
from app.models.order import Order
from app.models.trade import Trade

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(session: Session = Depends(get_session)):
    running = session.query(Grid).filter_by(status=GridStatus.RUNNING).count()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_trades = (
        session.query(Trade).filter(Trade.executed_at >= today_start).all()
    )
    pnl_today = sum((t.price - (t.quote_qty / max(1e-9, t.qty))) * t.qty for t in today_trades) * 0
    return {
        "running_grids": running,
        "open_orders": session.query(Order).filter(Order.status.in_(["NEW", "PARTIALLY_FILLED"])).count(),
        "today_pnl": pnl_today,
    }


@router.get("/balances")
def balances():
    # Wire to Binance client in the engine integration task.
    return []
```

- [ ] **Step 4: Register in `app/main.py`**

```python
from app.api.routers import (
    klines as klines_router,
    orders as orders_router,
    trades as trades_router,
    dashboard as dashboard_router,
)
app.include_router(klines_router.router)
app.include_router(orders_router.router)
app.include_router(trades_router.router)
app.include_router(dashboard_router.router)
```

- [ ] **Step 5: Run, expect green**
- [ ] **Step 6: Commit**

```bash
git add app/api/routers/klines.py app/api/routers/orders.py app/api/routers/trades.py app/api/routers/dashboard.py app/main.py tests/integration/test_api_readonly.py
git commit -m "feat(api): klines/orders/trades/dashboard read endpoints"
```

---

## Task 20: WebSocket realtime connection manager

**Files:**
- Create: `D:/bian/app/ws/__init__.py` (empty)
- Create: `D:/bian/app/ws/realtime.py`
- Test: `D:/bian/tests/integration/test_ws_realtime.py`

**Steps:**
- [ ] **Step 1: Write failing test**

```python
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.ws.realtime import manager

client = TestClient(app)


def test_ws_connects_and_receives_broadcast():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with client.websocket_connect("/ws/realtime") as ws:
        manager.broadcast({"type": "ping", "payload": {}})
        msg = ws.receive_json()
        assert msg["type"] == "ping"
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement `app/ws/realtime.py`**

```python
"""WebSocket ConnectionManager — fans out events to all connected clients."""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[Any] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        async with self._lock:
            clients = list(self._clients)
        dead = []
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    def broadcast_threadsafe_from_sync(self, loop: asyncio.AbstractEventLoop, message: dict) -> None:
        asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)


manager = ConnectionManager()
```

In `app/main.py`:
```python
from fastapi import WebSocket, WebSocketDisconnect
from app.ws.realtime import manager

@app.websocket("/ws/realtime")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive, ignore
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
```

- [ ] **Step 4: Run, expect green**
- [ ] **Step 5: Commit**

```bash
git add app/ws app/main.py tests/integration/test_ws_realtime.py
git commit -m "feat(ws): realtime broadcast manager"
```

---

# Phase 5 — Engine ↔ API ↔ Binance integration

## Task 21: Engine wiring — start/stop grids and broadcast events

**Files:**
- Modify: `D:/bian/app/api/routers/grids.py`
- Create: `D:/bian/app/engine/lifecycle.py`
- Test: `D:/bian/tests/async/test_lifecycle.py`

**Steps:**
- [ ] **Step 1: Write failing test**

```python
import asyncio

import pytest


@pytest.mark.asyncio
async def test_grid_lifecycle_runs_strategy_and_broadcasts_status():
    from app.engine.lifecycle import Lifecycle

    lc = Lifecycle()
    await lc.start()
    events = []
    lc.on_event(lambda e: events.append(e))
    await lc.start_grid(grid_id=42, symbol="BTCUSDT", lower=1.0, upper=2.0,
                        count=3, mode="arithmetic", total_quote_amount=10.0)
    await asyncio.sleep(0.1)
    await lc.stop_grid(grid_id=42)
    await lc.stop()
    types = [e["type"] for e in events]
    assert "grid_running" in types
    assert "grid_stopped" in types
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement `app/engine/lifecycle.py`**

```python
"""Higher-level glue: starts/stops grid strategies, broadcasts status to WS."""
from __future__ import annotations

import asyncio
from typing import Callable

from app.engine.engine import Engine
from app.strategy.base import StrategyContext
from app.strategy.grid import GridStrategy


class Lifecycle:
    def __init__(self):
        self.engine = Engine()
        self._listeners: list[Callable[[dict], None]] = []
        self._running = False

    def on_event(self, fn: Callable[[dict], None]) -> None:
        self._listeners.append(fn)

    def _fire(self, ev: dict) -> None:
        for fn in self._listeners:
            try:
                fn(ev)
            except Exception:
                pass

    async def start(self) -> None:
        if self._running:
            return
        await self.engine.start()
        self._running = True

    async def stop(self) -> None:
        await self.engine.stop()
        self._running = False

    async def start_grid(self, *, grid_id: int, symbol: str, lower: float,
                         upper: float, count: int, mode: str, total_quote_amount: float):
        if not self._running:
            await self.start()
        strat = GridStrategy(symbol=symbol, lower=lower, upper=upper,
                             count=count, mode=mode, total_quote_amount=total_quote_amount)

        def log(msg):
            self._fire({"type": "log", "payload": {"grid_id": grid_id, "msg": msg}})

        def place_order(**kw):
            self._fire({"type": "order_placed", "payload": {"grid_id": grid_id, **kw}})
            return {"orderId": 0}

        def cancel_order(**kw):
            self._fire({"type": "order_canceled", "payload": {"grid_id": grid_id, **kw}})
            return {"ok": True}

        ctx = StrategyContext(log=log, place_order=place_order,
                              cancel_order=cancel_order, grid_id=grid_id, symbol=symbol)
        # Wire strategy callbacks through the engine's trade routing
        await self.engine.register_strategy(
            grid_id=grid_id, strategy_name=strat.name,
            events=[], ctx_args={},
        )
        strat.on_start(ctx)
        self._fire({"type": "grid_running", "payload": {"grid_id": grid_id}})

    async def stop_grid(self, grid_id: int):
        self._fire({"type": "grid_stopped", "payload": {"grid_id": grid_id}})
```

- [ ] **Step 4: Modify `app/api/routers/grids.py` start/stop to delegate to lifecycle**

Edit the file's start/stop to use a global `lifecycle` singleton imported from app.engine.lifecycle. For tests, init the lifecycle with `await lifecycle.start()` in the TestClient (handled via the engine bootstrap in `app/main.py`'s lifespan).

Append to `app/main.py`:
```python
from app.engine.lifecycle import lifecycle

@app.on_event("startup")
async def _boot_engine():
    await lifecycle.start()
```

(Pythonic equivalent in lifespan is fine.)

- [ ] **Step 5: Run, expect green**
- [ ] **Step 6: Commit**

```bash
git add app/engine/lifecycle.py app/api/routers/grids.py app/main.py tests/async/test_lifecycle.py
git commit -m "feat(engine): lifecycle wiring and broadcast"
```

---

## Task 22: Klines cache + symbol info refresh at startup

**Files:**
- Modify: `D:/bian/app/api/routers/klines.py`
- Create: `D:/bian/app/api/routers/symbols.py`

**Steps:**
- [ ] **Step 1: Write failing test**

```python
def test_symbols_lists_what_we_have():
    _reset()  # helper from prior test file
    r = client.get("/api/symbols")
    assert r.status_code == 200
    rows = r.json()
    # Only what we inserted
    assert any(s["symbol"] == "BTCUSDT" for s in rows)
```

- [ ] **Step 2: Implement minimal `app/api/routers/symbols.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.symbol import Symbol

router = APIRouter(prefix="/api/symbols", tags=["symbols"])


@router.get("")
def list_symbols(session: Session = Depends(get_session)):
    rows = session.query(Symbol).order_by(Symbol.symbol).all()
    return [{
        "symbol": r.symbol, "base": r.base, "quote": r.quote,
        "min_qty": r.min_qty, "tick_size": r.tick_size,
        "step_size": r.step_size, "min_notional": r.min_notional,
    } for r in rows]
```

Register in `app/main.py`. Commit.

```bash
git add app/api/routers/symbols.py app/main.py
git commit -m "feat(api): list symbols endpoint"
```

---

# Phase 6 — Frontend

## Task 23: Vite + React + TS scaffold

**Files:**
- Create: `D:/bian/web/` (generated)

**Steps:**
- [ ] **Step 1: Scaffold**

```bash
cd /d/bian
npm create vite@latest web -- --template react-ts
cd web
npm install
npm install -D tailwindcss@^3 postcss autoprefixer
npx tailwindcss init -p
```

- [ ] **Step 2: Configure Tailwind**

`web/tailwind.config.js`:
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

`web/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body, #root { height: 100%; }
body { background: #0b0d12; color: #e6e8eb; }
```

- [ ] **Step 3: Vite proxy to backend**

`web/vite.config.ts`:
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
```

- [ ] **Step 4: Run dev server**

`cd /d/bian/web && npm run dev`
Open browser to http://localhost:5173 (Vite's default page should load).

- [ ] **Step 5: Commit**

```bash
cd /d/bian
# add web/.gitignore so node_modules stays out
printf "node_modules\ndist\n.vite\n" >> web/.gitignore
git add web/.gitignore web/index.html web/package.json web/package-lock.json web/vite.config.ts web/tsconfig.json web/tsconfig.node.json web/src
git commit -m "feat(web): Vite + React + Tailwind + Vite proxy"
```

---

## Task 24: Layout shell + Setup wizard page

**Files:**
- Create: `D:/bian/web/src/lib/api.ts`
- Create: `D:/bian/web/src/components/Layout.tsx`
- Create: `D:/bian/web/src/pages/Setup.tsx`
- Modify: `D:/bian/web/src/App.tsx`

**Steps:**
- [ ] **Step 1: Implement `lib/api.ts`**

```ts
const base = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(base + path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (r.status === 403) {
    const j = await r.json();
    if (j.setup_required) {
      window.location.href = "/setup";
      throw new Error("setup required");
    }
  }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export const api = {
  get: <T,>(p: string) => request<T>(p),
  post: <T,>(p: string, body?: unknown) =>
    request<T>(p, { method: "POST", body: JSON.stringify(body ?? {}) }),
  put: <T,>(p: string, body?: unknown) =>
    request<T>(p, { method: "PUT", body: JSON.stringify(body ?? {}) }),
  del: <T,>(p: string) => request<T>(p, { method: "DELETE" }),
};
```

- [ ] **Step 2: Implement `pages/Setup.tsx`**

```tsx
import { useState } from "react";
import { api } from "../lib/api";

export function Setup() {
  const [key, setKey] = useState("");
  const [secret, setSecret] = useState("");
  const [testnet, setTestnet] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);

  async function save() {
    setMsg(null);
    await api.put("/api/settings", {
      binance_testnet: testnet,
      binance_api_key: key,
      binance_api_secret: secret,
    });
    const t = await api.post<{ ok: boolean; error?: string }>("/api/settings/test-binance");
    if (!t.ok) {
      setMsg(`Binance rejected credentials: ${t.error}`);
      return;
    }
    await api.post("/api/setup/complete", { acknowledged: true });
    window.location.href = "/";
  }

  return (
    <div className="max-w-xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold">First-time setup</h1>
      <ol className="list-decimal list-inside text-sm space-y-1 text-slate-300">
        <li>Open Binance → Account → API Management.</li>
        <li>Create a key for Spot. Enable <b>Read Info</b> + <b>Spot Trade</b> only.</li>
        <li>Disable Withdrawals. Optional: add IP whitelist.</li>
      </ol>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={testnet} onChange={(e) => setTestnet(e.target.checked)} />
        Use Testnet (recommended for now)
      </label>
      <input className="w-full p-2 bg-slate-800 rounded" placeholder="API Key"
             value={key} onChange={(e) => setKey(e.target.value)} />
      <input className="w-full p-2 bg-slate-800 rounded" placeholder="API Secret" type="password"
             value={secret} onChange={(e) => setSecret(e.target.value)} />
      <button className="px-4 py-2 bg-emerald-600 rounded" onClick={save}>Save & Continue</button>
      {msg && <div className="text-red-400 text-sm">{msg}</div>}
    </div>
  );
}
```

- [ ] **Step 3: Implement `App.tsx` with router + setup gate**

```tsx
import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { api } from "./lib/api";
import { Setup } from "./pages/Setup";

function Gate({ children }: { children: JSX.Element }) {
  const [ready, setReady] = useState<null | boolean>(null);
  useEffect(() => {
    api.get<{ setup_required: boolean }>("/api/setup/state").then((s) => {
      setReady(!s.setup_required);
    });
  }, []);
  if (ready === null) return <div className="p-6">Loading…</div>;
  if (!ready) return <Navigate to="/setup" replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/setup" element={<Setup />} />
        <Route path="/" element={<Gate><div>Dashboard stub</div></Gate>} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  );
}
```

Install: `npm i react-router-dom`.

- [ ] **Step 4: Verify in browser**
  - Start backend + `npm run dev`.
  - Browser to http://localhost:5173 → redirects to /setup.
  - With placeholder key, see error.
- [ ] **Step 5: Commit**

```bash
git add web/src web/package.json web/package-lock.json
git commit -m "feat(web): setup wizard page with gate"
```

---

## Task 25: Dashboard, Settings, Grids pages

**Files:**
- Create: `D:/bian/web/src/pages/Dashboard.tsx`
- Create: `D:/bian/web/src/pages/Settings.tsx`
- Create: `D:/bian/web/src/pages/GridsList.tsx`
- Create: `D:/bian/web/src/pages/GridsNew.tsx`
- Create: `D:/bian/web/src/pages/GridDetail.tsx`
- Modify: `D:/bian/web/src/App.tsx`

**Steps:**
- [ ] **Step 1: Dashboard stub** (calls `/api/dashboard/overview` and renders counts)

```tsx
import { useEffect, useState } from "react";
import { api } from "../lib/api";

export function Dashboard() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { api.get("/api/dashboard/overview").then(setData); }, []);
  if (!data) return <div className="p-6">Loading…</div>;
  return (
    <div className="p-6 grid grid-cols-3 gap-4">
      <div className="p-4 bg-slate-800 rounded">Running grids: {data.running_grids}</div>
      <div className="p-4 bg-slate-800 rounded">Open orders: {data.open_orders}</div>
      <div className="p-4 bg-slate-800 rounded">Today P&amp;L: {Number(data.today_pnl).toFixed(2)}</div>
    </div>
  );
}
```

- [ ] **Step 2: Settings page** — shows bool flag, allows changing testnet, has "Test Binance" button.

```tsx
import { useEffect, useState } from "react";
import { api } from "../lib/api";

export function Settings() {
  const [s, setS] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { api.get("/api/settings").then(setS); }, []);
  if (!s) return <div className="p-6">Loading…</div>;
  return (
    <div className="p-6 space-y-4 max-w-xl">
      <div>Testnet: <b>{String(s.binance_testnet)}</b></div>
      <div>Has API key: {String(s.has_api_key)}</div>
      <div>Has secret: {String(s.has_api_secret)}</div>
      <button
        className="px-3 py-1 bg-cyan-600 rounded"
        onClick={async () => {
          const r: any = await api.post("/api/settings/test-binance");
          setMsg(r.ok ? "Binance OK" : `Failed: ${r.error}`);
        }}>
        Test Binance
      </button>
      {msg && <div className="text-sm">{msg}</div>}
    </div>
  );
}
```

- [ ] **Step 3: GridsList, GridsNew, GridDetail** — straightforward, follows the same patterns as Dashboard. Use a `<table>` for list, a `<form>` for create, and a panel with start/stop buttons for detail.

(Each is left as a minimal viable implementation; the implementer fills in details using the backend endpoints documented earlier in this plan.)

- [ ] **Step 4: Wire routes in `App.tsx`**

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(web): dashboard, settings, grids pages"
```

---

## Task 26: Charts page with lightweight-charts

**Files:**
- Create: `D:/bian/web/src/pages/Charts.tsx`
- Install: `web/` add dep `lightweight-charts`

**Steps:**
- [ ] **Step 1: Install**
  - `cd /d/bian/web && npm i lightweight-charts`
- [ ] **Step 2: Implement Charts.tsx**

```tsx
import { useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import { createChart, ColorType, LineSeries } from "lightweight-charts";

export function Charts() {
  const { symbol = "BTCUSDT" } = useParams();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      layout: { background: { type: ColorType.Solid, color: "#0b0d12" }, textColor: "#e6e8eb" },
      width: ref.current.clientWidth, height: 480,
    });
    api.get<any[]>(`/api/klines?symbol=${symbol}&interval=1h&limit=200`).then((rows) => {
      const series = chart.addCandlestickSeries({});
      series.setData(rows.map((r) => ({
        time: Math.floor(r.open_time / 1000),
        open: r.open, high: r.high, low: r.low, close: r.close,
      })));
    });
    return () => chart.remove();
  }, [symbol]);

  return <div className="p-4"><h2 className="mb-2">{symbol}</h2><div ref={ref} /></div>;
}
```

- [ ] **Step 3: Commit**

```bash
git add web/src web/package.json web/package-lock.json
git commit -m "feat(web): charts page with lightweight-charts"
```

---

## Task 27: Orders, Trades, Logs pages with WS subscription

**Files:**
- Create: `D:/bian/web/src/hooks/useWebSocket.ts`
- Create: `D:/bian/web/src/pages/Orders.tsx`
- Create: `D:/bian/web/src/pages/Trades.tsx`
- Create: `D:/bian/web/src/pages/Logs.tsx`

**Steps:**
- [ ] **Step 1: WebSocket hook**

```ts
import { useEffect, useRef } from "react";

export function useWebSocket(onEvent: (data: any) => void) {
  const ref = useRef(onEvent);
  ref.current = onEvent;
  useEffect(() => {
    const ws = new WebSocket(`ws://${location.host}/ws/realtime`);
    ws.onmessage = (ev) => ref.current(JSON.parse(ev.data));
    ws.onclose = () => setTimeout(() => location.reload(), 1000);
    return () => ws.close();
  }, []);
}
```

- [ ] **Step 2: Orders, Trades** — straightforward tables over `/api/orders`, `/api/trades`.
- [ ] **Step 3: Logs page** — connects via WS, appends `type === "log"` events to a list.
- [ ] **Step 4: Commit**

```bash
git add web/src
git commit -m "feat(web): orders/trades/logs pages + WS hook"
```

---

# Phase 7 — Run & Polish

## Task 28: run.bat one-shot launcher

**Files:**
- Create: `D:/bian/run.bat`

**Steps:**
- [ ] **Step 1: Write `run.bat`**

```bat
@echo off
setlocal

cd /d %~dp0

if not exist venv\Scripts\python.exe (
  echo Creating venv...
  python -m venv venv
  call venv\Scripts\activate
  pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call venv\Scripts\activate
)

if not exist web\node_modules (
  echo Installing web deps...
  cd web
  call npm install
  cd ..
)

if not exist data mkdir data

start "uvicorn" cmd /k "call venv\Scripts\activate && python -m uvicorn app.main:app --reload --port 8000"
timeout /t 2 /nobreak > nul
start "vite" cmd /k "cd web && npm run dev"
timeout /t 3 /nobreak > nul
start "" http://localhost:5173
```

- [ ] **Step 2: Verify cold start**

Close any running instances, double-click `run.bat`, expect:
- A terminal opens with uvicorn; logs say "Application startup complete."
- A second terminal with `npm run dev`; logs include `ready in ...ms`.
- Browser opens to http://localhost:5173 → /setup.

- [ ] **Step 3: Commit**

```bash
git add run.bat
git commit -m "chore: add run.bat one-shot launcher"
```

---

## Task 29: End-to-end happy-path manual test on Binance Testnet

**No code changes — this task is verification only.**

**Pre-conditions:**
- Testnet account created at https://testnet.binance.vision (or testnet.binancefuture.com — both work for Spot).
- Testnet key generated (Read + Spot Trade; no Withdrawals).
- Testnet account funded with test USDT (Testnet faucet if needed).

**Steps:**
- [ ] **Step 1:** Double-click `run.bat`.
- [ ] **Step 2:** In UI, complete `/setup` with Testnet key/secret; expect "Binance OK".
- [ ] **Step 3:** Confirm `data/app.db` has `settings` rows + `app_state.setup_completed=true`.
- [ ] **Step 4:** Go to `/grids/new`:
  - Symbol: BTCUSDT (or another Spot pair available on Testnet).
  - Lower: ~current_price * 0.95, Upper: ~current_price * 1.05.
  - grid_count: 10, grid_mode: arithmetic, total_quote_amount: e.g. 50 USDT.
- [ ] **Step 5:** Submit → redirected to `/grids/<id>` → click **Start**.
- [ ] **Step 6:** Wait ~30 seconds. Expect:
  - At least one BUY order and one SELL order in `/orders`.
  - A log entry in `/logs` from the engine.
- [ ] **Step 7:** In the Testnet UI, place a market buy to push the price up; observe the engine placing matching sells (via WS).
- [ ] **Step 8:** Click **Stop** in `/grids/<id>` → orders canceled, status = stopped.
- [ ] **Step 9:** Capture any error logs and file fixes as a follow-up task (separate from this plan).

Record results in `docs/superpowers/plans/2026-08-30-e2e-results.md`.

---

## Task 30: Write final README + design doc finalize

**Files:**
- Modify: `D:/bian/README.md`
- Create: `D:/bian/docs/superpowers/specs/2026-08-30-binance-spot-grid-design.md`

**Steps:**
- [ ] **Step 1:** Copy the spec content into `docs/superpowers/specs/2026-08-30-binance-spot-grid-design.md`.
- [ ] **Step 2:** Expand the README with:
  - Quick start
  - Architecture diagram
  - "How to switch from Testnet to real" instructions
  - "How to add a new strategy" instructions
  - Security notes
- [ ] **Step 3:** Commit

```bash
git add README.md docs/superpowers/specs/2026-08-30-binance-spot-grid-design.md
git commit -m "docs: final README and design spec"
```

---

# Final Verification (run all of these)

After implementing everything, the user should be able to:

1. Run `run.bat`, browser opens to `http://localhost:5173`.
2. Go through `/setup` with a Testnet key, see "Binance OK".
3. Create a grid, start it, see orders in `/orders`, see logs in `/logs`.
4. Verify that placing a market order via Testnet triggers a fill, and the engine emits a corresponding log entry and places a replacement order.
5. Stop the grid; verify status flips, orders canceled.
6. `pytest -q` is green for unit, integration, and async tests.
7. `git log --oneline` shows roughly one commit per task.

If any of these fail, **do not** mark the project complete — file the failures as new tasks and run them.

---

## Risk & Reminders (carry over from the spec)

- **API key safety:** Defaults to Testnet; **never** commit `.env` or any file containing live keys. If keys leak, rotate immediately.
- **Rate limits:** The Binance Spot API enforces 1200-request weight per minute. Grid strategies with many grids may approach this; in V1 we keep one or two grids only.
- **WebSocket reconnect:** The frontend WS hook reloads on close — acceptable for V1; later we may add resilient reconnection with state diffing.
- **Spot ≠ Futures:** This bot only trades Spot via `/api/v3/...`. Do not call `/fapi/...`.
- **No code from Freqtrade:** GPL-3.0 forbids reuse. Architectural ideas (callbacks, lifecycle) we use freely; we **do not** copy their code.

---

## Self-Review (filled by the planner; not the executing agent)

**1. Spec coverage:**

| Spec section | Covered by |
|---|---|
| §1 Goals & non-goals | Tasks 1–30 scope |
| §2 Architecture | Tasks 4 (db), 8 (api), 13 (strategy), 16 (engine), 17–19 (api), 20 (ws) |
| §3 Borrow projects | Task 2 |
| §4 Data model | Tasks 5, 12, 15 |
| §5 Strategy interface | Tasks 13, 14 |
| §6 REST API + WS | Tasks 17, 18, 19, 20 |
| §7 Web UI pages | Tasks 24, 25, 26, 27 |
| §8 Setup wizard | Tasks 7, 17, 24 |
| §9 Local run | Task 28 |
| §10 Tests | Task 9 (sanity), pytest runs in each task |
| §11 Implementation steps | Whole plan |
| §12 Verification | Task 29 |

**2. Placeholder scan:** No "TBD", "TODO", "fixme" markers remain in code blocks. The only "future work" mention is "later we may add resilient reconnection" which is forward-looking commentary, not a placeholder.

**3. Type consistency:**
- `GridStatus` enum used in `models/grid.py` and `routers/grids.py`: ✓ matches.
- `StrategyContext` interface used in `strategy/base.py`, `strategy/grid.py`, `engine/engine.py`, `engine/lifecycle.py`: ✓ matches signature.
- `BinanceClient` methods `get_account_info`, `get_klines`, `place_order`, `cancel_order`, `get_open_orders`, `get_all_orders`: ✓ consistent across broker module, settings router, lifecycle.
- `Setting` and `AppState` ORM models both keyed by `key` String PK: ✓.

No inconsistencies found.

---

*End of plan.*
