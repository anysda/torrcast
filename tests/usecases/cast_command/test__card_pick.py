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


def _mazhor(year: int, episode: int = 8) -> list[Plan]:
    """Круг «Мажор s5e8»: все раздачи подписаны годом пятого сезона, а не годом сериала."""
    pack = replace(film("Мажор / S5E1-8 of 8 [2026, WEBRip 1080p]", kind="tv"), season=5)
    menu = shown("Мажор", year, kind="tv", pool=[replace(pack, episodes=tuple(range(1, 9)))])
    menu.series = _Series(want=Episode(5, episode))
    return [shown("Мажор", 2021, pool=[film("Мажор. Фильм 2021 WEB-DL 1080p")]), menu]


def test_a_series_card_finds_its_picture_under_the_year_of_the_season() -> None:
    """🔴 TC-1267. Вышедшая серия с русской раздачей в пуле не отказывает «картины больше нет»."""
    asked = Args(query=["Мажор", "s5e8"], picture="tv:мажор:2014")

    assert _card_number(_mazhor(2026), asked, _exact_picture) == 2


@pytest.mark.parametrize(
    ("menu", "query"),
    [
        (_mazhor(2026), ["Мажор"]),
        (_mazhor(2010), ["Мажор", "s5e8"]),
        (_mazhor(2026, 9), ["Мажор", "s5e9"]),
    ],
)
def test_without_the_episode_in_a_later_series_the_card_picture_stays_gone(
    menu: list[Plan], query: list[str]
) -> None:
    with pytest.raises(NotFoundError):
        _card_number(menu, Args(query=query, picture="tv:мажор:2014"), _exact_picture)


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
