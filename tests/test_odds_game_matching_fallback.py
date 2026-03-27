import time

from bot.fair_value_engine import FairValueEngine
from bot.models import BotState, ContractMeta, LiveGameProb, OrderBook, BookLevel, TeamFairValue, TeamProbabilities, TeamTournamentState
from bot.risk_engine import RiskEngine
from bot.strategy_live import LiveStrategy
from bot.strategy_pregame import PregameStrategy


def _base_state(live: bool) -> BotState:
    now = time.time()
    state = BotState()
    state.set_source_timestamp("odds", now)
    state.contracts["A"] = ContractMeta("A", "A", "a")
    state.team_states["a"] = TeamTournamentState(
        team_name="A",
        normalized_team_name="a",
        alive=True,
        in_live_game=live,
        has_upcoming_game=(not live),
        current_round="ROUND_32",
        game_id="ncaa-g-123",
        eliminated_round=None,
        fixed_settlement=None,
        ncaa_status_mode=("live" if live else "upcoming"),
        last_status_ts=now,
    )
    # Different id namespace than NCAA game id.
    state.live_game_probs["odds-g-9"] = LiveGameProb(
        game_id="odds-g-9",
        home_team_normalized="a",
        away_team_normalized="b",
        home_win_prob=0.62,
        away_win_prob=0.38,
        bookmakers_used=4,
        source_timestamp=now,
        is_fresh=True,
        is_live=live,
        odds_quality_score=1.0,
    )
    state.order_books["A"] = OrderBook("A", now, bids=(BookLevel(12.0, 5),), asks=(BookLevel(8.0, 5),))
    return state


def test_fair_value_engine_uses_team_match_when_ids_differ():
    state = _base_state(live=True)
    state.team_probs["a"] = TeamProbabilities(
        team_name="A",
        normalized_team_name="a",
        p_r32=1.0,
        p_s16=0.5,
        p_e8=0.25,
        p_f4=0.12,
        p_final=0.06,
        p_champion=0.03,
        baseline_fv=9.0,
        source_timestamp=time.time(),
    )
    out = FairValueEngine().recompute_all(state)
    assert out["A"].live_fv is not None


def test_live_strategy_uses_team_match_when_ids_differ():
    state = _base_state(live=True)
    now = time.time()
    state.set_source_timestamp("books", now)
    state.set_source_timestamp("ncaa", now)
    state.fair_values["A"] = TeamFairValue("A", "A", 9.0, 10.0, None, 10.0, None, "live", now)
    out = LiveStrategy(RiskEngine()).run(state)
    assert out


def test_pregame_strategy_uses_team_match_when_ids_differ():
    state = _base_state(live=False)
    now = time.time()
    state.set_source_timestamp("books", now)
    state.set_source_timestamp("ncaa", now)
    state.fair_values["A"] = TeamFairValue("A", "A", 9.0, None, 10.0, 10.0, None, "pregame", now)
    out = PregameStrategy(RiskEngine()).run(state)
    assert out
