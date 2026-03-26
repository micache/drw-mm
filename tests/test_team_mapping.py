from bot.team_mapping import normalize_team_name, TeamMapper


def test_aliases():
    mapper = TeamMapper()
    assert mapper.normalize("Miami FL") == "miami"
    assert mapper.normalize("Miami OH") == "miami oh"
    assert mapper.normalize("St Johns") == "st johns"
    assert mapper.normalize("Saint Marys") == "st marys"
    assert mapper.normalize("Michigan St") == "michigan st"
    assert mapper.normalize("Iowa St") == "iowa st"
    assert normalize_team_name("St. John's") == "st john s"
