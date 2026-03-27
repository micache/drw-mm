# TEST_INSTRUCTION

This document explains how to run tests in this repository and what each test checks.

## 1) Prerequisites

From the repository root:

```bash
cd /Users/macbook/Documents/workspace/drw-mm
python -m pip install -r requirements.txt
python -m pip install pytest
```

Notes:
- `pytest` is the test runner.
- Project tests live in the `tests/` folder.

## 2) Run All Tests

Run the full test suite:

```bash
python -m pytest
```

Useful variants:

```bash
# More detailed output
python -m pytest -v

# Stop on first failure
python -m pytest -x

# Show print/log output in real time
python -m pytest -s
```

## 3) Run Specific Tests

Run one test file:

```bash
python -m pytest tests/test_team_mapping.py
```

Run one test function:

```bash
python -m pytest tests/test_team_mapping.py::test_aliases
```

Filter by keyword:

```bash
python -m pytest -k "live or pregame"
```

## 4) What Each Test Means

### tests/test_bracket_fixing.py
- `test_no_fixed_without_bracket_truth`
  - Verifies NCAA live scoreboard data alone does not force a fixed settlement value.
- `test_fixed_after_bracket_truth`
  - Verifies bracket truth data sets a fixed settlement when winner/loser outcome is known.

### tests/test_live_confirmation.py
- `test_one_snapshot_jump_blocks_first_trade`
  - Verifies live strategy avoids trading immediately after a sudden one-snapshot probability jump (confirmation guard).

### tests/test_odds_game_matching_fallback.py
- `test_fair_value_engine_uses_team_match_when_ids_differ`
  - Verifies fair value still computes when odds game ID and NCAA game ID do not match, using team-name matching fallback.
- `test_live_strategy_uses_team_match_when_ids_differ`
  - Verifies live strategy can produce orders with ID mismatch by matching on team identity.
- `test_pregame_strategy_uses_team_match_when_ids_differ`
  - Verifies pregame strategy can produce orders with ID mismatch by matching on team identity.

### tests/test_pregame_signal_symmetry.py
- `test_pregame_buy_sell_symmetry`
  - Verifies pregame strategy can produce both buy and sell opportunities when order book is symmetrically mispriced around fair value.

### tests/test_reporter_entry_source.py
- `test_unknown_entry_after_restart`
  - Verifies PnL reporting marks average entry source as `unknown_after_restart` when position exists but entry price history is unavailable (for example after process restart).

### tests/test_side_plumbing.py
- `test_signed_qty_side_semantics`
  - Verifies adapter side semantics: bid sends positive quantity, ask sends negative quantity.

### tests/test_simulator_adapter_parsing.py
- `test_sync_fills_accepts_dict_payload_and_side_sign`
  - Verifies fill sync accepts dict payload format and applies side sign correctly.
- `test_sync_account_reads_top_level_avg_entries`
  - Verifies account sync reads average entry prices from top-level `avg_entry_prices`.
- `test_sync_fills_accepts_tuple_rows_payload`
  - Verifies fill sync also accepts tuple/list row payload format.
- `test_sync_account_reads_nested_position_stats_avg_entries`
  - Verifies account sync can read average entry prices from nested `position_stats`.

### tests/test_team_mapping.py
- `test_aliases`
  - Verifies team-name normalization and alias handling (for example `Miami FL` vs `Miami OH`, saint/st abbreviations, punctuation cases).

### tests/test_zero_fv_guard.py
- `test_zero_fv_blocked_for_alive_unfixed`
  - Verifies risk engine blocks orders when a still-alive, unfixed contract has fair value equal to zero (safety guard against invalid pricing).

## 5) Typical Workflow

1. Run full suite before opening a PR:
   ```bash
   python -m pytest -v
   ```
2. If a test fails, rerun only that file/function for quick iteration.
3. After fixing, run full suite again.

## 6) Troubleshooting

If `pytest` is not found:

```bash
python -m pip install pytest
```

If import errors occur from `bot` modules:
- Ensure you are running from repository root (`drw-mm`).
- Use `python -m pytest` (not bare `pytest`) to keep interpreter/path behavior consistent.
