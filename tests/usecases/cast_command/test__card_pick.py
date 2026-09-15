"""Показ с карточки: картина по её ключу и раздача, которую карточка отобрала."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from tests.fakes import composition
from tests.usecases.cast_command.world import plan, plans, release
from tests.usecases.choice.world import film
from tests.usecases.choice.world import plan as shown
from torrcast.domain._series import _Series
from torrcast.domain.args import Args
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.episode import Episode
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._card_pick import _card_number, _card_release_note
from torrcast.usecases.cast_command._choose import _choose
from torrcast.usecases.cast_command.play_stage import _exact_picture
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.start_clock import _Clock

_A = f"magnet:?xt=urn:btih:{'a' * 40}"
_B = f"magnet:?xt=urn:btih:{'b' * 40}"


@pytest.fixture(autouse=True)
def _russian(_russian_product: None) -> None:
    """Предмет модуля - русские строки показа."""


def test_the_card_picture_is_found_by_its_key_whatever_its_number() -> None:
    menu = plans(3)
    asked = Args(query=["тачки"], picture=menu[2].picture.key)

    assert _card_number(menu, asked, _exact_picture) == 3


def test_a_card_picture_gone_from_the_circle_is_a_refusal_not_a_neighbour() -> None:
    """Ключа в круге нет: сыграть соседку под тем же номером - подмена кино без строки."""
    asked = Args(query=["тачки"], picture="movie:тачки-9:2031")

    with pytest.raises(NotFoundError) as refusal:
        _card_number(plans(3), asked, _exact_picture)

    assert str(refusal.value) == phrase("choice.card_picture_gone", asked="тачки")


def _series(
    title: str, year: int, want: Episode, *seasons: tuple[int, ...], original: str | None = None
) -> list[Plan]:
    """Круг сериала: по паку на каждый кортеж сезонов (пустой - без номера), серии 1-13."""
    packs = [
        replace(
            film(f"{title} / E1-13 of 13 [{year}, WEBRip 1080p]", kind="tv"),
            season=got[0] if got else None,
            seasons=got if len(got) > 1 else (),
            episodes=tuple(range(1, 14)),
        )
        for got in seasons
    ]
    menu = shown(title, year, kind="tv", original=original, pool=packs)
    menu.series = _Series(want=want)
    return [shown(title, 2021, pool=[film(f"{title}. Фильм 2021 WEB-DL 1080p")]), menu]


def _mazhor(year: int, episode: int = 8, original: str | None = None) -> list[Plan]:
    """Круг «Мажор s5e8»: все раздачи подписаны годом пятого сезона, а не годом сериала."""
    return _series("Мажор", year, Episode(5, episode), (5,), original=original)


def test_a_series_card_finds_its_picture_under_the_year_of_the_season() -> None:
    """🔴 TC-1267. Вышедшая серия с русской раздачей в пуле не отказывает «картины больше нет»."""
    asked = Args(query=["Мажор", "s5e8"], picture="tv:мажор:2014")

    assert _card_number(_mazhor(2026), asked, _exact_picture) == 2


def test_the_original_of_a_later_season_is_compared_loosely() -> None:
    asked = Args(query=["Мажор", "s5e8"], picture="tv:мажор:2014", picture_original="MAZHOR")

    assert _card_number(_mazhor(2026, original="Mazhor"), asked, _exact_picture) == 2


@pytest.mark.parametrize(
    ("menu", "query", "original"),
    [
        (_mazhor(2026), ["Мажор"], ""),
        (_mazhor(2010), ["Мажор", "s5e8"], ""),
        (_mazhor(2026, 14), ["Мажор", "s5e14"], ""),
        (_mazhor(2026, original="Major"), ["Мажор", "s5e8"], "Mazhor"),
        (_mazhor(2026, original="Mazhor"), ["Мажор", "s5e8"], ""),
    ],
)
def test_without_the_episode_in_a_later_series_the_card_picture_stays_gone(
    menu: list[Plan], query: list[str], original: str
) -> None:
    asked = Args(query=query, picture="tv:мажор:2014", picture_original=original)

    with pytest.raises(NotFoundError):
        _card_number(menu, asked, _exact_picture)


@pytest.mark.parametrize(
    ("want", "seasons"),
    [
        (Episode(1, 1), [(1,)]),
        (Episode(1, 1), [()]),
        (Episode(2, 1), [(1,), (2,)]),
        (Episode(2, 1), [(1, 2)]),
    ],
)
def test_a_later_remake_under_the_same_original_is_a_refusal(
    want: Episode, seasons: list[tuple[int, ...]]
) -> None:
    """«Доктор Кто» 1963 и 2005 делят и имя, и оригинал: ремейк считает сезоны с первого."""
    menu = _series("Доктор Кто", 2005, want, *seasons, original="Doctor Who")
    asked = Args(
        query=["Доктор Кто", str(want)], picture="tv:доктор-кто:1963", picture_original="Doctor Who"
    )

    with pytest.raises(NotFoundError):
        _card_number(menu, asked, _exact_picture)


def test_a_film_card_does_not_go_to_a_later_series_of_its_name() -> None:
    asked = Args(query=["Мажор", "s5e8"], picture="movie:мажор:2014")

    with pytest.raises(NotFoundError):
        _card_number(_mazhor(2026), asked, _exact_picture)


def test_a_series_card_does_not_go_to_a_later_film_of_its_name() -> None:
    menu = _mazhor(2026)
    menu[1].picture.kind = "movie"

    with pytest.raises(NotFoundError):
        _card_number(menu, Args(query=["Мажор", "s5e8"], picture="tv:мажор:2014"), _exact_picture)


def test_the_card_release_that_played_says_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    asked = Args(query=["кино"], card_release="a" * 40, voice=2)

    _card_release_note(asked, plan(), _Prep(number=1, release=replace(release(), magnet=_A)))

    assert capsys.readouterr().out == ""
    assert asked.voice == 2


def test_a_replaced_card_release_is_said_and_its_track_number_dropped(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Номер дорожки относится к раздаче карточки: у другой под ним может быть иной язык."""
    asked = Args(query=["кино"], card_release="a" * 40, voice=2)

    _card_release_note(asked, plan(), _Prep(number=1, release=replace(release(), magnet=_B)))

    said = capsys.readouterr().out
    assert phrase("choice.card_release_replaced", title="Кино") in said
    assert phrase("choice.card_voice_dropped", voice=2) in said
    assert asked.voice is None


def test_a_named_voice_survives_a_replaced_release(capsys: pytest.CaptureFixture[str]) -> None:
    """Имя студии или языка годится любой раздаче - снимать нечего."""
    asked = Args(query=["кино"], card_release="a" * 40, voice="eng")

    _card_release_note(asked, plan(), _Prep(number=1, release=replace(release(), magnet=_B)))

    assert asked.voice == "eng"


def test_the_show_takes_the_card_picture_by_key_and_skips_the_old_table() -> None:
    """Номер картины выводится из ключа в ЭТОМ круге и доходит до выбора как карточный."""
    menu = plans(3)
    heard: dict[str, object] = {}

    def pick(*_rest: object, **named: object) -> Any:
        heard.update(named)
        return menu[named["pick"] - 1]  # type: ignore[operator]

    picked = _choose(
        Config(),
        cast(Any, Args(query=["тачки"], picture=menu[1].picture.key)),
        Choice(profile=CAUTIOUS, how="стенд"),
        WatchState(),
        None,
        _Clock(),
        circle=lambda *args, **rest: menu,
        stand=lambda *args, **rest: cast(Any, _NoBench()),
        passport_of=lambda plans: cast(Any, _NoPassport()),
        pick=pick,
        bookmark=lambda *args, **rest: EXIT_OK,
    )

    assert picked == EXIT_OK
    assert heard["pick"] == 2
    assert heard["card"] is True


class _NoBench:
    def start(self, plan: object, number: int) -> None:
        return None

    def spare(self, plan: object, args: object) -> None:
        return None

    def drop_all(self) -> None:
        return None


class _NoPassport:
    def get(self) -> Any:
        from torrcast.domain.facts.origin import Origin

        return Origin()


def test_a_show_from_the_card_asks_the_facts_of_its_own_picture_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Меню показа с карточки никто не читает: справка по всему кругу только держала старт.

    Живой замер: на круге из трёх десятков картин показ стоял 1.5 с в ожидании справки
    и ещё 1.4 с в дописи её кэша, хотя картина карточки лежала в кэше целиком.
    """
    asked: list[list[object]] = []

    class _Facts:
        def __init__(self, wanted: list[object]) -> None:
            asked.append(list(wanted))

        def start(self) -> None:
            return None

        def wait(self) -> None:
            return None

        def finish(self) -> None:
            return None

        def ready(self, *_rest: object) -> Any:
            from torrcast.domain.facts.fact import Fact

            return Fact()

        get = ready

    composition.use_facts(monkeypatch, _Facts)
    menu = plans(3)
    card = menu[1].picture

    picked = _choose(
        Config(),
        cast(Any, Args(query=["тачки"], picture=card.key)),
        Choice(profile=CAUTIOUS, how="стенд"),
        WatchState(),
        None,
        _Clock(),
        circle=lambda *args, **rest: menu,
        stand=lambda *args, **rest: cast(Any, _NoBench()),
        passport_of=lambda plans: cast(Any, _NoPassport()),
        pick=lambda *args, **rest: menu[1],
        bookmark=lambda *args, **rest: EXIT_OK,
    )

    assert picked == EXIT_OK
    assert asked == [[(card.title, card.year, card.kind)]]
