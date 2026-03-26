# DRW Market Madness Bot Strategy Guide

## Runtime pipeline
`bot/bot.py` loops through:
1. Account/books/orders resync.
2. NCAA scoreboard + bracket refresh.
3. PlayoffStatus refresh.
4. Odds refresh.
5. Fair-value recompute.
6. Strategy routing + risk checks.
7. CSV reporting.

## Strategy priority (`bot/strategy_router.py`)
1. Eliminated mispricing (`strategy_arbitrage.eliminated_mispricing`)
2. Basket arbitrage (`strategy_arbitrage.basket_arbitrage`)
3. Pregame dislocation (`strategy_pregame`)
4. Live dislocation (`strategy_live`)
5. Inventory reduction (`inventory_reduction`)

## Data and valuation
- Team mapping is fail-closed; unresolved symbols are blocked from trading.
- NCAA scoreboard supplies live/upcoming/final state.
- NCAA bracket supplies elimination/fixed settlement truth.
- Odds source builds median no-vig consensus + quality metadata.
- Fair value modes: `fixed`, `live`, `pregame`, `baseline`.

## Key behavior improvements
- Two-snapshot live confirmation to avoid immediate trades on one noisy jump.
- Symmetric pregame strategy (can emit both buys and sells).
- Explicit cover/reduce paths for existing inventory.
- Zero-FV guard blocks non-fixed teams from accidental zero-value trading.

## Risk controls (`bot/risk_engine.py`)
Order candidates are rejected on unresolved mapping, stale sources, self-cross, cap breaches, missing FV confirmation, and drawdown pressure (reduce-only behavior preserved).

## CSV semantics
- `positions.csv` is concise and avoids sparse/mostly-empty diagnostic columns.
- `avg_entry_price_est` is sourced from in-memory fills when available, otherwise server snapshot average if supplied.
- If no trusted entry is available, `entry_source=unknown_after_restart` and unrealized PnL is left blank.
- `fills.csv` now includes an explicit `timestamp` column so rows are not shifted/misaligned.

## Signed quantity convention
- Positive qty = buy/BID.
- Negative qty = sell/ASK.
This is preserved end-to-end through adapter and simulator client order transport.
