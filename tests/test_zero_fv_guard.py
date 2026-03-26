from bot.models import BotState, ContractMeta, TeamFairValue
from bot.risk_engine import RiskEngine


def test_zero_fv_blocked_for_alive_unfixed():
    state = BotState()
    state.contracts["A"] = ContractMeta(display_symbol="A", team_name="A", normalized_team_name="a")
    state.fair_values["A"] = TeamFairValue("A", "A", 0.0, None, None, 0.0, None, "baseline", 0.0)
    decision = RiskEngine().check_order(state, "A", "sell", 1.0, 1, "live_dislocation")
    assert not decision.ok
