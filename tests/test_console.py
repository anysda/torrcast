"""Консоль: кириллица в вопросах, чистка ввода, вопрос без терминала.

Живьём это ловится в ssh-сессии без ``stty``; здесь то же самое на pty, который делаем
сами, плюс поведение там, где терминала нет вовсе (юнит, пайп, cron).
"""

from __future__ import annotations

import io
import os
import pty
import sys
import termios
import time

import pytest

from torrcast import console


def test_broken_input_never_reaches_the_parser() -> None:
    """Одиночные суррогаты и управляющие символы чистятся на любом ответе."""
    assert console.clean("моа\udcd0на") == "моана"
    assert console.clean(" да\x07\x1b ") == "да"
    assert console.clean("моана").encode("utf-8") == "моана".encode()
    # Ответ из битого pty обязан пережить запись в файл - на этом рвалось всё остальное.
    assert console.clean("Моана\udce2\udc80").encode("utf-8", "strict")


def test_the_terminal_gets_iutf8_and_gives_the_mode_back() -> None:
    """IUTF8 включается на время команды и возвращается как было.

    Именно он чинит забой на кириллице: без него ssh-pty стирает один байт из двух.
    """
    parent, child = pty.openpty()
    saved = sys.stdin
    try:
        sys.stdin = open(child, encoding="utf-8")  # noqa: SIM115 - закрываем в finally
        before = termios.tcgetattr(child)
        termios.tcsetattr(child, termios.TCSANOW, [before[0] & ~console.iutf8(), *before[1:]])
        assert not termios.tcgetattr(child)[0] & console.iutf8(), "готовим pty как у ssh"

        with console.terminal():
            assert termios.tcgetattr(child)[0] & console.iutf8(), "внутри команды IUTF8 включён"

        assert not termios.tcgetattr(child)[0] & console.iutf8(), "режим возвращён как был"
    finally:
        sys.stdin.close()
        sys.stdin = saved
        os.close(parent)


def test_a_question_without_a_terminal_takes_the_default_instead_of_hanging(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Без tty ``input()`` больше не висит (наблюдалось 180 с) — берёт дефолт."""
    monkeypatch.setattr(console, "stdin_is_tty", lambda: False)

    def refuse(prompt: str = "") -> str:
        pytest.fail("без терминала спрашивать некого")

    monkeypatch.setattr("builtins.input", refuse)

    assert console.ask("Что смотрим?", 3, default=2) == 2
    assert console.ask_line("Продолжить? [Да/сначала]") == ""
    assert "терминала нет" in capsys.readouterr().out


def test_a_question_takes_a_digit_and_a_bare_enter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Любой вопрос принимает и цифру, и пустой Enter."""
    answers = iter(["2", "", "  3  ", "нет", "1"])
    monkeypatch.setattr(console, "stdin_is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert console.ask("Что смотрим?", 3) == 2
    assert console.ask("Что смотрим?", 3) == 1, "Enter - это дефолт"
    assert console.ask("Что смотрим?", 3) == 3, "пробелы вокруг цифры не мешают"
    assert console.ask("Что смотрим?", 3) == 1, "чушь переспрашивается, а не падает"


def test_a_question_without_a_default_ignores_a_bare_enter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Дефолта нет (``None``) - Enter не ответ: номер части называет человек (TC-373)."""
    answers = iter(["", "2"])
    monkeypatch.setattr(console, "stdin_is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert console.ask("Что смотрим?", 3, default=None) == 2

    monkeypatch.setattr(console, "stdin_is_tty", lambda: False)
    with pytest.raises(EOFError):
        console.ask("Что смотрим?", 3, default=None)


def test_russian_answer_survives_the_question(monkeypatch: pytest.MonkeyPatch) -> None:
    """Русский ввод допустим, но никогда не обязателен."""
    monkeypatch.setattr(console, "stdin_is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "Сначала")
    assert console.ask_line("Продолжить? [Да/сначала]") == "сначала"


def test_progress_names_every_phase_and_its_time() -> None:
    """Фазы с бегущим временем: пользователь видит, на чём стоим, и сколько уже."""
    out = io.StringIO()
    progress = console.Progress(out=out, tick=0.01)
    assert not progress.live, "не терминал - печатаем построчно, без перерисовки"
    progress.phase("поиск «моана»")
    time.sleep(0.05)
    progress.phase("метаданные (DHT)")
    progress.stop()

    printed = _said(out)
    assert "поиск «моана»... 0." in printed
    assert "метаданные (DHT)... 0." in printed


def _said(out: io.StringIO) -> str:
    """Что напечатал прогресс: он пишет в свой поток, а по умолчанию это stdout."""
    return out.getvalue()


def test_the_running_clock_survives_an_empty_phase() -> None:
    """Пустая фаза между фазами не должна уносить с собой бегущее время.

    `cli._search` закрывает фазу поиска пустой строкой, а следом идут «метаданные (DHT)»
    и «дорожки» — те самые 4–17 секунд, ради которых бегущее время и заведено. Поток тика
    заводится только пока его нет вовсе, поэтому, уходя на первом же `phase("")`, он
    оставлял человека смотреть на замершее «метаданные (DHT)… 0 с».
    """

    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    out = Tty()
    progress = console.Progress(out=out, tick=0.01)
    assert progress.live, "терминал: строка перерисовывается на месте"
    progress.phase("поиск")
    progress.phase("")
    progress.phase("метаданные (DHT)")
    time.sleep(0.15)
    progress.stop()

    assert out.getvalue().count("метаданные (DHT)") > 2, "время второй фазы обязано бежать"
