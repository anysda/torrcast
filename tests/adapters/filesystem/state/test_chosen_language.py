"""Зеркало свежего языка продукта из файла настройки."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import torrcast.adapters.filesystem.state.chosen_language as chosen_language_module
import torrcast.domain.catalogs.tongue as tongue_module
from torrcast.adapters.filesystem.state.chosen_language import chosen_language
from torrcast.adapters.filesystem.state.config_path import config_path
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config


def test_the_current_setting_is_read_on_every_call() -> None:
    save_config(Config(language="en"))
    assert chosen_language() == "en"

    save_config(Config(language="ru"))

    assert chosen_language() == "ru"


def test_a_broken_setting_falls_back_to_english(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text('{"language": ', encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(broken))

    assert chosen_language() == "en"


def test_an_unchanged_setting_is_not_read_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """Надпись спрашивает язык на каждом зове, и круг поиска читал файл ~1300 раз."""
    save_config(Config(language="ru"))
    assert chosen_language() == "ru"

    def unread() -> Config:
        raise AssertionError("файл не менялся, а его читают снова")

    monkeypatch.setattr(chosen_language_module, "load_config", unread)

    assert chosen_language() == "ru"


class _Clock:
    """Подменные часы окна сверки: время двигает тест, а не сон."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


def _foreign_write(language: str) -> None:
    """Язык меняет чужой процесс (`cast language`): мимо `save_config` этого процесса."""
    config_path().write_text(json.dumps({"language": language}), encoding="utf-8")


def test_the_language_is_asked_without_touching_the_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Надпись спрашивает язык на каждом зове: в окне сверки файл не трогают вовсе."""
    clock = _Clock()
    monkeypatch.setattr(chosen_language_module, "time", clock)
    save_config(Config(language="ru"))
    assert chosen_language() == "ru"
    stats: list[object] = []

    def counted(path: object) -> os.stat_result:
        stats.append(path)
        return os.stat(path)  # type: ignore[arg-type]

    monkeypatch.setattr(chosen_language_module, "os", SimpleNamespace(stat=counted))

    assert [chosen_language() for _ in range(100)] == ["ru"] * 100
    assert stats == []

    clock.now += chosen_language_module._GLANCE
    chosen_language()
    assert len(stats) == 1, "отрицательная проба: за окном файл сверяют снова"


def test_a_language_changed_by_another_process_is_heard_without_a_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    monkeypatch.setattr(chosen_language_module, "time", clock)
    save_config(Config(language="en"))
    assert chosen_language() == "en"

    _foreign_write("ru")
    assert chosen_language() == "en", "в окне сверки язык прежний"
    clock.now += chosen_language_module._GLANCE

    assert chosen_language() == "ru"


class _SavedMidRead:
    """Путь настройки, на первом `str` которого соседний поток пишет язык (`cast --en`).

    Так проба мержера (три потока надписей и поток записи) ловит гонку не за десять
    секунд случая, а на первом же зове: запись встаёт ровно между шагами чтения снимка.
    """

    def __init__(self, real: Path) -> None:
        self.real, self.fired = real, False

    def __str__(self) -> str:
        if not self.fired:
            self.fired = True
            writer = threading.Thread(target=save_config, args=(Config(language="en"),))
            writer.start()
            writer.join()
        return str(self.real)

    def __fspath__(self) -> str:
        return str(self.real)


@pytest.mark.machine
def test_a_language_written_by_another_thread_mid_read_does_not_break_a_phrase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_config(Config(language="ru"))
    monkeypatch.setattr(tongue_module, "_TONGUE", chosen_language)
    assert phrase("rank.reason_disc") == "образ диска"
    racing = _SavedMidRead(config_path())
    monkeypatch.setattr(chosen_language_module, "config_path", lambda: racing)

    assert phrase("rank.reason_disc") == "образ диска", "начатое чтение договаривает своё"
    assert racing.fired, "запись посреди чтения не случилась - проба ничего не проверила"
    assert phrase("rank.reason_disc") == "disc image", "следующая надпись слышит запись"


@pytest.mark.machine
def test_a_read_overtaken_by_a_save_does_not_pin_the_old_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Читатель прочёл файл до записи соседа: старый язык он отдаёт, но не запоминает."""
    clock = _Clock()
    monkeypatch.setattr(chosen_language_module, "time", clock)
    save_config(Config(language="ru"))
    real = load_config

    def overtaken() -> Config:
        read = real()
        monkeypatch.setattr(chosen_language_module, "load_config", real)
        writer = threading.Thread(target=save_config, args=(Config(language="en"),))
        writer.start()
        writer.join()
        return read

    monkeypatch.setattr(chosen_language_module, "load_config", overtaken)

    assert chosen_language() == "ru"
    assert chosen_language() == "en", "запись соседа не ждёт окна сверки"
