# AI Trader · Leverage / USDⓈ-M Futures 扩展 · 设计文档

**目标**: 在现有 Binance Spot AI-Trader 之上,新增 **Binance USDⓈ-M Futures (合约)** 支持:
全局单选 `market_type ∈ {spot, futures}`,fixed leverage(1-125),新增 3 个 futures-specific 风险 guards,
保留全部现有 6 个 spot guards 和 193 个测试。

**生命周期**: 与原 spec (`2026-09-01-ai-trader-design.md`) 同源,延续 "先 testnet → 阶段授权 → 实盘小额度起步"。
本次 spec 是同一架构的**横向扩展**,不动 grid engine、不动核心调度器、不动 LLM 接口。

所有决定基于 2026-09-07 与用户的 brainstorming 会话(保留所有选择记录)。

> 读者:**人 + 后续编码 agent**。每个模块都要能独立理解、独立测试。

---

## 1. 用户决策汇总(来自 brainstorming)

| # | 决策点 | 选择 | 备选 |
|---|---|---|---|
| 1 | 期货市场范围 | **只 USDⓈ-M (USDT 永续/季度)** | USDT-M + COIN-M / USDT-M + spot 保留 |
| 2 | Grid Engine 杠杆化 | **保持 spot-only** | Grid + AI-Trader 都接 leverage / 未来再说 |
| 3 | Leverage 暴露层度 | **固定 leverage**(Settings 设整数,所有订单共用) | LLM 可选 leverage (1-125, hard cap) / 符号级 leverage |
| 4 | 新增风险 guards | **leverage + margin + liquidation buffer (3 个全加)** | 只加 margin_check / 完全复用 spot guard |
| 5 | Market_type 暴露层 | **全局单选**(`AISettings.market_type` ∈ {spot, futures}) | per-symbol / 独立 AITraderFuturesService |
| 6 | 架构方案 | **BinanceFuturesClient sibling**(共享 `_base.py`) | 单类 + market_type 参数 / Broker Protocol + 类型多态 |

---

## 2. 架构总览

Futures 扩展是**横向 sibling**,不是 fork。Spot 路径代码**完全不动**,futures 路径是平行模块,
通过 lifespan 按 `AISettings.market_type` 选择 broker 注入。AI TraderService 本身不知道当前是哪种市场 —
它从 settings 读 `market_type`,用它挑选 guard 列表和 prompt 模板。

```
                ┌───────────────────────────────┐
                │   AISettings.market_type      │
                │     ∈ { "spot", "futures" }   │
                └──────────────┬────────────────┘
                               │ (读于 lifespan + PUT /settings)
                               ▼
       ┌───────────────────────────────────────────────────┐
       │  app/broker/_base.py                              │
       │    HMAC sign · _signed() · _request()              │
       │    (共享 transport — 两个 client 继承)            │
       └──────────────┬─────────────────┬───────────────────┘
              ┌────────▼─────────┐ ┌────▼─────────────────┐
              │  BinanceClient   │ │  BinanceFuturesClient│
              │  /api/v3/* spot  │ │  /fapi/v1/* + /v2/   │
              │  (existing)      │ │  (new)               │
              └────────┬─────────┘ └──────┬───────────────┘
                       │ (satisfies Broker)│
                       │   6-method         │
                       │   protocol         │
                       └──────────┬─────────┘
                                  ▼
       ┌───────────────────────────────────────────────────┐
       │              AITraderService                       │
       │  market_type-aware guards.run_all()               │
       │  market_type-aware prompt.build_messages()        │
       │  set_broker(spot_or_futures_object)               │
       └────────────────────────┬──────────────────────────┘
                                │
                  ┌─────────────┴──────────────┐
                  ▼                            ▼
   spot guard list (6 existing)       futures guard list (9 = 6 + 3 NEW)
   [1] schema_valid                    [1-6] same as spot
   [2] per_order_cap                   [7] leverage_validation   (NEW)
   [3] position_cap                    [8] margin_check          (NEW)
   [4] daily_loss_cap                  [9] liquidation_distance  (NEW)
   [5] daily_trade_cap
   [6] symbol_exclusive
```

**核心原则**
- Spot 路径是**默认**(`market_type='spot'`)。所有现有 193 个测试在升级后保持 green。
- Futures 路径是**全新增量**,通过 `market_type='futures'` 触发。
- `_base.py` 把 transport (signing + HTTP) 抽出来,两个 client 共享 — DRY 但不过度抽象。
- 新增 guard 函数**永远不**把服务 trip 到 `paused`(只 reject 当前 tick)。Service pause 只来自 daily_loss / daily_trades tripwire。

---

## 3. Components & interfaces

### 3.1 `app/broker/_base.py` (新文件)

把 `binance.py:13-58` 的 transport 抽到 base class:

```python
def now_ms() -> int: ...
def sign_query(params: dict, secret: str) -> str: ...

class _BaseClient:
    """共享 transport。Subclass 设 base_url + endpoint 路径即可。"""
    def __init__(self, api_key, api_secret, *, base_url, http_client=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        import httpx
        self._http = http_client or httpx.Client(base_url=base_url, timeout=10.0)

    def _signed(self, params: dict) -> dict:
        # 与 binance.py:40-45 完全相同
        ...

    def _request(self, method: str, path: str, *, params=None, signed=False):
        # 与 binance.py:47-57 完全相同
        ...

    def close(self):
        self._http.close()
```

`BinanceClient` 改为 `class BinanceClient(_BaseClient)`,原 7 个方法 body 不动,transport 三个方法继承自 base。

### 3.2 `app/broker/futures.py` (新文件)

```python
TESTNET_FUTURES_BASE = "https://testnet.binancefuture.com"
PROD_FUTURES_BASE    = "https://fapi.binance.com"

class BinanceFuturesClient(_BaseClient):
    def __init__(self, api_key, api_secret, *, testnet=True, http_client=None):
        super().__init__(
            api_key, api_secret,
            base_url=TESTNET_FUTURES_BASE if testnet else PROD_FUTURES_BASE,
            http_client=http_client,
        )

    # ---- 接口方法 (与 BinanceClient 同形) ----
    def get_server_time(self) -> int:                 # GET /fapi/v1/time
    def get_account_info(self) -> dict:               # GET /fapi/v2/account
    def get_symbol_info(self, symbol: str) -> dict:   # GET /fapi/v1/exchangeInfo
    def get_klines(self, symbol, interval, limit=500) -> list:  # GET /fapi/v1/klines
    def place_order(self, symbol, side, type_, *,
                    quantity, price=None, time_in_force="GTC",
                    reduce_only=False, position_side="BOTH") -> dict:
    def cancel_order(self, symbol, order_id) -> dict: # DELETE /fapi/v1/order
    def get_open_orders(self, symbol=None) -> list:   # GET /fapi/v1/openOrders
    def get_all_orders(self, symbol, limit=100) -> list:  # GET /fapi/v1/allOrders

    # ---- futures-only 方法 (被 guards 7/8/9 使用) ----
    def set_leverage(self, symbol: str, leverage: int) -> dict:  # POST /fapi/v1/leverage
    def get_position_risk(self, symbol: str | None = None) -> list[dict]:  # GET /fapi/v2/positionRisk
    def get_mark_price(self, symbol: str) -> dict:    # GET /fapi/v1/premiumIndex
```

`place_order` 增 2 个 futures-only kwargs (`reduce_only`, `position_side`),默认与 spot 行为一致。
Spot 调用方 (`service.py:530-536`) 不需要改 — 它不传这两个新 kwarg,默认即可。

### 3.3 `app/broker/__init__.py`

```python
from .binance import BinanceClient
from .futures import BinanceFuturesClient
```

### 3.4 `app/migrations.py`

3 个 idempotent migrations(追加到 `run_all_migrations()` 末尾):

```python
def _migrate_ai_settings_market_type(engine):
    if _has_column(engine, "ai_settings", "market_type"):
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE \"ai_settings\" ADD COLUMN market_type VARCHAR NOT NULL DEFAULT 'spot'"
        ))

def _migrate_ai_settings_leverage(engine):
    # leverage 是 futures-only,spot 行保留 NULL
    if _has_column(engine, "ai_settings", "leverage"):
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE \"ai_settings\" ADD COLUMN leverage INTEGER"
        ))

def _migrate_ai_settings_margin_type(engine):
    if _has_column(engine, "ai_settings", "margin_type"):
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE \"ai_settings\" ADD COLUMN margin_type VARCHAR NOT NULL DEFAULT 'ISOLATED'"
        ))
```

### 3.5 `app/models/ai_settings.py`

3 个新 mapped columns(沿用现有列风格):

```python
market_type: Mapped[str] = mapped_column(String, default="spot", nullable=False)
leverage:    Mapped[int | None] = mapped_column(Integer, nullable=True)
margin_type: Mapped[str] = mapped_column(String, default="ISOLATED", nullable=False)
```

### 3.6 `app/main.py` lifespan wire-up

替换 `main.py:101-103` 的单 client 构造为市场类型分支:

```python
from app.models.ai_settings import load_or_create

with SessionLocal() as s:
    _settings = load_or_create(s)
    market_type = _settings.market_type

if market_type == "futures":
    from app.broker import BinanceFuturesClient
    client = BinanceFuturesClient(api_key, api_secret, testnet=cfg.binance_testnet)
else:
    from app.broker import BinanceClient
    client = BinanceClient(api_key, api_secret, testnet=cfg.binance_testnet)
trader.set_broker(client)
```

`client` 类型对 `trader.set_broker()` 透明(都是 Any);运行时由 guard 的 `broker=...` kwarg 决定具体调用。

### 3.7 `app/services/ai_trader/guards.py`

3 个新 guards + `run_all` 改为 market-aware。

```python
# 新 guards(放在文件末尾,run_all 之前)

def leverage_validation(parsed, ctx, settings, *, broker) -> GuardResult:
    """确认交易所端的 leverage 与 settings 匹配。首次进入某 symbol 时
    调用 set_leverage(Binance idempotent)。"""
    try:
        positions = broker.get_position_risk(parsed["symbol"])
        if positions:
            current_lev = int(positions[0].get("leverage", 0))
            if current_lev != settings.leverage:
                # 反向设置;Binance 接受幂等
                broker.set_leverage(parsed["symbol"], settings.leverage)
        else:
            broker.set_leverage(parsed["symbol"], settings.leverage)
    except Exception as e:
        return GuardResult(False, f"leverage_set_failed:{type(e).__name__}:{e}")
    return _pass()


def margin_check(parsed, ctx, settings, *, broker, account_info) -> GuardResult:
    """required_margin = notional / leverage,可用 ≥ 80%。"""
    if parsed["action"] == "hold":
        return _pass()
    notional = abs(float(parsed["qty"]) * float(parsed["price"]))
    required_margin = notional / max(1, settings.leverage or 1)
    available = float(account_info.get("availableBalance", 0))
    if required_margin > 0.8 * available:
        return GuardResult(
            False,
            f"margin_insufficient:{required_margin:.2f} > 80% of {available:.2f}",
        )
    return _pass()


def liquidation_distance(parsed, ctx, settings, *, broker) -> GuardResult:
    """从 mark price 到估算 liquidation_price 的距离 ≥ 15%。"""
    if parsed["action"] == "hold":
        return _pass()
    try:
        sym = parsed["symbol"]
        mark = float(broker.get_mark_price(sym)["markPrice"])
        positions = broker.get_position_risk(sym)
        if not positions:
            return _pass()  # 无持仓,无所谓 liquidation
        pos_amt = float(positions[0]["positionAmt"])
        if pos_amt == 0:
            return _pass()
        entry = float(positions[0]["entryPrice"])
        liq = estimate_liq_price(
            pos_amt, entry, settings.leverage or 1, settings.margin_type
        )
        distance_pct = abs(mark - liq) / max(mark, 1e-9) * 100
        if distance_pct < 15.0:
            return GuardResult(
                False,
                f"liquidation_too_close:{distance_pct:.2f}% < 15%",
            )
    except Exception as e:
        return GuardResult(False, f"mark_price_unavailable:{type(e).__name__}:{e}")
    return _pass()


def estimate_liq_price(
    position_amt: float, entry_price: float, leverage: int, margin_type: str
) -> float:
    """纯函数。Isolated margin 近似公式:
       long:  liq ≈ entry * (1 - 1/leverage)
       short: liq ≈ entry * (1 + 1/leverage)
       Crossed 模式下相同但维护保证金率 MMR 不同 — 保守起见全按 isolated 算。
       Binance 实际公式含 maintenance margin + wallet balance;此处是早期预警,
       不是结算系统 — spec §4 标注近似性质。"""
    if position_amt == 0 or leverage <= 0 or entry_price <= 0:
        return 0.0
    if position_amt > 0:  # long
        return entry_price * (1 - 1 / leverage)
    return entry_price * (1 + 1 / leverage)  # short


# run_all 改为 market-aware
def run_all(
    parsed, ctx, settings, *,
    pnl_today, trades_today, grid_has_open_orders,
    market_type="spot",
    broker=None, account_info=None,
) -> tuple[bool, list[GuardResult]]:
    base_steps = [
        (schema_valid, {"parsed": parsed, "ctx": ctx}),
        (per_order_cap, {"parsed": parsed, "ctx": ctx, "settings": settings}),
        (position_cap, {"parsed": parsed, "ctx": ctx, "settings": settings}),
        (daily_loss_cap, {"parsed": parsed, "ctx": ctx, "settings": settings,
                          "pnl_so_far_today_usdt": pnl_today}),
        (daily_trade_cap, {"parsed": parsed, "ctx": ctx, "settings": settings,
                           "trades_today": trades_today}),
        (symbol_exclusive, {"parsed": parsed, "ctx": ctx,
                            "grid_has_open_orders": grid_has_open_orders}),
    ]
    futures_steps = []
    if market_type == "futures":
        futures_steps = [
            (leverage_validation, {"parsed": parsed, "ctx": ctx, "settings": settings,
                                    "broker": broker}),
            (margin_check, {"parsed": parsed, "ctx": ctx, "settings": settings,
                            "broker": broker, "account_info": account_info}),
            (liquidation_distance, {"parsed": parsed, "ctx": ctx, "settings": settings,
                                     "broker": broker}),
        ]
    steps = base_steps + futures_steps
    # ... 其余逻辑不变
```

### 3.8 `app/services/ai_trader/prompt.py`

`_SYSTEM_TEMPLATE` 改为函数式,根据 `market_type` 选模板:

```python
_SYSTEM_SPOT = """\
You are a conservative Binance Spot trader. ...

Constraints you MUST respect:
- Trade ONLY symbols from this whitelist: {symbols}.
- Spot only — never request margin, futures, or options.
- qty and price are positive decimals; use the latest close as your price reference.
- "reason" must reference concrete facts from the snapshot ...
"""

_SYSTEM_FUTURES = """\
You are a conservative Binance USDⓈ-M Futures (perpetual) trader. ...

Constraints you MUST respect:
- Trade ONLY symbols from this whitelist: {symbols}.
- This account uses fixed leverage {leverage}x, ISOLATED margin.
- Trade side semantics: buy = open/increase long or close short;
 sell = open/increase short or close long; hold = do nothing.
- Never suggest order quantities that exceed available margin
 (qty * price / leverage ≤ 80% of available balance).
- Never trade if mark price is within 15% of estimated liquidation price.
- "reason" must reference concrete facts from the snapshot ...
"""


def build_messages(snapshot, *, symbols_whitelist, market_type="spot", leverage=1):
    if market_type == "futures":
        system = _SYSTEM_FUTURES.format(
            symbols=", ".join(symbols_whitelist),
            leverage=leverage,
        )
    else:
        system = _SYSTEM_SPOT.format(symbols=", ".join(symbols_whitelist))
    system += "\n\n" + JSON_SCHEMA_TEXT.format(symbols=", ".join(symbols_whitelist))
    # user message 部分: 见 §4.2 (futures 模式追加 available_margin /
    # mark_price / current_position_qty 字段)
    user_lines = [...]  # 完整内容见 §4.2
    return [{"role": "system", "content": system},
            {"role": "user", "content": "\n".join(user_lines)}]
```

`parser.VALID_ACTIONS` 不变(buy/sell/hold)。Side 语义扩展在 system prompt 里讲清,parser 不解析 position_side。

---

## 4. Data flow

### 4.1 单 tick (futures mode) 流程

```
scheduler (unchanged)                          AITraderService.tick()
    │                                                  │
    ▼ ▼
load AISettings                              load market_type + leverage
    │                                                  │
    ▼ ▼
for symbol in symbols:                       for symbol in symbols:
    │                                              │
    ▼ ▼ context.gather(broker, symbol)        broker = self.broker
    │                                          snapshot = context.gather(...)
    │                                              │
    ▼ ▼                                          ▼
account = broker.get_account_info()          market_snapshot 含 futures 字段:
    │                                              - availableBalance
    │                                              - positions[]
    │                                              - mark_price
    │                                                  │
    ▼ ▼                                          ▼
messages = prompt.build_messages(            llm.chat(messages, ...)
    snapshot,                              │
    market_type=settings.market_type,  │
    leverage=settings.leverage,           │
    symbols_whitelist=[symbol])            │
    │                                          │
    ▼ ▼                                          ▼
parsed = parser.parse_response(             guards.run_all(parsed, ctx, settings,
    raw,                                              market_type='futures',
    symbol_whitelist=[symbol])                          broker=broker,
    │                                                  account_info=account,
    │                                                  pnl_today=..., trades_today=...,
    │                                                  grid_has_open_orders=...)
    │                                                  │
    ▼ ▼                                                  ▼
    ok, results = ...                            [1] schema_valid
    │                                              [2] per_order_cap (notional/lev)
    │                                              [3] position_cap (long/short aware)
    │                                              [4] daily_loss_cap
    │                                              [5] daily_trade_cap
    │                                              [6] symbol_exclusive
    │                                              [7] leverage_validation ← 可能 set_leverage
    │                                              [8] margin_check (≤ 80% of available)
    │                                              [9] liquidation_distance (≥ 15%)
    │                                                  │
    ▼ ▼                                                  ▼
all 9 pass:                                  if ok:
    qty, price = _apply_exchange_precision       order = broker.place_order(
    order = broker.place_order(symbol, side=     symbol, side=parsed['action'],
     parsed['action'], type_='limit',             type_='limit',
     quantity=qty, price=price)                    quantity=qty, price=price)
    │                                                  │
    ▼ ▼                                                  ▼
_write_decision(...)                          _write_decision(
    action, outcome='placed',                     action, market_type='futures',
    market_type='futures',                        outcome='placed', is_paper=...)
    is_paper=...)
```

### 4.2 prompt.build_messages() user-section 字段 (futures mode)

```
Symbol: BTCUSDT
Price: 67234.50
Mark price: 67238.20
Available margin (USDT): 1234.56
Current position qty (signed): 0.05 (long)
Current position entry price: 66500.00
Current position leverage: 5x
Recent 1h klines:
...
Balances: [{...USDT...}, {...other assets...}]
Open orders: [...]
GridTrader has open orders on this symbol: False
Now output your decision JSON.
```

### 4.3 AIDecision row 新增字段

```python
# app/models/ai_decision.py
market_type: Mapped[str] = mapped_column(String, default="spot", nullable=False, index=True)
leverage:    Mapped[int | None] = mapped_column(Integer, nullable=True)
```

迁移 `_migrate_ai_decision_market_type(engine)` 同 §3.4 模式。
back-compat: 旧 audit 行的 `market_type='spot'`, `leverage=NULL`。

`_compute_today_counters` 维持不变:它统计 `placed` 行的 cash flow,spot/futures 都适用。

---

## 5. Error handling

| 失败模式 | 处理 |
|---|---|
| `set_leverage` 失败(合约不存在 / 权限不足) | Guard 7 trip → `outcome=rejected`, error=`leverage_set_failed:<reason>`。Service 保持 `running`(单 symbol 失败,不波及)。 |
| `get_position_risk` 401(密钥错 / IP 未加白) | Guard 7 trip → Guard 8/9 cascade trip → guard_results 含 `leverage_validation` / `mark_price_unavailable`。Service 经 `_maybe_trip_after_tick` 解析,**保持 `running`**(新 guards 不 trip)。Operator 需在 `/status` 看到并 fix。 |
| `get_mark_price` 返回空 / 过期 | Guard 9 trip,reason=`mark_price_unavailable:<err>`。Service 保持 `running`。 |
| `place_order` 返回 `-2019` "margin insufficient" | 已在 `service.py:537-553` `place_failed` 分支内。Audit row 写出。Service 保持 `running`。 |
| `place_order` 返回 `-2021` "order would immediately trigger" | 同上。 |
| `set_leverage` 报 "leverage exceeds exchange max" (e.g. 设置 50x 但 symbol 仅 20x) | Guard 7 trip,reason=`leverage_set_failed:...`。Operator 需下调 settings.leverage。 |
| Liquidation 公式漂移(Binance 改 margin 规则) | **不在范围内**。Guard 9 是 tripwire,不是结算系统。Spec 注明 "近似公式,意图是早期预警"。 |

**`_maybe_trip_after_tick` 不变**:3 个新 guards 永不把 service trip 到 `paused`。Service pause 只来自 daily_loss / daily_trades tripwire(已被 guards 4/5 触发后 substring 解析到)。

---

## 6. Testing 计划

| 测试文件 | 内容 | 数量 |
|---|---|---|
| `tests/unit/test_binance_base.py` (新) | sign_query · _signed · _request 行为(httpx mock) | ~3 |
| `tests/unit/test_binance_futures.py` (新) | 6-method 接口契约(URL 路径 / signing / base url);set_leverage idempotent;get_position_risk / get_mark_price shape | ~10 |
| `tests/unit/test_futures_guards.py` (新) | leverage_validation trips on bad symbol;margin_check trips at 80%;liquidation_distance trips at <15%;est liq price formula (long/short) | ~8 |
| `tests/unit/test_prompt_market_type.py` (新) | futures prompt 包含 "leveraged"、"liquidation";spot prompt 包含 "spot only" | ~3 |
| `tests/unit/test_ai_settings_migration.py` (新) | 3 个新列 migration、默认值、idempotent | ~2 |
| `tests/unit/test_ai_guards.py` (改) | 现有测试加 `market_type='spot'` 默认 kwarg;新增 futures-mode tests 验证 run_all 输出 9 个 steps | +3 |
| `tests/unit/test_ai_prompt.py` (改) | 拆分:旧测试 call `build_messages(..., market_type='spot')`;新增 `market_type='futures'` 测试 | +1 |
| `tests/integration/test_paper_live_isolation.py` (改) | 验证 paper/live isolation 在 futures 下仍 work(counters 仍按 is_paper 分隔) | +2 |
| `tests/unit/test_windows_service.py` (改) | SERVICE_NAME 改名;旧名作为 install alias | +1 |
| `tests/unit/test_binance_rest.py` (不改) | spot 路径 — 保持原样 | 0 |
| `tests/unit/test_backtest.py` (不改) | spot backtest — 本 PR 不引入 futures backtest(独立 spec) | 0 |

**总计:~33 个新测试函数,~6 个改动。估算 suite 从 193 → ~226。**

测试原则:
- 新测试用 `httpx.MockTransport` 注入 httpx client,避免网络。
- Guards 测试用 `broker=Mock(spec=BinanceFuturesClient)` — 显式只 mock futures 客户端需要的方法。
- Liq price formula 是纯函数,直接 unit-test。

---

## 7. Frontend & docs 变更

### 7.1 `frontend/src/pages/Settings.tsx`

增加 2 个控件:
- 市场类型 radio: `spot` (默认) / `futures`
- Leverage number input (1-125),仅 `futures` 时显示

两者通过既有 `PUT /api/ai/settings` 端点提交,需先在 `app/api/routers/ai_trader.py` 的 `_SettingsUpdate` 增加 3 个字段。

### 7.2 `frontend/src/pages/Grids.tsx`

**不动**。Grid 保持 spot-only。

### 7.3 README.md

- Tagline "Binance Spot (no leverage)" 改 "Binance Spot + USDⓈ-M Futures"
- 架构图追加 `BinanceFuturesClient`
- 新增 "Supported markets" 章节说明全局 `market_type` switch
- "Risk philosophy" 章节追加 "Futures 模式启用 3 个新 guards (leverage / margin / liquidation)"

### 7.4 `app/main.py:157`

`FastAPI(title="Binance Spot Grid Bot")` → `FastAPI(title="Binance Grid + AI-Trader")`。

### 7.5 `scripts/windows_service.py`

- `SERVICE_NAME = "BinanceGridAI"` (新)
- `SERVICE_DISPLAY = "Binance Grid + AI-Trader"` (新)
- 旧名 `BinanceSpotGridAI` 保留作为 install alias,允许既有服务升级不破坏。

### 7.6 `app/crypto_store.py:8`

keyring `SERVICE_NAME = "binance-spot-grid-bot"` 改 `binance-trading-bot`,让 spot / futures credentials 共用 namespace(Binance Spot 和 USDⓈ-M 用同一组 API key+secret)。

---

## 8. 部署 / Rollout

1. **PR1 (本 spec)**: code + migrations + tests 一次 ship。`market_type='spot'` 是默认,既有用户零行为变化。
2. Operator 在 Settings 切换 market_type → AI-Trader 重启,改用 futures client + 9-guard 列表。
3. **第一轮 futures run 仅 testnet**。Live arming phrase `I UNDERSTAND REAL MONEY` 仍需。
4. operator 调节 leverage 数值(每次变更需在 Settings 重启 AI Trader 生效;不热加载 — 简单优先)。

---

## 9. 明确不做的内容

- ❌ Grid engine 加 leverage variant(scope 锁定:Grid 保持 spot-only)
- ❌ COIN-M markets(scope 锁定:仅 USDⓈ-M)
- ❌ LLM-chosen leverage(scope 锁定:固定 leverage)
- ❌ Futures backtest(`HistoricalFuturesBroker` + futures-aware metrics) — 独立 spec,600-800 LOC +15 tests
- ❌ Per-symbol market_type(scope 锁定:全局单选)
- ❌ Funding rate 作为 position metric(guards 仅用 mark price)
- ❌ Margin call 通知(operator 须主动 poll `/status`)

---

## 10. 开放问题

无。本 spec 由 6 个 locked 决策驱动,设计层面无歧义。后续在 plan / implementation 阶段如发现新问题,另开 spec。