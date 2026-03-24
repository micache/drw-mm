# drw-mm
Trading bot for DRW Market Madness.

## v1 architecture (implemented)
Single Python process, in-memory state only, subclassing the provided simulator `Client`.

### Implemented module layout
- `bot/config.py`
- `bot/models.py`
- `bot/state_store.py`
- `bot/simulator_adapter.py`
- `bot/ncaa_source.py`
- `bot/playoffstatus_source.py`
- `bot/live_odds_source.py`
- `bot/team_mapping.py`
- `bot/fair_value_engine.py`
- `bot/pnl_engine.py`
- `bot/risk_engine.py`
- `bot/strategy_arbitrage.py`
- `bot/strategy_live.py`
- `bot/strategy_router.py`
- `bot/reporter.py`
- `bot/bot.py`
- `bot/main.py`

## Run
Environment variables:

- `DRW_GAME_ID`
- `DRW_TOKEN`
- optional: `DRW_BASE_URL`, `BOT_DRY_RUN`, `ODDS_API_KEY`

Run:

```bash
python -m bot.main
```

CSV outputs are written to `./out/`.
