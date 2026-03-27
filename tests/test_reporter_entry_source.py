from types import SimpleNamespace

from bot.bot import SimulatorBot
from bot.models import BookLevel, BotState, ContractMeta, OrderBook
from bot.pnl_engine import PnlEngine


def test_unknown_entry_after_restart():
    state = BotState()
    state.positions_raw["A"] = 2
    state.contracts["A"] = ContractMeta("A", "A", "a")
    views = PnlEngine().build_position_views(state)
    assert views[0].avg_entry_price is None
    assert views[0].entry_source == "server_snapshot_qty_only"


def test_backfill_avg_entry_from_mark_for_qty_only_snapshot():
    state = BotState()
    state.positions_raw["A"] = -8
    state.contracts["A"] = ContractMeta("A", "A", "a")
    state.order_books["A"] = OrderBook(
        contract_id="A",
        timestamp=0.0,
        bids=(BookLevel(price=10.0, qty=1),),
        asks=(BookLevel(price=12.0, qty=1),),
    )
    fake_bot = SimpleNamespace(state_store=SimpleNamespace(state=state), pnl_engine=PnlEngine())

    SimulatorBot._backfill_missing_avg_entries_from_mark(fake_bot)

    assert state.avg_entry_by_symbol["A"] == 11.0
    assert state.entry_source_by_symbol["A"] == "server_snapshot_mark_backfill"
