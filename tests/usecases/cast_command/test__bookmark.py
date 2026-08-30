"""Зеркало закладки: продолжить, начать сначала, списать досмотренное - и сказать об этом."""

from __future__ import annotations

from typing import Any, cast

import pytest

from tests.usecases.cast_command.world import entry, plan
from torrcast.domain.args import Args
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._bookmark import (
    _continue_picked,
    _kept_place,
    _plays_recorded,
)
from torrcast.usecases.start_clock import _Clock


@pytest.fixture(autouse=True)
def _russian_bookmark(_russian_product: None) -> None:
    """Предмет всего модуля - закладка показа, писанная по-русски до языкового яруса."""


class Bench:
    """Стенд отбора под наблюдением зеркала: важно, убрал ли он прогретое."""

    def __init__(self) -> None:
        self.dropped = 0

    def drop_all(self) -> None:
        self.dropped += 1


def _state_with(saved: object | None) -> WatchState:
    state = WatchState()
    if saved is not None:
        state.put(plan().picture.key, saved)  # type: ignore[arg-type]
    return state


def test_a_picture_without_a_bookmark_goes_the_usual_way() -> None:
    """Записи нет - продолжать нечего, и путь остаётся обычным."""
    code = _continue_picked(
        Config(),
        _state_with(None),
        cast(Any, plan()),
        Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино"]),
        clock=_Clock(),
    )

    assert code is None


def test_a_hand_named_release_says_out_loud_that_it_drops_the_bookmark(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--release N`` значит «другая раздача», а не «забудь, где я остановился»."""
    bench = Bench()

    code = _continue_picked(
        Config(),
        _state_with(entry()),
        cast(Any, plan()),
        bench,  # type: ignore[arg-type]
        args=Args(query=["кино"], release=2),
        clock=_Clock(),
    )

    assert code is None, "названный руками релиз играется обычным путём"
    said = phrase("bookmark.release_named_resume", title="Кино", pos="1:00:00")
    assert said in capsys.readouterr().out
    assert bench.dropped == 0, "прогретое тут ещё пригодится: показ пойдёт обычным путём"


def test_a_series_is_left_to_the_usual_way() -> None:
    """Сериал сюда не заходит: его продолжение ведёт своя ветка."""
    code = _continue_picked(
        Config(),
        _state_with(entry(kind="tv", season=1, episode=2, episodes=[(1, 1), (1, 2)])),
        cast(Any, plan()),
        Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино"]),
        clock=_Clock(),
    )

    assert code is None


def test_a_menu_picked_started_series_says_it_drops_the_saved_place(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Из меню взяли тот же начатый сериал: показ с нуля снесёт сохранённое место.

    Причиной названа та дверь, которой вошли: релиз тут руками не называли. Хвост о потере
    общий с ``--release N`` - потеря одна, а молчать значило бы снести место без строки.
    """
    saved = entry(kind="tv", season=1, episode=2, episodes=[(1, 1), (1, 2)])

    code = _continue_picked(
        Config(),
        _state_with(saved),
        cast(Any, plan()),
        Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино"], menu=True),
        clock=_Clock(),
    )

    assert code is None, "сериал уходит обычным путём - показ с нуля"
    said = phrase("bookmark.picked_in_menu", title="Кино", pos="1:00:00")
    assert said in capsys.readouterr().out


def test_a_flag_picked_started_series_says_it_drops_the_saved_place(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--pick N`` - та же дверь меню: та же строка о потере места обязана быть и там."""
    saved = entry(kind="tv", season=1, episode=2, episodes=[(1, 1), (1, 2)])

    code = _continue_picked(
        Config(),
        _state_with(saved),
        cast(Any, plan()),
        Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино"], pick=2),
        clock=_Clock(),
    )

    assert code is None
    said = phrase("bookmark.picked_in_menu", title="Кино", pos="1:00:00")
    assert said in capsys.readouterr().out


def test_a_menu_picked_picture_without_a_bookmark_stays_silent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Из меню взяли ДРУГУЮ картину: записи о ней нет, терять нечего - и строки нет."""
    code = _continue_picked(
        Config(),
        _state_with(None),
        cast(Any, plan()),
        Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино"], menu=True),
        clock=_Clock(),
    )

    assert code is None
    assert capsys.readouterr().out == ""


def test_a_menu_picked_series_without_progress_stays_silent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Места у записи нет - терять нечего, и строка молчит, как у ``--release N``."""
    saved = entry(kind="tv", season=1, episode=2, episodes=[(1, 1), (1, 2)], pos=0.0)

    code = _continue_picked(
        Config(),
        _state_with(saved),
        cast(Any, plan()),
        Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино"], menu=True),
        clock=_Clock(),
    )

    assert code is None
    assert capsys.readouterr().out == ""


def test_a_started_series_without_the_menu_door_stays_silent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Без ручек меню закладка сериала молчит: его продолжение ведёт своя ветка."""
    saved = entry(kind="tv", season=1, episode=2, episodes=[(1, 1), (1, 2)])

    code = _continue_picked(
        Config(),
        _state_with(saved),
        cast(Any, plan()),
        Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино"]),
        clock=_Clock(),
    )

    assert code is None
    assert capsys.readouterr().out == ""


def test_a_picture_without_a_bookmark_keeps_its_warm_under_the_menu() -> None:
    """Записи нет - прогреву этой картины сноситься нечем."""
    assert _plays_recorded(_state_with(None), plan().picture.key, Args(query=["кино"])) is False


def test_a_resumable_bookmark_answers_with_the_recorded_release() -> None:
    """Начатый и недосмотренный фильм продолжится записанной раздачей: прогрев снесётся."""
    assert _plays_recorded(_state_with(entry()), plan().picture.key, Args(query=["кино"])) is True


def test_a_series_bookmark_does_not_answer_for_the_warm() -> None:
    """Сериал продолжает своя ветка, а не закладка выбранной картины: прогрев живёт."""
    saved = entry(kind="tv", season=1, episode=2, episodes=[(1, 1), (1, 2)])

    assert _plays_recorded(_state_with(saved), plan().picture.key, Args(query=["кино"])) is False


def test_a_finished_bookmark_does_not_answer_for_the_warm() -> None:
    """Продолжать нечего - и сносить прогретое закладка не будет."""
    assert (
        _plays_recorded(_state_with(entry(done=True)), plan().picture.key, Args(query=["кино"]))
        is False
    )


def test_a_named_episode_keeps_the_warm_of_the_film() -> None:
    """Серию у записи фильма не спросить: картину выберет обычный путь - прогрев нужен."""
    assert (
        _plays_recorded(_state_with(entry()), plan().picture.key, Args(query=["кино", "s1e1"]))
        is False
    )


def test_a_hand_named_release_keeps_the_warm() -> None:
    """``--release N`` играет выбранное руками: прогретое ещё пригодится."""
    assert (
        _plays_recorded(_state_with(entry()), plan().picture.key, Args(query=["кино"], release=2))
        is False
    )


def test_from_start_answers_with_the_recorded_release_from_zero() -> None:
    """``--new`` играет записанную раздачу с нуля - и тоже сносит прогретое."""
    assert (
        _plays_recorded(
            _state_with(entry()), plan().picture.key, Args(query=["кино"], from_start=True)
        )
        is True
    )


def test_from_start_with_a_hand_named_release_keeps_the_warm() -> None:
    """``--new`` вместе с названным руками релизом играет выбранное: прогрев живёт."""
    assert (
        _plays_recorded(
            _state_with(entry()),
            plan().picture.key,
            Args(query=["кино"], release=2, from_start=True),
        )
        is False
    )


def test_a_hand_named_release_keeps_the_place_of_a_started_series() -> None:
    """``--release N`` у начатого сериала: серия закладки встаёт в запрос как своя."""
    saved = entry(kind="tv", season=5, episode=1, pos=265.0, episodes=[(5, 1), (5, 2)])

    kept = _kept_place(_state_with(saved), ("кино", saved), Args(query=["кино"], release=2))

    assert kept is not None
    _, args, place = kept
    assert str(args.episode) == "s5e1", "искать и подписывать надо серию закладки, не s1e1"
    assert place.pos == 265.0, "позиция едет в показ выбранной раздачи дальше"


def test_a_watched_series_bookmark_moves_to_the_next_episode_under_a_hand_named_release(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Досмотренная серия под ``--release N`` - это место на СЛЕДУЮЩЕЙ серии."""
    saved = entry(
        kind="tv", season=5, episode=1, pos=7000.0, episodes=[(5, 1, 0, 10**9), (5, 2, 1, 10**9)]
    )

    kept = _kept_place(_state_with(saved), ("кино", saved), Args(query=["кино"], release=2))

    assert kept is not None
    _, args, place = kept
    assert str(args.episode) == "s5e2"
    assert place.pos == 0.0, "следующая серия начинается с нуля"
    assert "досмотрено" in capsys.readouterr().out


def test_a_hand_named_release_does_not_keep_the_place_of_a_movie() -> None:
    """У фильма одно место на всю картину: ручной релиз играет его с начала, как и было."""
    saved = entry(pos=265.0)

    assert _kept_place(_state_with(saved), ("кино", saved), Args(query=["кино"], release=2)) is None


def test_a_finished_series_has_no_place_to_keep() -> None:
    """Досмотренная раздача - не место: дальше решает обычный путь."""
    saved = entry(kind="tv", season=5, episode=2, done=True, episodes=[(5, 1), (5, 2)])

    assert _kept_place(_state_with(saved), ("кино", saved), Args(query=["кино"], release=2)) is None


def test_a_hand_named_episode_outranks_the_bookmark_place() -> None:
    """Человек сам назвал ДРУГУЮ серию - его слово старше закладки."""
    saved = entry(kind="tv", season=5, episode=1, pos=265.0, episodes=[(5, 1), (5, 2)])

    kept = _kept_place(_state_with(saved), ("кино", saved), Args(query=["кино", "s2e3"], release=2))

    assert kept is None


def test_the_bookmarked_episode_named_by_hand_keeps_its_place() -> None:
    """Названная руками серия совпала с закладкой - продолжается её место."""
    saved = entry(kind="tv", season=5, episode=1, pos=265.0, episodes=[(5, 1), (5, 2)])

    kept = _kept_place(_state_with(saved), ("кино", saved), Args(query=["кино", "s5e1"], release=2))

    assert kept is not None
    assert kept[2].pos == 265.0


def test_a_hand_named_release_of_a_series_with_kept_place_says_nothing_about_a_loss(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Место сериала поднято - строка «сохранённое место не поднимаю» была бы ложью."""
    saved = entry(kind="tv", season=5, episode=1, pos=265.0, episodes=[(5, 1), (5, 2)])

    code = _continue_picked(
        Config(),
        _state_with(saved),
        cast(Any, plan()),
        Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино", "s5e1"], release=2),
        clock=_Clock(),
    )

    assert code is None
    assert capsys.readouterr().out == ""


def test_a_hand_named_release_of_a_series_at_another_episode_says_the_place_is_dropped(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Человек назвал другую серию - место закладки правда теряется, и строка остаётся."""
    saved = entry(kind="tv", season=5, episode=1, pos=265.0, episodes=[(5, 1), (5, 2)])

    code = _continue_picked(
        Config(),
        _state_with(saved),
        cast(Any, plan()),
        Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино", "s2e3"], release=2),
        clock=_Clock(),
    )

    assert code is None
    said = phrase("bookmark.release_named_resume", title="Кино", pos="0:04:25")
    assert said in capsys.readouterr().out


def test_a_buried_release_is_not_played_again_by_the_bookmark_of_the_chosen_picture(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-571. Похороненную раздачу второй выход закладки обратно не поднимает.

    Первый выход уже спросил рой и получил отказ. Заходить сюда с той же записью значило
    бы спросить его второй раз - ещё минута ожидания за заранее известный ответ, - да ещё
    и снести ``bench.drop_all()`` прогрев, который поиску прямо сейчас и понадобится.
    """
    args = Args(query=["кино"])
    args.bury(entry().magnet)
    bench = Bench()

    code = _continue_picked(
        Config(),
        _state_with(entry()),
        cast(Any, plan()),
        bench,  # type: ignore[arg-type]
        args=args,
        clock=_Clock(),
    )

    assert code is None
    assert bench.dropped == 0, "прогрев нужен поиску, в который закладка сама же и ушла"
    assert capsys.readouterr().out == "", "про мёртвую раздачу уже сказано, второй раз незачем"


def test_a_buried_picture_keeps_its_warm_like_any_other() -> None:
    """Записанная раздача не играется - значит греть картину надо наравне с прочими."""
    args = Args(query=["кино"])
    args.bury(entry().magnet)

    assert _plays_recorded(_state_with(entry()), plan().picture.key, args) is False
