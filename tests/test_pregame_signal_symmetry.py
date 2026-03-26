from bot.models import BotState, ContractMeta, TeamFairValue, TeamTournamentState, OrderBook, BookLevel, LiveGameProb
from bot.strategy_pregame import PregameStrategy
from bot.risk_engine import RiskEngine


def test_pregame_buy_sell_symmetry():
    state = BotState()
    import time
    now = time.time()
    state.set_source_timestamp("odds", now)
    state.set_source_timestamp("books", now)
    state.set_source_timestamp("ncaa", now)
    state.contracts["A"] = ContractMeta("A", "A", "a")
    state.team_states["a"] = TeamTournamentState("A", "a", True, False, True, "ROUND_32", "g1", None, None, "upcoming", now)
    state.live_game_probs["g1"] = LiveGameProb("g1", "a", "b", 0.5, 0.5, 4, 10_000, True, False, 1.0)
    state.fair_values["A"] = TeamFairValue("A", "A", 9.0, None, 10.0, 10.0, None, "pregame", now)

    state.order_books["A"] = OrderBook("A", 10_000, bids=(BookLevel(12, 3),), asks=(BookLevel(8, 3),))
    out = PregameStrategy(RiskEngine()).run(state)
    sides = {o.side for o in out}
    assert "buy" in sides and "sell" in sides
