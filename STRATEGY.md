# DRW Market Madness Bot Strategy Guide

This document explains how the current bot works end-to-end, with emphasis on **how strategy decisions are made** and **which module is responsible for each step**.

---

## 1) Runtime flow (high level)

The bot runs as one async process (`python -m bot.main`) and continuously loops through:

1. **Simulator state sync** (positions, open orders, books)
2. **External source refresh** (NCAA status, PlayoffStatus probabilities, live odds)
3. **Fair value recomputation**
4. **Strategy evaluation**
5. **Order placement** (unless `BOT_DRY_RUN=true`)
6. **CSV reporting**

Main orchestrator: `bot/bot.py`.

---

## 2) Strategy architecture and priority

Strategy execution is orchestrated by `StrategyRouter` in `bot/strategy_router.py`.

Priority order:

1. `eliminated_mispricing` (from `bot/strategy_arbitrage.py`)
2. `basket_arbitrage` (from `bot/strategy_arbitrage.py`, gated by config)
3. `live.run` (from `bot/strategy_live.py`)

All candidate orders then pass risk checks before they are returned by the strategy modules.

---

## 3) Core inputs used by strategy

Strategies consume a shared in-memory `BotState` (`bot/models.py` + `bot/state_store.py`) containing:

- latest order books
- server positions/open orders
- fair values
- NCAA team state (live/finished flags)
- PlayoffStatus probabilities
- live game probabilities

### Source modules

- `bot/playoffstatus_source.py`: baseline tournament probabilities by team.
- `bot/ncaa_source.py`: game-state and round-status context.
- `bot/live_odds_source.py`: live win-probability updates for active games.

---

## 4) Fair value engine (what strategy trades against)

`bot/fair_value_engine.py` builds per-symbol fair values with three modes:

- **fixed**: eliminated team has known settlement
- **baseline**: from PlayoffStatus probabilities
- **live**: baseline adjusted by live game win probability

The active fair value used by strategy is `TeamFairValue.active_fv`.

---

## 5) Strategy A: Eliminated-team mispricing

Module: `bot/strategy_arbitrage.py` (`eliminated_mispricing`)

Logic:

- only for symbols whose FV mode is `fixed` and settlement is known
- if `best_ask` is below fixed settlement by at least `ELIMINATED_MIN_EDGE`, generate buy
- if `best_bid` is above fixed settlement by at least `ELIMINATED_MIN_EDGE`, generate sell

Position sizing is small and capped by top-of-book and risk checks.

---

## 6) Strategy B: Basket arbitrage

Module: `bot/strategy_arbitrage.py` (`basket_arbitrage`)

### Economic idea

The sum of all 68 final settlements is constant (224), so baskets can be mispriced in aggregate.

### Current implementation safeguards

- Disabled by default unless `ENABLE_BASKET_ARBITRAGE=true`
- Requires exactly 68 contracts present
- Uses size `1`
- Blocks repeated stacking via `BASKET_MAX_NET_PER_SYMBOL`
- Requires valid positive prices (`0 < price <= 64`) and sufficient size on both sides

Trigger conditions:

- `224 - total_ask >= BASKET_MIN_EDGE` -> long basket
- `total_bid - 224 >= BASKET_MIN_EDGE` -> short basket

> Note: basket logic evaluates aggregate edge, not per-leg edge.

---

## 7) Strategy C: Live dislocation

Module: `bot/strategy_live.py` (`run`)

Logic:

- only symbols with fair-value mode `live`
- requires fresh live odds
- compares market vs live fair value using `LIVE_ENTRY_BUFFER`
- buys when market ask is sufficiently below FV
- sells when market bid is sufficiently above FV

Additional guard:

- if live probabilities jump too quickly (`ODDS_JUMP_CIRCUIT_BREAKER`), skip immediate trading that cycle.

---

## 8) Risk guardrails

Module: `bot/risk_engine.py`

Every candidate order must pass:

- quantity > 0
- projected position cap (`MAX_ABS_POSITION`)
- live strategy tighter cap (`LIVE_MAX_POSITION`)
- stale-data checks (books/NCAA/odds)
- self-cross prevention with own resting orders
- MTM threshold buffer check near contest drawdown limit

If any check fails, candidate is dropped.

---

## 9) Order execution path

1. `StrategyRouter.evaluate(...)` returns candidates.
2. `bot/bot.py` strategy loop iterates candidates.
3. Adapter submits via simulator client:
   - buy: positive quantity
   - sell: negative quantity
   - order_type: `LIMIT` by default (`SIM_ORDER_TYPE` override)

The strategy loop runs event-driven and also wakes at least once per second.

---

## 10) Reporting outputs

Main reporter module: `bot/reporter.py`

- `positions.csv`
- `open_orders.csv`
- `fills.csv`
- `fair_values.csv`

`positions.csv` is intentionally concise for runtime monitoring:

- `display_symbol`
- `qty`
- `avg_entry_price`
- `best_bid`
- `best_ask`
- `mark_price`
- `fair_value`
- `unrealized_pnl`

---

## 11) Config knobs most relevant to strategy

Defined in `bot/config.py`:

- `BOT_DRY_RUN`
- `ELIMINATED_MIN_EDGE`
- `BASKET_MIN_EDGE`
- `ENABLE_BASKET_ARBITRAGE`
- `BASKET_MAX_NET_PER_SYMBOL`
- `LIVE_ENTRY_BUFFER`
- `ODDS_FRESHNESS_SECONDS`
- `ODDS_JUMP_CIRCUIT_BREAKER`
- `MAX_ABS_POSITION`, `LIVE_MAX_POSITION`

---

## 12) Smoke test for order plumbing

Use `python -m bot.force_order_smoke` to place and cancel one small test order.

This validates:

- credentials
- connectivity
- order placement/cancel endpoint behavior

It is separate from the full strategy pipeline.
