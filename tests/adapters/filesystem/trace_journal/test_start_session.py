"""Отдельный сеанс на серию: суффикс не даёт сериям слипнуться, корень держит запуск."""

from __future__ import annotations

import pytest

from torrcast.adapters.filesystem.trace_journal.session_id import SID_ENV, session_id
from torrcast.adapters.filesystem.trace_journal.start_session import start_session


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


def test_the_counter_restarts_when_a_new_run_brings_its_own_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Новый запуск ``cast`` - новый корень и счёт серий с единицы.

    Иначе номера серий росли бы сквозь запуски, и «первая серия этого вечера» имела бы
    в ленте номер, зависящий от того, сколько смотрели вчера.
    """
    monkeypatch.setenv(SID_ENV, "запуск-3")
    assert start_session() == "запуск-3.1"

    monkeypatch.setenv(SID_ENV, "запуск-4")
    assert start_session() == "запуск-4.1"
