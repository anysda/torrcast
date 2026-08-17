"""Проверяет форму запроса на проводе: её должен пережить санитайзер Prowlarr."""

from torrcast.domain.wire_query import wire_query


def test_wire_query_разводит_склеенные_знаком_слова() -> None:
    """TC-129: Prowlarr вырезает такой знак, не ставя пробела, и в индексер уходит
    несуществующее слово ``SteinsGate`` - ноль строк там, где их 96."""
    assert wire_query("Steins;Gate") == "Steins Gate"
    assert wire_query("Fate/Zero") == "Fate Zero"


def test_wire_query_не_трогает_живые_знаки() -> None:
    """Точка, дефис и апостроф до индексера доезжают целыми, и выдача по ним живая."""
    for query in ("F.R.I.E.N.D.S.", "WALL-E", "Ocean's Eleven", "Fast & Furious", "Amélie"):
        assert wire_query(query) == query
