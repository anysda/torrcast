"""Зеркало сценария флага языка: выбор ложится в настройку и называется вслух."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.cli.main import main
from torrcast.domain.args import Args
from torrcast.domain.catalogs.tongue import tongue
from torrcast.domain.config import Config
from torrcast.runtime.language_command import language_command
from torrcast.runtime.wire import wire


def test_the_choice_is_written_to_the_settings_and_named_aloud(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert language_command("ru") == 0

    assert load_config().language == "ru"
    assert "русский" in capsys.readouterr().out


def test_the_confirmation_speaks_the_language_it_switched_to(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Отчёт "cast --en" не смеет звучать по-русски, а "cast --ru" - по-английски.

    Сравнение построчное и точное: у английского имя языка пишется с заглавной буквы
    ("English"), и строка со строчной "english" обязана считаться таким же провалом,
    как и русский текст на английском флаге.
    """
    assert language_command("en") == 0
    assert capsys.readouterr().out == "language: English\n"

    assert language_command("ru") == 0
    assert capsys.readouterr().out == "язык: русский\n"


def test_the_choice_outlives_the_run_and_leaves_the_neighbours_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Язык - настройка: он остаётся в файле, а чужие ключи в нём остаются нетронутыми."""
    path = tmp_path / "config.json"
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))
    save_config(Config(tv="10.0.0.50"))
    stored = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**stored, "token": "1:проба"}), encoding="utf-8")

    language_command("ru")

    written = json.loads(path.read_text(encoding="utf-8"))
    assert (written["language"], written["tv"], written["token"]) == ("ru", "10.0.0.50", "1:проба")


def test_a_bare_language_flag_switches_the_language_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Настоящий ``cast --ru``: ни пустого поиска, ни справки - переключение и ноль."""
    assert main(["--ru"]) == 0

    assert load_config().language == "ru"
    assert "русский" in capsys.readouterr().out


def test_a_language_flag_next_to_a_query_switches_the_language_too() -> None:
    """``cast --ru мумия`` - и переключение, и работа: флаг чужой работы не отменяет."""
    played: list[str] = []

    def play(args: Args) -> int:
        played.append(args.title_query)
        return 0

    def remember(args: Args) -> int:
        return language_command(str(args.language))

    table: dict[str, Callable[[Args], int]] = {"play": play, "language": remember}

    assert main(["--ru", "мумия"], table) == 0

    assert load_config().language == "ru"
    assert played == ["мумия"]


def test_the_named_work_in_the_same_run_already_speaks_the_new_language() -> None:
    """🔴 ``cast --ru мумия`` делает названную работу ТУТ ЖЕ, тем же процессом.

    Настройка ляжет на диск, а надписи собираются в памяти: не переключи каталог сразу -
    человек прочитал бы «язык: русский» и следом английское меню, а до русского дожил бы
    только следующий запуск.
    """
    wire()
    assert language_command("ru") == 0
    assert tongue() == "ru"

    assert language_command("en") == 0
    assert tongue() == "en"
