"""Зеркало :mod:`torrcast.adapters.filesystem.trace_journal`: недельный след показа.

Горячий путь, потолок места и потери очереди сторожит набор следа (``tests/test_trace.py``).
Здесь - раскладка ленты и склейка сеансов: куда лента ложится, как она делится по суткам и
почему поиск, отбор и показ одного запуска сходятся в одну строку истории, а серии при этом
не слипаются в один сеанс.

Часов эти проверки не трогают: сутки задаются меткой времени, идентификатор - окружением.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state import state_path
from torrcast.adapters.filesystem.trace_journal import (
    LOG_ENV,
    RETAIN_DAYS,
    SID_ENV,
    log_dir,
    log_path,
    session_id,
    start_session,
)

#: Две метки времени внутри одних суток и одна - в следующих (UTC, полдень и вечер).
NOON = 1_754_654_400.0
EVENING = NOON + 8 * 3600
NEXT_DAY = NOON + 24 * 3600


def test_the_trace_lies_next_to_the_state_unless_it_is_sent_elsewhere(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """По умолчанию лента живёт рядом с состоянием, а переопределение уводит её целиком.

    Рядом с состоянием - потому что это одно хозяйство одного пользователя: разъедься они,
    и `cast log` читал бы не тот след, который писал показ. Переопределение нужно ровно
    затем, чтобы заведомо тестовый или локальный запуск не мешал свои записи в общую ленту.
    """
    monkeypatch.delenv(LOG_ENV, raising=False)
    assert log_dir() == state_path().parent

    monkeypatch.setenv(LOG_ENV, str(tmp_path / "след"))
    assert log_dir() == tmp_path / "след"


def test_the_tape_is_cut_by_days_so_a_week_can_be_kept_and_dropped_by_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ротация идёт по суткам: один файл - одни сутки, и хранится их неделя.

    Именно поэтому старое убирается удалением файла, а не переписыванием ленты: сложи все
    записи в один файл - и «держим неделю» превратилось бы в вычитание строк из растущего
    файла на каждом запуске показа.
    """
    monkeypatch.setenv(LOG_ENV, str(tmp_path))

    assert log_path(NOON) == log_path(EVENING)
    assert log_path(NOON) != log_path(NEXT_DAY)
    assert log_path(NOON).parent == tmp_path
    assert RETAIN_DAYS >= 7, "неделя - это то, за что вообще имеет смысл спрашивать след"


def test_the_identifier_of_a_run_is_made_once_and_inherited_by_everything_it_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Идентификатор кэшируется в окружении - и потому доезжает до юнита показа.

    Показ идёт в отдельном процессе. Заведи он себе свой идентификатор - поиск, отбор и
    картинка на экране легли бы в ленту тремя разными сеансами, и связать их было бы нечем.
    """
    monkeypatch.setenv(SID_ENV, "запуск-1")

    assert session_id() == "запуск-1"
    assert session_id() == "запуск-1", "второй вопрос не заводит второй идентификатор"


def test_a_run_without_an_identifier_gets_one_instead_of_staying_nameless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Пустое окружение - обычный случай первого запуска, а не повод остаться без имени.

    Останься сеанс безымянным - все записи недели слились бы в один блок выжимки, и
    разобрать по ней отдельный показ стало бы нельзя.
    """
    monkeypatch.delenv(SID_ENV, raising=False)

    made = session_id()

    assert made
    assert session_id() == made, "заведённый идентификатор тут же становится общим"


def test_each_episode_starts_its_own_session_without_losing_the_run_it_belongs_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Серия начинает свой сеанс, но остаётся частью того же запуска ``cast``.

    Родительский идентификатор в начале строки сохраняет связь с вызовом, суффикс не даёт
    сериям склеиться. Потеряй он родителя - серия выглядела бы чужим запуском; потеряй
    суффикс - весь сериал стал бы одним сеансом с общим счётчиком ребуферов.
    """
    monkeypatch.setenv(SID_ENV, "запуск-2")

    first = start_session()
    second = start_session()

    assert first != second
    assert first.startswith("запуск-2.")
    assert second.startswith("запуск-2.")
    assert session_id() == second, "текущим сеансом становится последний начатый"
