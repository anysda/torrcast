"""Зеркало :mod:`torrcast.runtime.main`: точка входа ``cast``.

Модуль существует ради одного порядка действий, и он же тут сторожится: команда обязана
получить внешний мир УЖЕ собранным. Console-script указывает сюда, а не сразу в команду,
ровно потому, что собирать мир - дело композиционного корня, и только его.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from torrcast.domain.exit_codes import EXIT_INFRA
from torrcast.runtime.main import main


def test_the_world_is_assembled_before_the_command_gets_to_work() -> None:
    """Сборка идёт первой, команда второй - иначе команда работает по пустым портам.

    Поменяй порядок - и первая же команда пошла бы в незаполненные порты: след молчал бы,
    состояние читалось бы мимо адаптера, а понять это по выводу было бы нельзя - выглядит
    как «просто ничего не записалось».
    """
    order: list[str] = []

    def fake_wire() -> None:
        order.append("собрали мир")

    def fake_run(argv: Sequence[str] | None) -> int:
        order.append("выполнили команду")
        return 0

    main(["status"], assemble=fake_wire, command=fake_run)

    assert order == ["собрали мир", "выполнили команду"]


def test_the_arguments_reach_the_command_untouched() -> None:
    """Точка входа ничего не разбирает сама и отдаёт аргументы команде как есть.

    Начни она их трогать - разбор жил бы в двух местах, и флаг, понятный команде, мог бы
    потеряться по дороге ещё до того, как о нём кто-нибудь узнал.
    """
    seen: list[Sequence[str] | None] = []

    def fake_run(argv: Sequence[str] | None) -> int:
        seen.append(argv)
        return 0

    main(["кино", "--release", "2"], assemble=lambda: None, command=fake_run)
    main(None, assemble=lambda: None, command=fake_run)

    assert seen == [["кино", "--release", "2"], None]


def test_the_exit_code_of_the_command_is_the_exit_code_of_the_process() -> None:
    """Код возврата команды уходит наружу нетронутым - по нему судит вызывающий.

    Проглоти точка входа неудачу - скрипт, запустивший `cast`, считал бы провалившийся
    показ успешным и пошёл бы дальше по своему сценарию.
    """
    assert main(["status"], assemble=lambda: None, command=lambda argv: 3) == 3


def _trace_records(directory: Path) -> list[dict[str, object]]:
    """Записи ленты как их оставил настоящий писатель - по всем файлам каталога."""
    rows: list[dict[str, object]] = []
    for path in sorted(directory.glob("trace-*.jsonl")):
        for raw in path.read_text("utf-8").splitlines():
            rows.append(json.loads(raw))
    return rows


def test_log_works_when_the_configuration_is_broken(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`cast log` читает след, а не настройку, которая могла его сломать."""
    config_path = tmp_path / "config.json"
    config_path.write_text("{", encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(config_path))

    code = main(["log"])

    assert code == 0
    assert capsys.readouterr().out == "no trace - not a single session over the week\n"


def test_a_command_that_needs_configuration_still_names_the_broken_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Fallback языка не стирает признак: `status` обязан сам прочесть настройку."""
    config_path = tmp_path / "config.json"
    config_path.write_text("{", encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(config_path))

    code = main(["status"])

    assert code != 0
    assert str(config_path) in capsys.readouterr().err


@pytest.mark.parametrize(
    ("config_text", "stderr_substring"),
    [
        ("{не json", "broken config"),
        # Неведомый язык - это тот самый случай, когда домен не вправе спросить
        # каталог, на каком языке пожаловаться (:mod:`torrcast.domain.catalogs.tongue`):
        # жалоба всегда по-английски, тем же выбором, что у нечитаемой настройки.
        ('{"language": "de"}', "unknown setting language"),
    ],
    ids=["битый-json", "неведомый-язык"],
)
def test_a_broken_assembly_reaches_the_human_the_same_way_a_broken_command_does(
    config_text: str,
    stderr_substring: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Беда с настройкой обязана дойти до человека текстом и кодом инфры, а не трейсбеком.

    Пути у двух случаев разные, и оба названы. Неведомый язык ломает СБОРКУ:
    :func:`~torrcast.runtime.wire.wire` читает язык настройки раньше, чем
    :func:`~torrcast.cli.answered.answered` вообще заводится, и отказ ловит ограда самой
    точки входа (:func:`~torrcast.runtime.main.main`, TC-929, заход 4). Битый JSON сборку
    переживает (:func:`~torrcast.adapters.filesystem.state.chosen_language.chosen_language`
    отвечает на него английским оформлением, а не отказом), и настройку честно читает
    команда - отказ ловит уже ``answered``. Мера трогает боевую пару
    ``assemble``/``command`` (умолчание точки входа), а не подставные фейки.
    """
    config_path = tmp_path / "config.json"
    config_path.write_text(config_text, encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(config_path))

    code = main(["status"])

    assert code == EXIT_INFRA
    assert stderr_substring in capsys.readouterr().err


@pytest.mark.machine
def test_an_assembly_failure_lands_in_the_trace_of_the_real_process(tmp_path: Path) -> None:
    """Отказ сборки обязан попасть в след, и меряется это подпроцессом, а не здесь.

    🔴 Внутри pytest это утверждение доказать нельзя: сессионная ``_wired``
    (:mod:`tests.conftest`) зовёт :func:`~torrcast.runtime.wire.wire` один раз на весь
    прогон ещё до первого теста, а функциональная ``_ports_restored`` возвращает слот -
    боевая :class:`~torrcast.adapters.filesystem.trace_journal.file_journal.FileJournal`
    уже стоит в слоте независимо от порядка строк внутри ``wire()``. Замер мержера
    (TC-947): набор молча пропускал перестановку ``install_journal`` НИЖЕ чтения
    настройки (7 passed), а боевая точка входа на том же коде писала в след 0 записей
    вместо двух - слот держал :class:`~torrcast.ports.journal.silent.Silent`. Поэтому
    здесь - настоящий процесс ``cast``, где никакой сессионной сборки нет.
    """
    config_path = tmp_path / "config.json"
    config_path.write_text('{"language": "de"}', encoding="utf-8")
    trace = tmp_path / "trace"
    trace.mkdir()
    env = {
        **os.environ,
        "TORRCAST_CONFIG": str(config_path),
        "TORRCAST_LOG": str(trace),
        "TORRCAST_STATE": str(tmp_path / "state.json"),
    }

    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from torrcast.runtime.main import main; sys.exit(main(['status']))",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert done.returncode == EXIT_INFRA
    assert "unknown setting language" in done.stderr
    records = _trace_records(trace)
    assert any(row.get("phase") == "error" for row in records), (
        "отказ сборки обязан попасть в след, а не пройти мимо журнала"
    )
    assert any(
        row.get("phase") == "command"
        and row.get("event") == "finished"
        and row.get("result") == "assembly_failure"
        for row in records
    ), "след обязан закрыться ярлыком assembly_failure, а не оборваться на ошибке"
