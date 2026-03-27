from types import SimpleNamespace

from bot.bot import SimulatorBot


def test_should_poll_live_odds_when_team_states_unavailable():
    fake = SimpleNamespace(state_store=SimpleNamespace(state=SimpleNamespace(team_states={})))
    assert SimulatorBot._should_poll_live_odds(fake, now_ts=0.0) is True
