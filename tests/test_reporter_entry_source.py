from bot.models import BotState, ContractMeta
from bot.pnl_engine import PnlEngine


def test_unknown_entry_after_restart():
    state = BotState()
    state.positions_raw["A"] = 2
    state.contracts["A"] = ContractMeta("A", "A", "a")
    views = PnlEngine().build_position_views(state)
    assert views[0].avg_entry_price is None
    assert views[0].entry_source == "unknown_after_restart"
