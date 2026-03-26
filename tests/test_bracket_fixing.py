from bot.ncaa_source import NcaaSource
from bot.team_mapping import TeamMapper


def test_no_fixed_without_bracket_truth():
    source = NcaaSource(None, "", TeamMapper())
    scoreboard = [{"id": "1", "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"}, "gameState": "final", "bracketRound": "SWEET_16"}]
    states = source.refresh_live_games(scoreboard)
    assert states["a"].fixed_settlement is None


def test_fixed_after_bracket_truth():
    source = NcaaSource(None, "", TeamMapper())
    states = {"a": source.refresh_live_games([]).get("a")} if False else {}
    merged = source.refresh_bracket_truth({"games": [{"round": "SWEET_16", "loser": {"name": "A"}, "winner": {"name": "B"}}]}, {})
    assert merged["a"].fixed_settlement == 4.0
