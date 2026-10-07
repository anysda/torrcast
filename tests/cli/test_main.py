"""Точка входа ``cast``: разбор строки, выбор команды и перевод отказов в коды возврата."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pytest

from torrcast.cli.main import main
from torrcast.domain.args import Args
from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_NOT_FOUND, EXIT_OK
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.usecases.stopped import _Stopped

#: Все имена контракта: :attr:`Args.command` других не отдаёт.
_NAMES = (
    "configure",
    "language",
    "stop",
    "status",
    "doctor",
    "log",
    "releases",
    "voices",
    "worker",
    "play",
)


def _table(command: Callable[[Args], int]) -> Mapping[str, Callable[[Args], int]]:
    """Одна и та же команда на каждое имя: проверяем не выбор, а обработку её ответа."""
    return dict.fromkeys(_NAMES, command)


class _Named:
    """Команда, которая только записывает своё имя: по нему и видно, куда ушёл разбор."""

    def __init__(self, name: str, called: list[str]) -> None:
        self._name, self._called = name, called

    def __call__(self, _args: Args) -> int:
        self._called.append(self._name)
        return EXIT_OK


def _raises(error: BaseException) -> Callable[[Args], int]:
    def command(_args: Args) -> int:
        raise error

    return command


@pytest.mark.parametrize(
    ("argv", "command"),
    [
        ([], "play"),
        (["--tv", "10.0.0.50"], "configure"),
        (["stop"], "stop"),
        (["status"], "status"),
        (["doctor"], "doctor"),
        (["log"], "log"),
        (["releases", "кино"], "releases"),
        (["voices", "кино"], "voices"),
        (["--play-key", "movie:кино:1999"], "worker"),
        (["моана", "2"], "play"),
        (["--ru"], "language"),
        # Флаг, который команда читает, дорогу ей не закрывает: лента по-прежнему отвечает
        # на `--since`, а голый показ - на `--dry`, и «продолжи последнее» остаётся (TC-1003).
        (["log", "--since", "2h"], "log"),
        (["--dry"], "play"),
    ],
)
def test_every_name_of_the_contract_reaches_its_own_command(argv: list[str], command: str) -> None:
    called: list[str] = []
    table: Mapping[str, Callable[[Args], int]] = {name: _Named(name, called) for name in _NAMES}

    assert main(argv, table) == EXIT_OK
    assert called == [command]


@pytest.mark.parametrize(
    ("argv", "flag"),
    [
        (["--since", "2h"], "--since"),
        (["--tv", "10.0.0.50", "моана"], "--tv"),
    ],
)
def test_a_flag_the_show_does_not_read_is_named_and_the_show_does_not_start(
    argv: list[str], flag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-1003. Цена молчания тут не пустой вывод, а занятый телевизор.

    ``cast --since 2h`` терял флаг молча, уходил в «продолжи последнее» и заводил показ:
    просьба почитать ленту оборачивалась запуском. Поэтому мера смотрит на ДВЕ вещи
    сразу - названный флаг в stderr и пустой список позванных команд, - а не на одну
    строку вывода: строка при заведённом показе была бы такой же.
    """
    called: list[str] = []
    table: Mapping[str, Callable[[Args], int]] = {name: _Named(name, called) for name in _NAMES}

    assert main(argv, table) == EXIT_INFRA
    assert called == []
    assert capsys.readouterr().err.strip() == f"flag {flag} is not understood here"


def test_a_language_flag_next_to_work_remembers_the_choice_before_doing_the_work() -> None:
    """Порядок тут договор: язык запоминается ДО работы, и работа при этом не пропадает."""
    called: list[str] = []
    table: Mapping[str, Callable[[Args], int]] = {name: _Named(name, called) for name in _NAMES}

    assert main(["--ru", "моана"], table) == EXIT_OK
    assert called == ["language", "play"]


def test_the_code_of_the_command_is_the_code_of_the_run() -> None:
    assert main(["status"], _table(lambda _args: 7)) == 7


def test_a_thing_not_found_is_a_short_russian_line_and_its_own_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Наружу - строка без трейсбека и код «не нашли», а не два разных отказа в одном."""
    assert main(["status"], _table(_raises(NotFoundError("ничего не нашёл")))) == EXIT_NOT_FOUND

    done = capsys.readouterr()
    assert done.err.strip() == "ничего не нашёл"
    assert "Traceback" not in done.err


def test_an_infrastructure_failure_keeps_its_own_code(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["status"], _table(_raises(InfraError("TorrServer не отвечает")))) == EXIT_INFRA
    assert capsys.readouterr().err.strip() == "TorrServer не отвечает"


def test_a_stopped_show_is_a_success_and_not_a_refusal() -> None:
    """`cast stop` гасит показ сигналом - для systemd это штатный конец, а не ошибка."""
    assert main(["status"], _table(_raises(_Stopped()))) == EXIT_OK


def test_ctrl_c_stays_a_refusal() -> None:
    assert main(["status"], _table(_raises(KeyboardInterrupt()))) == EXIT_INFRA


def test_the_version_is_named_and_the_run_ends_there(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as ended:
        main(["--version"])

    assert ended.value.code == 0
    assert capsys.readouterr().out.startswith("torrcast ")


def test_the_help_names_the_commands_and_the_debug_handles(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as ended:
        main(["--help"])

    assert ended.value.code == 0
    out = capsys.readouterr().out
    assert "cast" in out and "stop / status" in out
    assert "--release" in out and "--voice" in out and "--tv" in out
