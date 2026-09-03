"""Зеркало :mod:`hass.hit_posters`: имя картинки в выдаче сразу, байты - следом."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from hass.hit_posters import _CHECKED, FIELD, HitPosters
from hass.poster_shelf import PosterShelf
from torrcast.domain.json_value import JsonValue

POSTER = b"\xff\xd8\xff\xe0poster"
KEPT = b"\x89PNG\r\n\x1a\nkept"

#: Сколько ждём фоновый поход в пробе, секунды. Он весь на подделках и стоит миллисекунды;
#: потолок - против зависшей пробы, а не против медленной сети.
_SETTLE = 5.0
#: За сколько обязана вернуться выдача, пока картинка ещё ищется, секунды. Ждать её тут
#: значило бы сложить время поиска со временем похода в Википедию.
_QUICK = 0.5


@dataclass
class FakePoster:
    """Двойник похода за постером: помнит, о чём спрашивали, и отвечает, чем велено."""

    body: bytes | None = POSTER
    gate: threading.Event | None = None
    asked: list[tuple[str, int | None, str]] = field(default_factory=list)

    def __call__(self, title: str, year: int | None, kind: str, timeout: float) -> bytes | None:
        self.asked.append((title, year, kind))
        if self.gate is not None:
            self.gate.wait(_SETTLE)
        return self.body


def _hits(
    shelf: Path, poster: FakePoster, now: object = time.monotonic, correct: object = None
) -> HitPosters:
    return HitPosters(
        poster=poster,
        correct=correct,  # type: ignore[arg-type]
        shelf=PosterShelf(home=lambda: shelf),
        now=now,  # type: ignore[arg-type]
    )


def _row(title: str = "Тачки", year: int = 2006, kind: str = "movie") -> dict[str, JsonValue]:
    return {"pick": 1, "title": title, "year": year, "kind": kind}


def _named(hits: HitPosters, record: dict[str, JsonValue]) -> str:
    offered = hits.offer([record])[0]
    assert isinstance(offered, dict)
    name = offered.get(FIELD)
    assert isinstance(name, str), f"записи не досталось имени картинки: {offered}"
    return name


def _settled(hits: HitPosters, name: str) -> tuple[bytes, str] | None:
    return hits.read(name)


def test_hit_carries_the_name_of_its_poster_and_the_picture_follows(tmp_path: Path) -> None:
    """Имя картинки едет в записи выдачи, а байты приходят по нему следом."""
    poster = FakePoster()
    hits = _hits(tmp_path, poster)
    name = _named(hits, _row())
    assert _settled(hits, name) == (POSTER, "image/jpeg")


def test_the_list_does_not_wait_for_the_picture(tmp_path: Path) -> None:
    """Выдача уходит человеку, пока картинка ещё ищется: круг поиска не удлиняется."""
    gate = threading.Event()
    poster = FakePoster(gate=gate)
    hits = _hits(tmp_path, poster)
    started = time.monotonic()
    name = _named(hits, _row())
    took = time.monotonic() - started
    gate.set()
    assert took < _QUICK, f"выдача ждала картинку {took:.3f} с"
    assert _settled(hits, name) == (POSTER, "image/jpeg")


def test_a_picture_without_a_title_stays_a_line(tmp_path: Path) -> None:
    """Названия нет - имени картинки нет, и строка остаётся строкой без заглушки."""
    hits = _hits(tmp_path, FakePoster())
    offered = hits.offer([{"pick": 1, "title": "  "}])[0]
    assert offered == {"pick": 1, "title": "  "}


def test_the_same_name_in_another_year_is_another_picture(tmp_path: Path) -> None:
    """Тёзка другого года получает СВОЁ имя: постер соседней картины хуже, чем никакого."""
    hits = _hits(tmp_path, FakePoster())
    assert _named(hits, _row("Матрица", 1999)) != _named(hits, _row("Матрица", 2021))


def test_a_poster_already_on_the_shelf_is_taken_without_the_network(tmp_path: Path) -> None:
    """Лежащее на общей полке берётся с неё, и в сеть за этой картиной не ходят вовсе."""
    PosterShelf(home=lambda: tmp_path).write(f"Тачки|2006|movie|{_CHECKED}", KEPT)
    poster = FakePoster()
    hits = _hits(tmp_path, poster)
    name = _named(hits, _row())
    assert _settled(hits, name) == (KEPT, "image/png")
    assert poster.asked == []


def test_a_miss_holds_off_the_next_walk_for_the_same_picture(tmp_path: Path) -> None:
    """Промах откладывает следующий поход: список из десятка не стучит по справке заново."""
    poster = FakePoster(body=None)
    hits = _hits(tmp_path, poster, now=lambda: 0.0)
    name = _named(hits, _row())
    assert _settled(hits, name) is None
    again = hits.offer([_row()])[0]
    assert isinstance(again, dict)
    assert FIELD not in again, f"после промаха записи снова досталось имя: {again}"
    assert poster.asked == [("Тачки", 2006, "movie")]


def test_the_unchecked_picture_of_the_card_does_not_leak_into_the_list(tmp_path: Path) -> None:
    """🔴 Картинку карточки список с полки не берёт: год у неё не сверен.

    Полка у них общая и название, год и род у записи те же, поэтому картинка соседки,
    положенная туда показом «Паразитов» 2004 года, приехала бы в список готовой - минуя
    ту самую сверку, ради которой всё и заведено.
    """
    PosterShelf(home=lambda: tmp_path).write("Тачки|2006|movie", KEPT)
    poster = FakePoster()
    hits = _hits(tmp_path, poster)

    assert _settled(hits, _named(hits, _row())) == (POSTER, "image/jpeg")
    assert poster.asked == [("Тачки", 2006, "movie")]


def test_a_year_the_reference_does_not_confirm_leaves_the_row_a_row(tmp_path: Path) -> None:
    """🔴 Постер соседней картины хуже, чем никакого: год не подтверждён - картинки нет.

    Голое название ведёт в одну статью на всех тёзок, и без сверки «Паразиты» 1999, 2004
    и 2016 годов получили бы один постер на всех - постер «Паразитов» 2019-го.
    """
    poster = FakePoster()
    hits = _hits(tmp_path, poster, now=lambda: 0.0, correct=lambda title, year, kind, timeout: "")

    assert _settled(hits, _named(hits, _row("Паразиты", 1999))) is None
    assert poster.asked == [], "за постером пошли, хотя год не подтверждён"


def test_the_confirmed_name_is_the_one_the_picture_is_looked_for_by(tmp_path: Path) -> None:
    """Подтверждённое справкой имя и есть то, под которым ищется постер."""
    poster = FakePoster()
    hits = _hits(
        tmp_path, poster, correct=lambda title, year, kind, timeout: f"{title} (фильм, {year})"
    )

    assert _settled(hits, _named(hits, _row("Паразиты", 2019))) == (POSTER, "image/jpeg")
    assert poster.asked == [("Паразиты (фильм, 2019)", 2019, "movie")]
