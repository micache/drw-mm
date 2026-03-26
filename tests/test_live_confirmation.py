import time

from bot.models import BotState, ContractMeta, TeamFairValue, TeamTournamentState, OrderBook, BookLevel, LiveGameProb
from bot.strategy_live import LiveStrategy
from bot.risk_engine import RiskEngine


def _mk_state(p):
    s = BotState()
    now = time.time()
    s.set_source_timestamp("odds", now)
    s.set_source_timestamp("books", now)
    s.set_source_timestamp("ncaa", now)
    s.contracts["A"] = ContractMeta("A", "A", "a")
    s.team_states["a"] = TeamTournamentState("A", "a", True, True, False, "ROUND_32", "g1", now, None, None, "live", now)
    s.live_game_probs["g1"] = LiveGameProb("g1", "a", "b", p, 1 - p, 4, now, True, True, 1.0)
    s.fair_values["A"] = TeamFairValue("A", "A", 9.0, 10.0, None, 10.0, None, "live", now)
    s.order_books["A"] = OrderBook("A", now, bids=(BookLevel(11.2, 3),), asks=(BookLevel(8.8, 3),))
    return s


def test_one_snapshot_jump_blocks_first_trade():
    strat = LiveStrategy(RiskEngine())
    out1 = strat.run(_mk_state(0.50))
    out2 = strat.run(_mk_state(0.70))
    assert out1
    assert not out2
