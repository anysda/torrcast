"""ShelfPlayable: трёхсоставный приговор плитки, с памятью на процесс и на диск."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from torrcast.domain.config import Config
from torrcast.domain.infra_error import InfraError
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.built_by_rule import RULE
from web.shelf_playable import ShelfPlayable
from web.verdict_disk import VerdictDisk

_RELEASE = Release(raw_name="Film 2010 BDRip 1080p LostFilm", title="Film", magnet="magnet:f")
_PICTURE = Picture(title="Film", year=2010, kind="movie", releases=[_RELEASE])
_PLAN = Plan(picture=_PICTURE, ranked=[_RELEASE], runtime=0, warn_mbit=0)
_UNRANKED_PLAN = Plan(picture=_PICTURE, ranked=[], runtime=0, warn_mbit=0)
_CONFIG = Config(torrserver_url="http://ts", receiver_profile="q70d")


def _alive(_config: Config) -> bool:
    """Подделка стенда: жив - тестам самого TorrServer не нужно."""
    return True


def _dead(_config: Config) -> bool:
    """Подделка стенда: лёг - дальше отбор идти не должен."""
    return False


@dataclass
class _Voices:
    """Подмена отбора дорожек: отвечает названным приговором и считает свои вызовы."""

    heard: Any
    pending: bool = False
    calls: list[str] = field(default_factory=list)

    def __call__(self, plan: Plan, query: str, config: Config) -> tuple[Any, bool]:
        self.calls.append(query)
        return self.heard, self.pending


def _circle(plans: list[Plan]) -> Any:
    return lambda _query: plans


def test_a_found_release_makes_the_tile_playable() -> None:
    playable = ShelfPlayable(circle=_circle([_PLAN]), voices=_Voices(heard=object()), alive=_alive)

    assert playable.of("film", _PICTURE.key, _CONFIG) is True


def test_no_heard_release_makes_the_tile_not_playable() -> None:
    playable = ShelfPlayable(circle=_circle([_PLAN]), voices=_Voices(heard=None), alive=_alive)

    assert playable.of("film", _PICTURE.key, _CONFIG) is False


def test_an_unranked_plan_is_not_playable_and_never_asks_voices() -> None:
    """``not plan.ranked`` - честный факт «раздач нет», а не «не знаю» (докстрока модуля)."""
    voices = _Voices(heard=object())
    playable = ShelfPlayable(circle=_circle([_UNRANKED_PLAN]), voices=voices, alive=_alive)

    assert playable.of("film", _PICTURE.key, _CONFIG) is False
    assert voices.calls == []


def test_pending_voices_read_as_unknown_not_as_not_playable() -> None:
    """Отбор дорожек ещё не дочитал раздачу - «не знаю», плитка остаётся на полке."""
    playable = ShelfPlayable(
        circle=_circle([_PLAN]), voices=_Voices(heard=None, pending=True), alive=_alive
    )

    assert playable.of("film", _PICTURE.key, _CONFIG) is None


def test_a_key_missing_from_the_circle_is_unknown_not_not_playable() -> None:
    """Круг мог не дойти именно до этой картины - это «не знаю», не приговор."""
    voices = _Voices(heard=object())
    playable = ShelfPlayable(circle=_circle([]), voices=voices, alive=_alive)

    assert playable.of("film", _PICTURE.key, _CONFIG) is None
    assert voices.calls == []


def test_a_silent_circle_is_unknown() -> None:
    def _failing(_query: str) -> list[Plan]:
        raise InfraError("прибили")

    playable = ShelfPlayable(circle=_failing, voices=_Voices(heard=object()), alive=_alive)

    assert playable.of("film", _PICTURE.key, _CONFIG) is None


def test_a_dead_torrserver_is_unknown_and_never_asks_the_circle() -> None:
    """Стенд проверяется ДЕШЕВО и ДО круга - поломка стенда не читается как приговор картине."""
    calls: list[str] = []

    def _circle_counting(query: str) -> list[Plan]:
        calls.append(query)
        return [_PLAN]

    voices = _Voices(heard=object())
    playable = ShelfPlayable(circle=_circle_counting, voices=voices, alive=_dead)

    assert playable.of("film", _PICTURE.key, _CONFIG) is None
    assert calls == []
    assert voices.calls == []


def test_a_verdict_of_the_current_rule_is_not_asked_twice() -> None:
    voices = _Voices(heard=object())
    playable = ShelfPlayable(circle=_circle([_PLAN]), voices=voices, alive=_alive)

    first = playable.of("film", _PICTURE.key, _CONFIG)
    second = playable.of("film", _PICTURE.key, _CONFIG)

    assert first is True and second is True
    assert voices.calls == ["film"], "готовый вердикт того же правила не перепрашивается"


def test_an_unknown_verdict_is_never_memoized_in_the_process() -> None:
    """«Не знаю» не запоминается - следующий заход спрашивает круг снова, а не читает память."""
    voices = _Voices(heard=object())
    playable = ShelfPlayable(circle=_circle([]), voices=voices, alive=_alive)

    playable.of("film", _PICTURE.key, _CONFIG)
    playable.of("film", _PICTURE.key, _CONFIG)

    assert playable._verdicts == {}


def test_a_rule_change_forgets_the_old_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    voices = _Voices(heard=None)
    playable = ShelfPlayable(circle=_circle([_PLAN]), voices=voices, alive=_alive)
    playable.of("film", _PICTURE.key, _CONFIG)

    monkeypatch.setattr("web.shelf_playable.RULE", 99)
    voices.heard = object()
    second = playable.of("film", _PICTURE.key, _CONFIG)

    assert second is True, "новое правило обязано спросить отбор заново"
    assert voices.calls == ["film", "film"]


def test_a_verdict_survives_a_restart_via_the_disk(tmp_path: Path) -> None:
    """Свежий предмет, указанный на тот же файл - это и есть рестарт службы (TC-1343)."""
    disk = VerdictDisk(path=lambda: tmp_path / "shelf_verdicts.json")
    first = ShelfPlayable(
        circle=_circle([_PLAN]), voices=_Voices(heard=object()), alive=_alive, disk=disk
    )
    assert first.of("film", _PICTURE.key, _CONFIG) is True

    second_voices = _Voices(heard=object())
    restarted = ShelfPlayable(
        circle=_circle([_PLAN]), voices=second_voices, alive=_alive, disk=disk
    )

    assert restarted.of("film", _PICTURE.key, _CONFIG) is True
    assert second_voices.calls == [], "готовый вердикт с диска не платит TorrServer заново"


def test_an_unknown_verdict_is_never_written_to_disk(tmp_path: Path) -> None:
    disk = VerdictDisk(path=lambda: tmp_path / "shelf_verdicts.json")
    playable = ShelfPlayable(
        circle=_circle([]), voices=_Voices(heard=object()), alive=_alive, disk=disk
    )

    playable.of("film", _PICTURE.key, _CONFIG)

    assert disk.get(_PICTURE.key, RULE) is None


def test_a_negative_verdict_stays_in_the_process_but_is_reasked_after_a_restart(
    tmp_path: Path,
) -> None:
    """TC-1343: ``False`` на живой сети шумный - диск бы закрепил один шум навсегда."""
    disk = VerdictDisk(path=lambda: tmp_path / "shelf_verdicts.json")
    voices = _Voices(heard=None)
    playable = ShelfPlayable(circle=_circle([_PLAN]), voices=voices, alive=_alive, disk=disk)

    assert playable.of("film", _PICTURE.key, _CONFIG) is False
    assert playable.of("film", _PICTURE.key, _CONFIG) is False
    assert voices.calls == ["film"], "процесс сам не перепрашивает свой же приговор"
    assert disk.get(_PICTURE.key, RULE) is None, "отрицательный приговор не идёт на диск"

    restarted_voices = _Voices(heard=object())
    restarted = ShelfPlayable(
        circle=_circle([_PLAN]), voices=restarted_voices, alive=_alive, disk=disk
    )
    assert restarted.of("film", _PICTURE.key, _CONFIG) is True
    assert restarted_voices.calls == ["film"], "рестарт обязан спросить шумный приговор заново"
