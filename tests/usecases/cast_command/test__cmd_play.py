"""Зеркало счастливого пути: ранние выходы отвечают показом, а не проваливаются в поиск."""

from __future__ import annotations

import pytest

from tests.fakes import composition
from tests.usecases.cast_command.world import entry
from torrcast.domain.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store.slot import store as watch_store
from torrcast.usecases.cast_command._cmd_play import _cmd_play


@pytest.fixture(autouse=True)
def _outside(monkeypatch: pytest.MonkeyPatch) -> None:
    """Паспорт приёмника на стенде спрашивать не у кого: профиль называется прямо.

    Настройки, уборка сирот и строка о занятом телевизоре тут настоящие: файл настроек
    свой у каждого теста, сирот в пустом состоянии нет, а занятого показа нет тем более.
    """
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))


def _remember(saved: object) -> None:
    state = WatchState()
    state.put("кино", saved)  # type: ignore[arg-type]
    watch_store().save(state)


def _never(*_args: object, **_rest: object) -> int:
    return pytest.fail("до поиска доходить нечему")


def test_a_saved_movie_is_continued_without_a_single_question() -> None:
    """Начатый фильм продолжается молча: до поиска этот путь не доходит вовсе."""
    _remember(entry(query="кино"))

    code = _cmd_play(Args(query=["кино"]), resume=lambda *args, **rest: EXIT_OK, choose=_never)

    assert code == EXIT_OK


def test_a_watched_movie_is_started_over_and_says_so() -> None:
    """Досмотренный фильм играется с начала - и это тоже ранний выход, а не поиск."""
    _remember(entry(query="кино", pos=7100.0))

    code = _cmd_play(Args(query=["кино"]), restart=lambda *args, **rest: EXIT_OK, choose=_never)

    assert code == EXIT_OK


def test_an_asked_menu_outranks_the_bookmark_and_says_nothing_about_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--menu`` - запрос «дай выбрать»: закладка на него не отвечает и не считает."""
    _remember(entry(query="кино", pos=7100.0))

    code = _cmd_play(
        Args(query=["кино"], menu=True),
        restart=_never,
        resume=_never,
        choose=lambda *args, **rest: EXIT_OK,
    )

    assert code == EXIT_OK
    assert "досмотрено" not in capsys.readouterr().out


def test_a_hand_named_menu_item_outranks_the_bookmark() -> None:
    """``--pick N`` называет картину номером - съесть этот номер закладке нечем."""
    _remember(entry(query="кино"))

    code = _cmd_play(
        Args(query=["кино"], pick=3),
        restart=_never,
        resume=_never,
        choose=lambda *args, **rest: EXIT_OK,
    )

    assert code == EXIT_OK


def test_the_code_of_the_bookmark_of_the_chosen_picture_reaches_the_caller() -> None:
    """Закладка выбранной картины отвечает показом - и её код уезжает наружу целым."""
    assert _cmd_play(Args(query=["кино"]), choose=lambda *args, **rest: EXIT_OK) == EXIT_OK
