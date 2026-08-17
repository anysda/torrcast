"""Цепочка серий: одна вперёд, не раньше времени и с повтором на обрыв связи."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.warm.world import lay, vault, warmer, world
from torrcast.usecases.warm.chain import _ask_follow, _chain, _nap
from torrcast.usecases.warm.warmer import Warmer

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _whole(root: Path, **kwargs: object) -> Warmer:
    """Прогрев, у которого весь фильм уже на диске: работы не осталось."""
    warm = warmer(root, **kwargs)
    for slot in range(warm.grid.count):
        lay(warm.vault, slot)
    return warm


def test_an_unfinished_episode_holds_the_chain_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пока текущая серия не на диске, каждый байт раздачи нужен ей, а не следующей."""
    world(monkeypatch)
    warm = warmer(tmp_path)
    warm.follow = lambda: warmer(tmp_path, vault=vault(tmp_path, key="следующая"))

    _chain(warm)

    assert warm.after is None, "цепочка тронулась, не доложив текущую серию"


def test_a_finished_episode_starts_the_next_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Серия легла целиком - следующая берётся в работу и защищается от бюджета."""
    fake = world(monkeypatch)
    warm = _whole(tmp_path)
    following = warmer(tmp_path, vault=vault(tmp_path, key="следующая"))
    warm.follow = lambda: following

    _chain(warm)

    assert warm.after is following, "следующая серия не взялась в работу"
    assert following.thread is not None, "следующую серию взяли, а нитку не подняли"
    assert warm.vault.key in following.vault.keep, "бюджет выел бы текущую серию первой"
    assert "прогрев следующей серии" in [name for name, _facts in fake.marks]
    following.stop()


def test_the_chain_hands_over_the_reserve_and_the_rival(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Соседу достаются и запас показа, и кодировщик: процессор и раздача у них общие."""
    world(monkeypatch)
    warm = _whole(tmp_path)
    following = warmer(tmp_path, vault=vault(tmp_path, key="следующая"))
    warm.slack, warm.rival = 42.0, object()
    warm.follow = lambda: following

    _chain(warm)

    assert following.slack == 42.0 and following.rival is warm.rival
    following.stop()


def test_a_chain_never_goes_two_episodes_ahead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ровно за одну серию: сезон-пак впрок - уже не страховка показа."""
    world(monkeypatch)
    warm = _whole(tmp_path)
    asked = 0

    def _follow() -> Warmer:
        nonlocal asked
        asked += 1
        return warmer(tmp_path, vault=vault(tmp_path, key=f"следующая{asked}"))

    warm.follow = _follow
    _chain(warm)
    _chain(warm)

    assert asked == 1, "цепочка ушла на две серии вперёд"
    warm.stop()


def test_there_is_nothing_to_chain_without_a_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """У фильма продолжения нет и быть не может - цепочка молчит."""
    world(monkeypatch)
    warm = _whole(tmp_path)

    _chain(warm)

    assert warm.after is None


def test_a_broken_network_is_waited_out_and_asked_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Спрашиваем повторно, пока показ жив: один вопрос стоил целой следующей серии."""
    world(monkeypatch)
    said: list[str] = []
    warm = warmer(tmp_path, log=said.append)
    warm.chain_retry = 0.0
    following = warmer(tmp_path, vault=vault(tmp_path, key="следующая"))
    tries = 0

    def _follow() -> Warmer:
        nonlocal tries
        tries += 1
        if tries < 3:
            raise OSError("сети нет")
        return following

    warm.follow = _follow

    assert _ask_follow(warm) is following
    assert tries == 3, "прогрев сдался после первого же обрыва"
    assert len(said) == 1, "жалоба повторяется на каждом круге и забивает журнал показа"


def test_nothing_to_follow_is_answered_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``None`` - это «нечего», а не «не смогли»: ждать тут нечего никогда."""
    world(monkeypatch)
    warm = warmer(tmp_path)
    warm.follow = lambda: None

    assert _ask_follow(warm) is None


def test_a_stopped_show_ends_the_nap_and_the_asking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Показ кончился - прогреву спать и спрашивать незачем."""
    fake = world(monkeypatch)
    warm = warmer(tmp_path)
    warm.stopped = True

    _nap(warm, 30.0)
    assert fake.slept == [], "снятый прогрев всё равно уснул"
    assert _ask_follow(warm) is None


def test_the_nap_wakes_up_in_small_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Сон меряется десятками секунд, а снятие показа обязано срабатывать сразу."""
    fake = world(monkeypatch)
    warm = warmer(tmp_path)

    _nap(warm, 2.0)

    assert fake.slept == [0.5, 0.5, 0.5, 0.5], "прогрев уснул одним куском"
