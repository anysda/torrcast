"""Длительность картины, замеренная паспортом файла прошлого показа."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.select._measured_runtime import _measured_runtime

_KEY = "tv:киберпанк-бегущие-по-краю:2022"


def _state(dur: float) -> WatchState:
    """Состояние, в котором картину уже смотрели и паспорт файла замерил длительность."""
    return WatchState(
        {
            _KEY: Entry(
                title="Киберпанк: Бегущие по краю",
                magnet="magnet:?xt=urn:btih:" + "a" * 40,
                kind="tv",
                dur=dur,
            )
        }
    )


def test_the_measured_duration_of_the_file_comes_out_of_the_entry() -> None:
    """🔴 TC-819. Запись знает: серия длится 27 минут, а не прикинутые 45."""
    assert _measured_runtime(_state(1620.0), _KEY) == 1620.0


def test_a_picture_never_watched_has_no_measured_runtime() -> None:
    """Паспорта файла нет - ответ ноль, и знаменателем остаётся честно названная прикидка."""
    assert _measured_runtime(WatchState(), _KEY) == 0.0


def test_an_entry_without_a_passport_stays_silent() -> None:
    """Запись прежней версии длительности не несёт: ноль, а не выдуманное число."""
    assert _measured_runtime(_state(0.0), _KEY) == 0.0


def test_the_entry_found_by_the_query_text_is_the_fallback() -> None:
    """Канонического ключа нет - берём запись, которую нашёл сам запрос (как память студии)."""
    found = ("tv:киберпанк:2022", _state(1620.0).entries[_KEY])

    assert _measured_runtime(WatchState(), "tv:киберпанк:2022", found) == 1620.0
    assert _measured_runtime(WatchState(), "tv:киберпанк:2022", None) == 0.0
