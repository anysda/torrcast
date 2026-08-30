"""Зеркало продолжения по состоянию: когда оно отвечает само, а когда уступает поиску."""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes.journal import Tape
from tests.usecases.select.world import entry
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.usecases.select._continue import _continue
from torrcast.usecases.start_clock import _Clock


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - продолжение по состоянию с русскими строками уступки поиску."""


_SERIES: dict[str, object] = {
    "kind": "tv",
    "season": 1,
    "episode": 2,
    "episodes": [[1, 1, 0], [1, 2, 1], [1, 3, 2]],
}


class _Shown:
    """Показ, который никуда не уезжает, а запоминает, с чем его позвали."""

    def __init__(self, verdict: str = "") -> None:
        self.launched: list[tuple[str, str]] = []
        self.resumed: list[str] = []
        #: Приговор записанной раздаче: пусто - играет. Спрашивать про неё живую службу
        #: зеркалу нельзя: молчание отказавшего соединения читается как «играет», и любой
        #: из этих случаев зеленел бы сам собой, даже когда мерить уже нечего.
        self.verdict = verdict
        self.asked: list[str] = []

    def launch(
        self, config: Config, key: str, saved: Entry, about: str, clock: _Clock, dry: bool = False
    ) -> int:
        self.launched.append((saved.label, about))
        return EXIT_OK

    def resume(
        self, config: Config, key: str, saved: Entry, clock: _Clock, dry: bool = False
    ) -> int:
        self.resumed.append(saved.title)
        return EXIT_OK

    def dead(self, config: Config, saved: Entry, own: object) -> str:
        self.asked.append(saved.magnet)
        return self.verdict

    @property
    def calls(self) -> dict[str, Any]:
        """Все три соседа продолжения разом - ровно теми именами, какими их зовут."""
        return {"launch": self.launch, "resume": self.resume, "dead": self.dead}


def test_a_film_with_nothing_to_continue_gives_way_to_the_usual_path() -> None:
    """Продолжать нечего - озвучку выберет обычный путь, по дорожкам потока."""
    shown = _Shown()

    code = _continue(
        Config(),
        "movie:кино:1999",
        entry(pos=0.0),
        Args(query=["кино"]),
        _Clock(),
        **shown.calls,
    )

    assert code is None
    assert (shown.launched, shown.resumed) == ([], [])


def test_a_film_in_the_middle_is_resumed_without_a_single_question() -> None:
    """Релиз, дорожка, файл и позиция уже записаны - спрашивать нечего."""
    shown = _Shown()

    code = _continue(
        Config(), "movie:кино:1999", entry(), Args(query=["кино"]), _Clock(), **shown.calls
    )

    assert code == EXIT_OK
    assert shown.resumed == ["Кино"]


def test_a_named_episode_is_not_answered_by_a_film_bookmark() -> None:
    """`cast кино s1e1` при закладке фильма - запрос сериала: отвечать на него нечем."""
    shown = _Shown()

    code = _continue(
        Config(),
        "movie:кино:1999",
        entry(),
        Args(query=["кино", "s1e1"]),
        _Clock(),
        **shown.calls,
    )

    assert code is None, "серию просили у фильма - идём искать сериал"
    assert (shown.launched, shown.resumed) == ([], [])


def test_an_asked_episode_jumps_by_the_cache_of_the_torrent() -> None:
    """`cast кино s1e3` - прыжок по кэшу раздачи, без Prowlarr и без вопросов."""
    saved, shown = entry(**_SERIES), _Shown()

    code = _continue(
        Config(), "tv:кино", saved, Args(query=["кино", "s1e3"]), _Clock(), **shown.calls
    )

    assert code == EXIT_OK
    assert [label for label, _about in shown.launched] == ["s1e3"]


def test_an_episode_the_torrent_does_not_have_goes_looking_for_a_release() -> None:
    """Серии в этой раздаче нет - честно идём искать релиз сезона, а не врём отказом."""
    saved, shown = entry(**_SERIES), _Shown()

    code = _continue(
        Config(), "tv:кино", saved, Args(query=["кино", "s9e1"]), _Clock(), **shown.calls
    )

    assert code is None
    assert shown.launched == []


def test_a_film_whose_recorded_release_no_longer_plays_goes_looking_by_itself(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-571. Раздача умерла - продолжение уступает поиску само, а не молчит шесть минут.

    До этой правки записанный выбор был единственной дверью без выхода: магнит отдавался
    показу как есть, и зритель получал до :data:`START_BUDGET` секунд чёрного экрана и
    код 2. Теперь тот же случай стоит одну честную строку и обычный путь поиска.
    """
    shown = _Shown(verdict="раздача не отдала метаданные за 60 с - нет пиров")
    args = Args(query=["кино"])

    code = _continue(Config(), "movie:кино:1999", entry(), args, _Clock(), **shown.calls)

    assert code is None, "продолжение уступило обычному пути само"
    assert shown.resumed == [], "мёртвую раздачу показу не отдают"
    assert capsys.readouterr().out == (
        "«Кино» - записанная раздача не играется: раздача не отдала метаданные за 60 с - "
        "нет пиров; ищу другую с 1:00:00\n"
    )
    assert args.dead_hash, "имя мёртвой раздачи уезжает в отбор - иначе он вернёт её же"


def test_a_series_whose_recorded_release_no_longer_plays_names_the_episode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """У сериала в той же строке названа серия: зритель видит, ЧТО именно не сыграло."""
    shown = _Shown(verdict="файла №1 в ней больше нет")
    args = Args(query=["кино"])

    code = _continue(Config(), "tv:кино", entry(**_SERIES), args, _Clock(), **shown.calls)

    assert code is None
    assert shown.launched == []
    assert capsys.readouterr().out == (
        "«Кино» s1e2 - записанная раздача не играется: файла №1 в ней больше нет; "
        "ищу другую с 1:00:00\n"
    )


def test_a_healthy_recording_plays_as_it_played_and_is_asked_about_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 Здоровая запись играет ровно как играла: один вопрос про рой и ни слова лишнего.

    Ложный отказ хуже отказа вовсе, поэтому мерится не только исход, но и цена: раздачу
    спрашивают ОДИН раз, тем же магнитом, который через секунду поднимет сам юнит.
    """
    shown = _Shown()

    code = _continue(
        Config(), "movie:кино:1999", entry(), Args(query=["кино"]), _Clock(), **shown.calls
    )

    assert code == EXIT_OK and shown.resumed == ["Кино"]
    assert shown.asked == ["magnet:?xt=кино"]
    assert capsys.readouterr().out == "", "здоровой записи объяснять нечего"


def test_the_cheap_reasons_to_give_way_do_not_cost_a_single_trip_to_the_swarm() -> None:
    """Продолжать нечего - это ответ состоянием, и рой об этом не спрашивают вовсе."""
    shown = _Shown(verdict="раздача не отдала метаданные за 60 с - нет пиров")

    code = _continue(
        Config(), "movie:кино:1999", entry(pos=0.0), Args(query=["кино"]), _Clock(), **shown.calls
    )

    assert code is None and shown.asked == []


def test_a_dry_run_wakes_no_swarm_to_judge_the_recorded_release() -> None:
    """Сухой прогон не будит рой: показа у него нет, чёрного экрана тоже, следов - тем более."""
    shown = _Shown(verdict="раздача не отдала метаданные за 60 с - нет пиров")

    args = Args(query=["кино"], dry=True)

    code = _continue(Config(), "movie:кино:1999", entry(), args, _Clock(), **shown.calls)

    assert code == EXIT_OK and shown.asked == []


def test_a_dry_run_leaves_no_mark_of_the_liveness_check(tape: Tape) -> None:
    """Сухой прогон не спрашивает ничего - и отметки о проверке живости не ставит."""
    shown = _Shown(verdict="раздача не отдала метаданные за 60 с - нет пиров")

    args = Args(query=["кино"], dry=True)

    code = _continue(Config(), "movie:кино:1999", entry(), args, _Clock(), **shown.calls)

    assert code == EXIT_OK
    assert tape.named("записанная раздача") == []
