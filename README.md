# drw-mm
Trading bot for DRW Market Madness.

## Architecture
Single Python asyncio process with in-memory state, subclassing simulator `Client`.

### Main modules
- Data: `bot/ncaa_source.py`, `bot/playoffstatus_source.py`, `bot/live_odds_source.py`, `bot/team_mapping.py`
- Pricing: `bot/fair_value_engine.py`
- Strategy: `bot/strategy_arbitrage.py`, `bot/strategy_pregame.py`, `bot/strategy_live.py`, `bot/inventory_reduction.py`, `bot/strategy_router.py`
- Risk/Reporting: `bot/risk_engine.py`, `bot/pnl_engine.py`, `bot/reporter.py`
- Runtime: `bot/bot.py`, `bot/main.py`, `bot/simulator_adapter.py`, `bot/state_store.py`

## Run
Required env:
- `DRW_GAME_ID`
- `DRW_TOKEN`

Optional common env:
- `DRW_BASE_URL`
- `BOT_DRY_RUN`
- `ODDS_API_KEY`

Run:
```bash
python -m bot.main
```

## Output CSVs (`./out/`)
- `positions.csv`: concise monitoring view (`display_symbol`, `qty`, avg entry estimate, top-of-book, fair value, strategy reason, unrealized pnl).
- `open_orders.csv`: active orders without redundant canceled flag.
- `fills.csv`: compact execution tape (`timestamp`, `order_id`, `display_symbol`, `price`, `traded_qty`).
- `fair_values.csv`: active fair value by symbol.

## Smoke check
```bash
python -m bot.force_order_smoke
```
Places and cancels one small test BID to validate API/order plumbing.

See `STRATEGY.md` for decision logic details.


### Odds API budget tip
With low The Odds API plans, keep `LIVE_ODDS_REFRESH_SECONDS=20` and rely on `LIVE_ODDS_IDLE_SECONDS` (default 900s) so high-frequency polling runs only during live/near-tip windows.
