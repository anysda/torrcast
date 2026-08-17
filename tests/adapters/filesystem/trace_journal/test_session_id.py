"""Идентификатор запуска: заводится один раз и живёт в окружении, чтобы доехать до юнита."""

from __future__ import annotations

import pytest

from torrcast.adapters.filesystem.trace_journal.session_id import SID_ENV, session_id


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
    import os

    assert os.environ[SID_ENV] == made, "заведённый кладётся в окружение, а не в память"


def test_the_name_of_the_variable_is_the_contract_between_two_processes() -> None:
    """Команда ставит её в окружение, юнит показа читает: разойдись имя - сеансов два."""
    assert SID_ENV == "TORRCAST_SID"
