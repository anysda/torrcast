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
