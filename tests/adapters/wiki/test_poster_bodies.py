"""Проверяет общий шаг байтов: порядок адресов, один запрос на адрес, молчание сети."""

from __future__ import annotations

from dataclasses import dataclass, field

from torrcast.adapters.wiki.poster_bodies import PosterBodies
from torrcast.domain.facts.ask import Ask

SMALL = "https://m.media-amazon.com/one._V1_UX500_.jpg"
RAW = "https://m.media-amazon.com/one._V1_.jpg"
PICTURE = b"\xff\xd8\xff\xe0picture"

HERE = Ask("Матрица", 1999, "movie", "The Matrix")
THERE = Ask("Матрица: Перезагрузка", 2003, "movie", "The Matrix Reloaded")


@dataclass
class FakeBytesClient:
    """Двойник загрузчика: помнит порядок адресов и отвечает по заранее заданной карте."""

    bodies: dict[str, bytes] = field(default_factory=dict)
    broken: set[str] = field(default_factory=set)
    asked: list[str] = field(default_factory=list)

    def fetch(self, address: str, timeout: float) -> bytes:
        self.asked.append(address)
        if address in self.broken:
            raise OSError("оборвалось")
        return self.bodies.get(address, b"")


def test_the_addresses_are_tried_in_the_order_the_verdict_named_them() -> None:
    """Первый адрес отдал байты - за вторым не идут."""
    files = FakeBytesClient({SMALL: PICTURE, RAW: b"raw"})
    assert PosterBodies(files).bodies({HERE: [SMALL, RAW]}, 5.0) == {HERE: PICTURE}
    assert files.asked == [SMALL]


def test_a_broken_first_address_does_not_leave_the_tile_broken() -> None:
    """🔴 Обрыв на первом адресе - не битая плитка: приговор назвал и второй."""
    files = FakeBytesClient({RAW: PICTURE}, broken={SMALL})
    assert PosterBodies(files).bodies({HERE: [SMALL, RAW]}, 5.0) == {HERE: PICTURE}
    assert files.asked == [SMALL, RAW]


def test_one_address_shared_by_two_pictures_is_fetched_once() -> None:
    """У сборника и его части постер общий: адрес качается один раз на обоих."""
    files = FakeBytesClient({SMALL: PICTURE})
    got = PosterBodies(files).bodies({HERE: [SMALL], THERE: [SMALL]}, 5.0)
    assert got == {HERE: PICTURE, THERE: PICTURE}
    assert files.asked == [SMALL]


def test_a_picture_whose_addresses_all_stay_silent_is_absent_not_broken() -> None:
    """Молчат все адреса - картины в ответе нет вовсе, и это не исключение."""
    files = FakeBytesClient(broken={SMALL, RAW})
    assert PosterBodies(files).bodies({HERE: [SMALL, RAW]}, 5.0) == {}


def test_a_picture_without_addresses_is_not_asked_of_the_network() -> None:
    """Приговор промолчал - в сеть не ходят вовсе."""
    files = FakeBytesClient()
    assert PosterBodies(files).bodies({HERE: []}, 5.0) == {}
    assert files.asked == []
