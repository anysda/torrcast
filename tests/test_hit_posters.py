"""Зеркало :mod:`hass.hit_posters`: имя картинки - только тем, у кого картинка будет."""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from hass.hit_posters import FIELD, HitPosters
from hass.poster_lookup import _poster_identity
from hass.poster_shelf import PosterShelf
from torrcast.domain.facts.ask import Ask
from torrcast.domain.json_value import JsonValue
from torrcast.domain.playback_snapshot import PlaybackSnapshot

POSTER = b"\xff\xd8\xff\xe0poster"
KEPT = b"\x89PNG\r\n\x1a\nkept"

#: Сколько ждём фоновый поход в пробе, секунды. Он весь на подделках и стоит миллисекунды;
#: потолок - против зависшей пробы, а не против медленной сети.
_SETTLE = 5.0
#: За сколько обязана вернуться выдача, пока картинка ещё качается, секунды. Ждать байты
#: тут значило бы сложить время поиска со временем загрузки десятка картинок.
_QUICK = 0.5


@dataclass
class FakeSource:
    """Двойник похода за постером: приговор по списку статей, байты - по приговору."""

    #: Кому есть что показывать: название картины → её статьи. Нет в карте - статей нет.
    pages: dict[str, list[str]] = field(default_factory=lambda: {"Тачки": ["Cars"]})
    body: bytes | None = POSTER
    gate: threading.Event | None = None
    judged: list[Ask] = field(default_factory=list)
    loaded: list[Ask] = field(default_factory=list)

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        self.judged.extend(asks)
        return {ask: list(self.pages.get(ask.title, ())) for ask in asks}

    def bodies(self, wanted: dict[Ask, list[str]], timeout: float) -> dict[Ask, bytes]:
        self.loaded.extend(wanted)
        if self.gate is not None:
            self.gate.wait(_SETTLE)
        if self.body is None:
            return {}
        return {ask: self.body for ask, pages in wanted.items() if pages}


def _hits(shelf: Path, source: FakeSource, now: object = time.monotonic) -> HitPosters:
    return HitPosters(
        source=source,
        shelf=PosterShelf(home=lambda: shelf),
        now=now,  # type: ignore[arg-type]
    )


def _row(title: str = "Тачки", year: int = 2006, kind: str = "movie") -> dict[str, JsonValue]:
    return {"pick": 1, "title": title, "year": year, "kind": kind}


def _card_name(title: str, year: int) -> str:
    """Имя картины ГЛАЗАМИ КАРТОЧКИ играющего: полка у карточки и у списка одна.

    Берётся оно у самой карточки (:func:`hass.poster_lookup._poster_identity`), а не собирается тут
    заново: сойдись оно только со списком, проба сторожила бы копию правила, а не общую
    полку, и разъезд двух картинок про одну картину остался бы незамеченным.
    """
    return _poster_identity(
        PlaybackSnapshot(key="k", title=title, year=year, label="", original="", query="")
    )


def _named(hits: HitPosters, record: dict[str, JsonValue]) -> str:
    offered = hits.offer([record])[0]
    assert isinstance(offered, dict)
    name = offered.get(FIELD)
    assert isinstance(name, str), f"записи не досталось имени картинки: {offered}"
    return name


def test_hit_carries_the_name_of_its_poster_and_the_picture_follows(tmp_path: Path) -> None:
    """Имя картинки едет в записи выдачи, а байты приходят по нему следом."""
    hits = _hits(tmp_path, FakeSource())
    name = _named(hits, _row())
    assert hits.read(name) == (POSTER, "image/jpeg")


def test_the_list_does_not_wait_for_the_bytes_of_the_pictures(tmp_path: Path) -> None:
    """Выдача уходит человеку, пока картинки ещё качаются: круг поиска не удлиняется."""
    gate = threading.Event()
    source = FakeSource(gate=gate)
    hits = _hits(tmp_path, source)
    started = time.monotonic()
    name = _named(hits, _row())
    took = time.monotonic() - started
    gate.set()
    assert took < _QUICK, f"выдача ждала байты картинки {took:.3f} с"
    assert hits.read(name) == (POSTER, "image/jpeg")


def test_a_picture_without_a_title_stays_a_line(tmp_path: Path) -> None:
    """Названия нет - имени картинки нет, и строка остаётся строкой без заглушки."""
    hits = _hits(tmp_path, FakeSource())
    offered = hits.offer([{"pick": 1, "title": "  "}])[0]
    assert offered == {"pick": 1, "title": "  "}


def test_a_hit_without_an_article_gets_no_name_at_all(tmp_path: Path) -> None:
    """🔴 Статьи у картины нет - поля нет, и человек видит строку, а не рамку с пустотой.

    Раньше имя уносила КАЖДАЯ находка, и маршрут за картинкой отвечал по нему «нет
    такой»: половина списка стояла битыми плитками (TC-1023).
    """
    source = FakeSource(pages={"Тачки": ["Cars"]})
    hits = _hits(tmp_path, source, now=lambda: 0.0)
    offered = hits.offer([_row(), _row("Секс-файлы: Секс-матрица", 2000)])
    assert isinstance(offered[0], dict) and isinstance(offered[1], dict)
    assert FIELD in offered[0], "у находки со статьёй имени картинки не оказалось"
    assert FIELD not in offered[1], f"безнадёжной находке досталось имя картинки: {offered[1]}"


def test_every_name_given_out_serves_its_bytes(tmp_path: Path) -> None:
    """🔴 Выданное имя обязано отдавать байты: битых плиток в списке ноль."""
    source = FakeSource(pages={"Тачки": ["Cars"], "Матрица": ["The Matrix"]})
    hits = _hits(tmp_path, source, now=lambda: 0.0)
    rows: list[JsonValue] = [_row(), _row("Матрица", 1999), _row("Секс-файлы: Секс-матрица", 2000)]
    named = [row.get(FIELD) for row in hits.offer(rows) if isinstance(row, dict)]
    given = [name for name in named if isinstance(name, str)]
    assert len(given) == 2, f"имена достались не тем: {named}"
    assert all(hits.read(name) is not None for name in given), "выданное имя не отдало байты"


def test_the_same_name_in_another_year_is_another_picture(tmp_path: Path) -> None:
    """Тёзка другого года получает СВОЁ имя: постер соседней картины хуже, чем никакого."""
    source = FakeSource(pages={"Матрица": ["The Matrix"]})
    hits = _hits(tmp_path, source)
    assert _named(hits, _row("Матрица", 1999)) != _named(hits, _row("Матрица", 2021))


def test_a_poster_already_on_the_shelf_is_taken_without_the_network(tmp_path: Path) -> None:
    """Лежащее на общей полке берётся с неё, и в сеть за этой картиной не ходят вовсе."""
    PosterShelf(home=lambda: tmp_path).write(_card_name("Тачки", 2006), KEPT)
    source = FakeSource()
    hits = _hits(tmp_path, source)
    name = _named(hits, _row())
    assert hits.read(name) == (KEPT, "image/png")
    assert source.judged == [], "за приговором пошли, хотя картинка лежит на полке"


def test_the_shelf_of_the_card_is_the_shelf_of_the_list(tmp_path: Path) -> None:
    """🔴 Картинка карточки достаётся списку с полки: правило сверки года у них одно.

    Раньше строка списка несла хвост «год сверен», и та же самая картинка искалась в
    сети второй раз. Хвост снят вместе с причиной: год сверяет сам поход за постером.
    """
    PosterShelf(home=lambda: tmp_path).write(_card_name("Тачки", 2006), KEPT)
    hits = _hits(tmp_path, FakeSource())
    assert hits.read(_named(hits, _row())) == (KEPT, "image/png")


def test_a_miss_holds_off_the_next_walk_for_the_same_picture(tmp_path: Path) -> None:
    """Промах откладывает следующий поход: список из десятка не стучит по справке заново."""
    source = FakeSource(pages={})
    hits = _hits(tmp_path, source, now=lambda: 0.0)
    first = hits.offer([_row()])[0]
    assert isinstance(first, dict) and FIELD not in first
    again = hits.offer([_row()])[0]
    assert isinstance(again, dict)
    assert FIELD not in again, f"после промаха записи досталось имя: {again}"
    assert len(source.judged) == 1, f"за приговором сходили снова: {source.judged}"


def test_the_original_name_rides_along_to_the_walk(tmp_path: Path) -> None:
    """Оригинальное имя доезжает до похода: у части картин русской статьи нет вовсе."""
    source = FakeSource()
    hits = _hits(tmp_path, source)
    hits.offer([{**_row("Армитаж: Двойная матрица", 2002), "original": "Armitage: Dual-Matrix"}])
    asked = Ask("Армитаж: Двойная матрица", 2002, "movie", "Armitage: Dual-Matrix")
    assert source.judged == [asked]
