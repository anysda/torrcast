"""Мера снабжения отличает живой контакт от достаточной доставки."""

from torrcast.domain.swarm_supply import ENOUGH, swarm_supply
from torrcast.ports.json_value import JsonValue


def test_supply_is_source_bytes_per_second_against_the_file_rate() -> None:
    status: dict[str, JsonValue] = {
        "download_speed": 417_522.25,
        "active_peers": 1,
        "file_stats": [{"id": 7, "path": "film.mkv", "length": 4_995_000_000}],
    }

    measured = swarm_supply(status, file_index=7, duration=3600.0)

    assert measured is not None
    ratio, got, need = measured
    assert round(got, 2) == 3.34
    assert round(need, 2) == 11.10
    assert round(ratio, 2) == 0.30 < ENOUGH


def test_an_unreported_speed_is_unknown_not_zero_supply() -> None:
    status: dict[str, JsonValue] = {"file_stats": [{"id": 0, "length": 1000}]}

    assert swarm_supply(status, 0, 10.0) is None
