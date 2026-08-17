"""Живой прогресс: фаза со своим временем, бегущий тик и заметка в недельном следе."""

from __future__ import annotations

import io
import time
from typing import Any

import pytest

from torrcast.adapters.console.console.progress import _TICK, Progress
from torrcast.adapters.filesystem.trace_journal.writer import _Writer


class _Tty(io.StringIO):
    """Поток, который называет себя терминалом: на нём строка перерисовывается на месте."""

    def isatty(self) -> bool:
        return True


@pytest.mark.machine
def test_progress_names_every_phase_and_its_time() -> None:
    """Фазы с бегущим временем: пользователь видит, на чём стоим, и сколько уже."""
    out = io.StringIO()
    progress = Progress(out=out, tick=0.01)
    assert not progress.live, "не терминал - печатаем построчно, без перерисовки"
    progress.phase("поиск «моана»")
    time.sleep(0.05)
    progress.phase("метаданные (DHT)")
    progress.stop()

    printed = out.getvalue()
    assert "поиск «моана»... 0." in printed
    assert "метаданные (DHT)... 0." in printed


@pytest.mark.machine
def test_the_running_clock_survives_an_empty_phase() -> None:
    """Пустая фаза между фазами не должна уносить с собой бегущее время.

    Поток тика заводится только пока его нет вовсе, поэтому, уходя на первом же
    ``phase("")``, он оставлял человека смотреть на замершее «метаданные (DHT)… 0 с».
    """
    out = _Tty()
    progress = Progress(out=out, tick=0.01)
    assert progress.live, "терминал: строка перерисовывается на месте"
    progress.phase("поиск")
    progress.phase("")
    progress.phase("метаданные (DHT)")
    time.sleep(0.15)
    progress.stop()

    assert out.getvalue().count("метаданные (DHT)") > 2, "время второй фазы обязано бежать"


def test_the_same_phase_twice_does_not_blink_or_reset_the_clock() -> None:
    """Повтор той же фазы - не событие: мигающая строка выглядела бы как перезапуск."""
    out = io.StringIO()
    progress = Progress(out=out, tick=0.01)
    progress.phase("поиск")
    progress.phase("поиск")
    progress.stop()

    assert out.getvalue().count("поиск") == 1


def test_a_note_reaches_both_the_screen_and_the_weekly_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Заметка - это решение показа, и знать о нём при разборе сеанса надо.

    Отдельных вызовов журнала в местах решений это не заводит: их подбирает сам ``note``.
    """
    queued: list[dict[str, Any]] = []
    monkeypatch.setattr(_Writer, "put", lambda _self, record: queued.append(record))
    out = io.StringIO()
    progress = Progress(out=out, tick=0.01)

    progress.phase("отбор")
    progress.note("беру вторую раздачу: у первой нет русской дорожки")
    progress.stop()

    assert "беру вторую раздачу" in out.getvalue()
    assert [(rec["phase"], rec["event"]) for rec in queued] == [("note", "note")]
    assert queued[0]["text"] == "беру вторую раздачу: у первой нет русской дорожки"


def test_a_note_does_not_lose_the_phase_it_interrupted() -> None:
    """Строка фазы возвращается после заметки: иначе бегущее время исчезло бы с экрана."""
    out = _Tty()
    progress = Progress(out=out, tick=10.0)  # тик длинный: рисует только сам вызов

    progress.phase("отбор")
    progress.note("нашёл дубляж")
    progress.stop()

    printed = out.getvalue()
    assert printed.index("нашёл дубляж") < printed.rindex("отбор")


def test_the_default_tick_is_fast_enough_to_look_alive() -> None:
    """Молчание дольше пары секунд неотличимо от зависания, и тик заведён против него."""
    assert _TICK == 0.5
    assert Progress().tick == _TICK
