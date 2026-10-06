"""Зеркало пульта моста: слово ложится в тот же файл, из которого его берёт показ."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hass.say import TOGGLE, say
from torrcast.adapters.choice_environment import _SystemChoiceEnvironment
from torrcast.domain.debug_handles import CTL_ENV


def test_the_word_lands_where_the_show_reads_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Читателя не подделываем: слово забирает та самая единица, которой его забирает
    # идущий показ, - иначе зелень доказывала бы только «файл записан».
    ctl = tmp_path / "torrcast.ctl"
    monkeypatch.setenv(CTL_ENV, str(ctl))

    say(TOGGLE)

    assert _SystemChoiceEnvironment().read_command() == TOGGLE
    # Слово одноразовое: показ съедает файл, и второй опрос не должен нажать кнопку ещё раз.
    assert not ctl.exists()
    assert _SystemChoiceEnvironment().read_command() is None


def test_the_default_path_is_the_one_the_bot_writes_to(monkeypatch: pytest.MonkeyPatch) -> None:
    # Общий с ботом файл выходит из одной формулы, а не из договорённости: имени в
    # окружении нет - и мост, и читатель считают путь одинаково.
    monkeypatch.delenv(CTL_ENV, raising=False)
    reader = _SystemChoiceEnvironment()
    mine = os.environ.get(CTL_ENV, f"/tmp/torrcast-telegram-{os.getuid()}.ctl")

    assert reader.ctl_env == CTL_ENV
    assert mine.endswith(f"torrcast-telegram-{os.getuid()}.ctl")


def test_the_show_never_reads_half_a_word(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Запись атомарная: временный файл переименовывается поверх. Половина слова в файле
    # была бы командой, и показ выполнил бы её.
    ctl = tmp_path / "torrcast.ctl"
    monkeypatch.setenv(CTL_ENV, str(ctl))

    say("seekby 90")

    assert sorted(p.name for p in tmp_path.iterdir()) == ["torrcast.ctl"]
    assert ctl.read_text(encoding="utf-8") == "seekby 90"


def test_seeks_in_a_row_add_up_until_the_show_eats_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-1169: три нажатия подряд перезаписывали друг друга, 3x60 давали +60."""
    monkeypatch.setenv(CTL_ENV, str(tmp_path / "torrcast.ctl"))

    say("seekby 60")
    say("seekby 60")
    say("seekby 60")
    assert _SystemChoiceEnvironment().read_command() == "seekby 180"

    say("seekby -60")
    assert _SystemChoiceEnvironment().read_command() == "seekby -60"
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_another_word_left_for_the_show_is_not_read_as_a_shift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CTL_ENV, str(tmp_path / "torrcast.ctl"))

    say(TOGGLE)
    say("seekby 30")
    assert _SystemChoiceEnvironment().read_command() == "seekby 30"


def test_a_word_said_while_the_show_reads_the_last_one_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Читатель забирает файл переименованием: «прочёл, потом удалил» стирал слово моста,
    положенное между чтением и удалением."""
    monkeypatch.setenv(CTL_ENV, str(tmp_path / "torrcast.ctl"))
    say("seekby 60")
    read = Path.read_text
    between = [True]

    def reading(self: Path, *args: object, **kwargs: object) -> str:
        said = read(self, *args, **kwargs)  # type: ignore[arg-type]
        if between.pop() if between else False:
            say("seekby 30")
        return said

    monkeypatch.setattr(Path, "read_text", reading)
    assert _SystemChoiceEnvironment().read_command() == "seekby 60"
    monkeypatch.setattr(Path, "read_text", read)
    assert _SystemChoiceEnvironment().read_command() == "seekby 30"
