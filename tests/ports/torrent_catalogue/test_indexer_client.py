"""Зеркало договора клиента индексеров: названы ровно те ручки, что зовёт круг поиска."""

from __future__ import annotations

from torrcast.ports.torrent_catalogue import IndexerClient, RawRow


class _Prowlarr:
    """Настоящий клиент: ручек у него больше, чем спрашивает договор."""

    def __init__(self) -> None:
        self.cap_floor = 1.0
        self.over_goal = False
        self.asked: list[str] = []
        self.budget = 8.0

    def search(self, query: str, limit: int = 100) -> list[RawRow]:
        self.asked.append(query)
        return [query]

    def late(self, wait: float = 0.0) -> list[RawRow]:
        return []

    def spare(self) -> float:
        return self.budget


def test_the_real_client_of_an_adapter_answers_the_whole_contract() -> None:
    """Клиент адаптера подходит договору целиком - и лишние доводы ему не мешают."""
    carried: IndexerClient = _Prowlarr()

    assert carried.search("кино") == ["кино"]
    assert carried.late() == []
    assert carried.spare() == 8.0


def test_the_floor_of_the_next_circle_is_a_slot_the_top_up_moves() -> None:
    """Пол бюджета круга - не свойство клиента, а ручка: добор её двигает и возвращает."""
    client: IndexerClient = _Prowlarr()

    client.cap_floor = 10.0

    assert client.cap_floor == 10.0
    assert client.over_goal is False, "частный бюджет за целью свежему клиенту не выдан"
