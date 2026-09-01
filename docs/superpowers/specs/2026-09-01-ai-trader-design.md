# AI Trader · 设计文档

**目标**: 在现有 Binance Spot Grid Trading 平台之上,新增一个**全自动 AI 交易模组**:
LLM 每 60 秒根据市场状态输出一条 `buy | sell | hold`,经 5 道硬风控闸校验后真实下单。

**生命周期**: 先 testnet 跑稳 → 走 4 阶段审慎解锁 → 实盘小额度起步。
所有决定都基于 2026-09-01 与用户的 brainstorming 会话(保留所有选择记录)。

> 读者:**人 + 后续编码 agent**。每个模块都要能独立理解、独立测试。

---

## 1. 用户决策汇总(来自 brainstorming)

| # | 决策点 | 选择 | 备选 |
|---|---|---|---|
| 1 | LLM 决策边界 | **每笔订单**(真全自动) | 半自动调网格参数 / 混合双签 |
| 2 | 触发节奏 | **定时轮询** | 价格信号触发 / 手动 |
| 3 | 轮询间隔 | **60 秒** | 10 秒激进 / 5 分钟保守 |
| 4 | 硬风控项(全选) | 单笔上限、当日亏损、总持仓、全局开关 | — |
| 5 | LLM 接口形状 | **严格 JSON + 单轮**(引擎注入上下文) | 多轮 + function calling / JSON+补充调用 |
| 6 | 审计详粒度 | **完整路径**(prompt/response/解析/guards/order 全部) | 只记订单决定 / 只记异常 |
| 7 | 异常路径(全选) | 解析失败→hold、风控拒单→报警+继续、当日亏损上限→自动停、人急停按钮 | — |
| 8 | Testnet → Live 防护 | 双重确认 + 阶段授权门 + 全交易上限 | 选了 3 项中的全部 |

---

## 2. 架构总览

AI Trader 是**与 GridTrader 并行的独立回路**,不修改 `app/engine/lifecycle.py` 或 `app/strategy/grid.py`。它在 lifespan 中由 `AI TraderService.start()` / `stop()` 维护一条 asyncio task。

**核心回路**(每 60 秒一次 tick):

```
┌────────────────────────────────────────────────────────────────────┐
│ 60s tick                                                           │
│                                                                    │
│  context.gather() ─→ prompt.build() ─→ llm.chat() ─→ parser.parse │
│                                                         │          │
│                                                         ▼          │
│                              guards.run(parsed, ctx) ──────────────┤
│                                              │                     │
│                              ┌──── pass ────┴─── fail ─────┐       │
│                              ▼                              ▼      │
│                       binance.place_order()         skip + log      │
│                       audit row: outcome=placed    audit row: outcome=rejected │
└────────────────────────────────────────────────────────────────────┘
```

**5 个一阶模块**:
1. `context.py` — 拉价格 / 余额 / 未成交单 / 最近 30 根 K 线摘要
2. `prompt.py` — 组装 system + user 消息,内嵌 JSON schema
3. `parser.py` — 严格解析;失败 = hold
4. `guards.py` — 5 道硬风控闸(顺序串联,任一 fail = hold)
5. `audit` — `app/models/ai_decision.py` + 写入函数

**两组外部依赖**:
- 复用 `app/services/llm.py`(需扩展 `response_format=json_object`)
- 复用 `app/broker/binance.py` REST(`place_order` 必须真的实现;若未实现,需在本任务中补全)

**控制层**:
- `app/api/routers/ai_trader.py` — 8 个 REST 端点
- `app/services/ai_trader/service.py` — 状态机 + tick loop
- `app/main.py` 注册 router,lifespan 启停 service

---

## 3. 状态机

`ai_settings.status` ∈ {`idle`, `running`, `paused`, `stopped`, `error`}

转换图:

```
            ┌─── POST /start ─────────────┐
            │                             ▼
        ┌──────┐    ENABLE_OK          ┌─────────┐
        │ idle │ ────────────────────► │ running │
        └──────┘                        └─────────┘
            ▲                              │  │
            │                              │  │
   POST /reset│                             │  │ guard 4 / guard 5 hit
            │                              │  ▼
   ┌─────────┐  POST /emergency-stop  ┌──────────┐
   │ stopped │ ◄───────────────────── │ paused   │
   └─────────┘                       └──────────┘
            ▲                              │
            │       POST /resume           │
            └──────────────────────────────┘

                 5×consecutive LLM error
                 ──────────► ┌────────┐
                              │ error  │◄──── (service 自动)
                              └────────┘
                              POST /reset (with confirm)
                              ─────────► idle
```

`status` 字段持久化进 `ai_settings`,每次 tick 入口校验;若状态 ∈ {paused, stopped, error} 直接 return,不调 LLM、不写决策行(除 trip 行)。

---

## 4. 模块切分

```
app/
├── services/
│   ├── llm.py                        ← 现有;扩展 chat(..., response_format=...)
│   └── ai_trader/                    ← 新建
│       ├── __init__.py
│       ├── service.py                ← AITraderService 类 + 模块级单例
│       ├── context.py                ← gather(symbol) -> dict
│       ├── prompt.py                 ← build(context) -> messages
│       ├── parser.py                 ← parse(text) -> ParsedDecision | None
│       └── guards.py                 ← 5 个 check_* + run_all(parsed, ctx)
├── api/routers/
│   ├── ai.py                         ← 现有,不动
│   └── ai_trader.py                  ← 新建
├── models/
│   ├── ai_decision.py                ← 新建
│   └── ai_settings.py                ← 新建 (singleton row id=1)
└── main.py                           ← 注册 ai_trader router;lifespan 启停 service
```

测试新增:
```
tests/
├── unit/
│   ├── test_ai_parser.py
│   ├── test_ai_guards.py
│   └── test_ai_prompt.py
└── integration/
    ├── test_ai_trader_service.py      ← 用 mock LLMClient + mock BinanceClient
    └── test_ai_trader_router.py
```

`tests/conftest.py` 加 fixture:`mock_llm_client` 接受队列式 `side_effect=["...","..."]`,
`mock_binance_client` 捕获所有 `place_order` 调用。

---

## 5. 风控闸语义(契约)

每道闸签名一致:
```python
def check_<name>(parsed: ParsedDecision, ctx: TradeContext,
                 settings: AISettings) -> GuardResult
# GuardResult = { ok: bool, reason: str | None }
```

顺序:`guards.run_all()` 依次调用,任一 `ok=false` 即吞掉本轮(等价 hold)。

| # | 名称 | 输入字段 | 通过条件 | 失败副作用 |
|---|---|---|---|---|
| 1 | schema_valid | 全部 parsed 字段 | action ∈ {buy,sell,hold};symbol 在缓存表;qty>0;price>0;reason 长度 5–200 | 本轮 hold |
| 2 | per_order_cap | `parsed.price * parsed.qty` | ≤ `max_order_quote_usdt` | 本轮 hold |
| 3 | position_cap | 当前 base 余额×价 + 本次买 quote | ≤ `max_position_per_symbol_usdt`;`sell` 永远放行 | 本轮 hold |
| 4 | daily_loss_cap | 今天已实现亏损 + 持仓未实现(项目化估算) | > `daily_loss_cap_usdt` ⇒ 触发 | service `paused` + trip 决策行 |
| 5 | daily_trade_cap | 今天 fill 数 | < `daily_max_trades` | service `paused` + trip 决策行 |
| 6 | symbol_exclusive | 该 symbol 当前本地 GridTrader 是否有未成交订单 | **任一未成交 → 本轮 hold** | 本轮 hold |

**注 1 — "全局开关"**:这是 service 的 `enabled / status` 字段本身。
`tick()` 入口判定:`if status != 'running': return`,因此 paused / stopped / error / idle 状态都不会调 LLM。
这与 Guard 1–6 的"hold"语义独立;后者是单轮不成交,前者是服务停摆。

**注 2 — Guard 6 互斥语义**:若 `ai_settings.symbols` 与现有 GridTrader 跑同一 symbol,
该 symbol 在本地数据库有 status ∈ {pending,running} 且有未成交 open order 时,
AI Trader 本轮 hold(避免两套规则互不知情而叠加仓位)。

**额外**:5 次连续 LLM 错(解析失败或 HTTP 异常)→ service `error`,需人工 `POST /reset`。

**Live 模式默认值降级**:第一次启用 live 时,5 个阈值取"保守"默认;用户在 AI Trader 页显式解锁后切"正常"默认。

---

## 6. 数据库 schema

### `ai_settings`(singleton,id=1)

```python
class AISettings(Base):
    __tablename__ = "ai_settings"
    id: int                        # always 1
    enabled: bool                  # 总开关
    status: str                    # idle|running|paused|stopped|error
    status_reason: str | None
    started_at: datetime | None
    last_tick_at: datetime | None
    armed_for_live_at: datetime | None  # 用户填过 "I UNDERSTAND REAL MONEY" 的时刻
    max_order_quote_usdt: float        # 默认 50 (testnet) / 20 (live 起步)
    max_position_per_symbol_usdt: float  # 500 / 200
    daily_loss_cap_usdt: float         # -30 / -10
    daily_max_trades: int              # 20 / 10
    symbols: str                       # JSON list of strings, e.g. '["BTCUSDT"]'
    poll_interval_sec: int             # 60
    llm_model: str | None              # 镜像当前 LLM 配置
    updated_at: datetime
```

### `ai_decision`(每轮一行)

```python
class AIDecision(Base):
    __tablename__ = "ai_decision"
    id: int
    ts: datetime
    symbol: str
    market_snapshot: str        # JSON: {price, klines_summary, balances, open_orders}
    prompt: str                  # 完整 system + user prompt
    raw_response: str            # LLM 原始输出
    parsed: str | None           # 解析后 JSON
    action: str                  # buy|sell|hold
    guard_results: str           # JSON: 5 道闸结果
    outcome: str                 # placed|rejected|no_trade|error
    order_id: str | None
    order_status: str | None
    filled_qty: float | None
    filled_price: float | None
    error: str | None
```

索引:`(ts DESC)`、`(symbol, ts DESC)`、`(outcome, ts DESC)`。

---

## 7. REST API

| Method | Path | 说明 |
|---|---|---|
| `GET`   | `/api/ai-trader/status` | 状态、阈值、今日统计(成交 / 亏损 / 已用笔数) |
| `POST`  | `/api/ai-trader/start` | 启用。Live 首次需 body `{confirm_text: "I UNDERSTAND REAL MONEY"}`,首次成功后写 `armed_for_live_at` |
| `POST`  | `/api/ai-trader/pause` | 人工暂停 |
| `POST`  | `/api/ai-trader/resume` | 从 paused/error 恢复 |
| `POST`  | `/api/ai-trader/emergency-stop` | 立刻取消 tick,status=stopped |
| `POST`  | `/api/ai-trader/reset` | 从 stopped 重置回 idle,需 confirm_text 同上 |
| `GET`   | `/api/ai-trader/decisions?limit=50&symbol=BTCUSDT` | 分页查审计 |
| `PUT`   | `/api/ai-trader/settings` | 改风控阈值(same payload 结构) |
| `GET`   | `/api/ai-trader/dry-run?symbol=BTCUSDT` | 单轮模拟,LLM 调到但不真下单,返回解析后的 JSON 与 guards verdict |

所有 POST 在 setup gate 之外:`/api/ai-trader/*` 加入 `main.py` 的 `OPEN_PREFIXES` 让 setup wizard 能看到当前状态。

---

## 8. UI 表面(mock 壳里新增)

**新增页面 `AI Trader`**(`frontend/src/mock/pages/AITrader.tsx`),左侧 nav 加一项。

页面结构:

1. **状态卡**(顶部)
   - 大字:`status: running`,`last tick: 12s ago`
   - 4 个小指标:`trades today 4/20`、`P&L +12.5 USDT`、`loss budget -30`、`symbols BTCUSDT`
   - 进度条:loss budget / total

2. **首期启用区**
   - 状态 == `idle` 时:大按钮 `ENABLE AI TRADER`
   - 设置检测到 testnet=false 且未 armed:**点击触发双重确认 Modal**,输入 `I UNDERSTAND REAL MONEY` 才放行

3. **EMERGENCY STOP 按钮**(常驻可见,红色)
   - 点击 → `POST /emergency-stop`
   - 二次确认

4. **阈值编辑表单**
   - 单笔上限 / 持仓上限 / 当日亏损上限 / 当日笔数上限
   - 数字输入,保存 → `PUT /settings`
   - live 模式下加锁显式"提升至正常默认"按钮

5. **Decisions 表格**
   - 列:ts, symbol, action, outcome, P&L, expanded row 看 prompt/raw/parsed/guards JSON
   - 颜色:placed=蓝、rejected=黄、error/no_trade=灰

6. **右侧悬浮 Symbols 列表**
   - 多选 + 增删(默认仅 BTCUSDT)

**Settings 页面加 `LLM Configuration` 卡片**
- 复用 keyring(`service="binance-spot-grid-bot"`,slugs:`llm_api_key`、`llm_base_url`、`llm_model`)
- 保存后立即能用于 AI Trader 与现有 `/api/ai/analyze`

---

## 9. LLM 调用契约

`app/services/llm.py` 需扩展:
```python
async def chat(
    self,
    messages: list[dict],
    *,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    response_format: dict | None = None,   # 新增:{"type":"json_object"}
) -> str
```

prompt.build() 输出的 system prompt 必须:
- 声明交易只为 Binance Spot,只能用 ai_settings.symbols 列表里的交易对
- 强调下单会用 USDT 计价,且严禁"所有余额全买"等极端指令
- 内嵌 JSON schema:
  ```json
  {
    "action": "buy|sell|hold",
    "symbol": "<from whitelist>",
    "qty": <float>,
    "price": <float>,
    "reason": "<5-200 chars>"
  }
  ```
- 给出"reason"要求:具体引用近期价格行为 / 风险点,而不是模板化语言

**Prompt 大小估算**:上下文 ~600 tokens + system ~400 tokens + completion ~150 tokens ≈ 1200 tokens/轮。每天 1440 轮 → ~1.7M tokens/天。DeepSeek-cached 价格约 $0.07/M,日费 ~$0.12 量级,成本可忽略。

---

## 10. 测试

### 单元(`tests/unit/test_ai_*.py`)
- `test_ai_parser.py` — 9 种异常 JSON 输入(空、HTML、截断、缺字段、类型错、超界字符等)→ 全返回 ok=false
- `test_ai_guards.py` — 5 个 guard × ~6 个边界条件(穷举表)
- `test_ai_prompt.py` — 产出 system prompt 含 json schema,symbol 白名单正确

### 集成(`tests/integration/test_ai_trader_*.py`)
- 全循环测试,使用 `mock_llm_client = LLMClient.side_effect = ["OK json", "BAD json", ...]` 和 mock_binance_client
- happy path
- 解析失败 → outcome=no_trade
- guard 2 拒 → outcome=rejected
- guard 3 拒(buy over cap,sell 放行)
- guard 4 触发 → status=paused
- guard 5 触发 → status=paused
- 5 次连续 error → status=error
- emergency-stop 后 ticker 不再调

### 手动 Testnet 上手清单(进 README)
1. 配 Binance testnet key(已有)
2. Settings → LLM Configuration:粘 DeepSeek / OpenAI key,保存
3. AI Trader → 改阈值到保守(单笔 20 / 当日亏 -10)
4. ENABLE → 进入 running
5. 等 3 分钟看 Logs(`[ai-trader] tick` / `[ai-trader] LLM said buy` / `[ai-trader] placed O...`)
6. 进 Decisions 表挑 1-2 条验证 prompt→response→orders 全链路
7. 跑 24 小时核对 P&L 与限额

---

## 11. 上线 4 阶段(防"testnet 没测就上 prod")

| 阶段 | 准入 | 验收 | 解锁条件 |
|---|---|---|---|
| 0 dry-run | LLM 已配 | `GET /dry-run` 返回 parsed JSON 但不下单 | 手动 |
| **1 testnet** | Binance testnet key + LLM 已配 | 24h:无 guard 误触 / P&L 在阈值内 / 决策可重放 | 人主动 |
| **2 live demo** | Binance prod key + `armed_for_live_at` null | 双重确认 + 降级默认阈值(单笔 20 / 当日亏 -10) | 跑满 7 天且无 emergency-stop |
| **3 live full** | AI Trader 页"提升至正常默认"按钮 | 单笔 50 / 当日亏 -30 起 | 人为显式点 |

settings.testnet 由 true 改 false **不会**自动解锁 live;每阶段必须显式推进。

---

## 12. 风险与后果

| 风险 | 缓解 |
|---|---|
| LLM 幻觉下单"全买" | Guard 2/3 拒;schema 检查;阈值默认保守 |
| LLM 输出违反 schema | Guard 1 拒;失败 ≡ hold;10% 连续错自动切 error |
| LLM 调用超时 / 网络断 | 60s timeout;失败一次就 hold;连续 5 次切 error |
| 当日亏损超 | Guard 4 → paused,等次日凌晨 00:00 UTC 自动重置 + 人工 Resume |
| 用户开大阈值后亏损 | live 必须双重确认 + 降级阈值起步 |
| 与现有 GridTrader 仓位叠加 | symbols 列表由用户在 AI Trader 页独占;**Guard 6** 保证 symbol 互斥:同一 symbol 出现 pending order 时 AI Trader 自动 skip |
| 审计数据膨胀 | 1440 行/天 × ~10KB = ~14MB/天,可容忍。后续可加 retention 90 天滚动清理 |

---

## 13. 已澄清的开放问题

- [x] LLM 决策边界:每笔订单真全自动
- [x] 节奏:60 秒轮询
- [x] 风控:5 道硬闸(单笔 / 当日亏 / 持仓 / 全局开关)
- [x] 接口:严格 JSON 单轮
- [x] 审计:完整路径
- [x] live 过渡:双重确认 + 阶段门 + 默认阈值降级

---

## 14. 不做(YAGNI)

- ❌ 多轮 function calling(单轮够用,审计更清晰)
- ❌ 跨 symbol 投资组合优化(超 scope,留给后续)
- ❌ 自动策略回测模块(LLM 行为不重现,留作人工)
- ❌ Telegram / 邮件通知(后续,如果用户要)
- ❌ 多 LLM Provider A/B(留口子,Settings 加 dropdown,但 v1 只支持 OpenAI 兼容一种)

---

## 15. 元信息

- 设计日期:2026-09-01
- 关联实现计划:`docs/superpowers/plans/2026-09-01-ai-trader.md`(由 writing-plans skill 生成)
- 影响范围:`app/services/ai_trader/`、`app/api/routers/ai_trader.py`、`app/models/ai_*.py`、`frontend/src/mock/pages/AITrader.tsx`、Settings 页面加 LLM 配置
- 数据库变更:新增 2 张表(`ai_settings` / `ai_decision`)
- 依赖变更:`requirements.txt` 不变;`.env` 增加可选 `LLM_*` 键
- 估计工作量:中(约 1–2 天实施 + 1 天 testnet 跑稳)
