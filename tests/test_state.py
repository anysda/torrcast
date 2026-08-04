"""Тесты состояния: атомарная запись, порог «досмотрено», сброс по --new."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from torrcast.state import Entry, State, load_config, save_config


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Не трогать /var/lib/torrcast и /etc/torrcast из тестов."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))


def test_roundtrip_creates_parent_dirs_and_keeps_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Состояние переживает запись и чтение, кириллица не экранируется."""
    nested = tmp_path / "var" / "lib" / "torrcast" / "state.json"
    monkeypatch.setenv("TORRCAST_STATE", str(nested))

    state = State()
    entry = Entry(title="Матрица", magnet="magnet:?xt=1", pos=2467, dur=8160)
    state.put("movie:матрица:1999", entry)
    state.save()

    assert "Матрица" in nested.read_text(encoding="utf-8")
    reloaded = State.load().get("movie:матрица:1999")
    assert reloaded is not None
    assert reloaded.pos == 2467
    assert reloaded.updated  # метку времени ставит put()


def test_watched_threshold_is_95_percent() -> None:
    """Позиция ≥ 95 % длительности = досмотрено → следующая серия (§2.4 ТЗ)."""
    assert not Entry(title="x", magnet="m", pos=940, dur=1000).watched
    assert Entry(title="x", magnet="m", pos=950, dur=1000).watched


def test_drop_forgets_entry() -> None:
    """`--new` сбрасывает запись и проходит выбор с нуля (§4 ТЗ)."""
    state = State()
    state.put("movie:тачки:2006", Entry(title="Тачки", magnet="m"))
    state.drop("movie:тачки:2006")

    assert state.get("movie:тачки:2006") is None


def test_missing_state_file_is_empty_not_error() -> None:
    """Отсутствующий файл состояния — не ошибка."""
    assert not State.load().entries


def test_config_requires_only_tv() -> None:
    """Конфиг переживает roundtrip; остальные поля имеют рабочие дефолты (§5 ТЗ)."""
    config = load_config()
    assert config.tv is None

    config.tv = "192.168.100.102"
    save_config(config)

    reloaded = load_config()
    assert reloaded.tv == "192.168.100.102"
    assert reloaded.torrserver_url.endswith(":8090")


def test_unknown_keys_in_state_are_ignored(tmp_path: Path) -> None:
    """Незнакомые поля из будущих версий не роняют чтение."""
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"movie:x:2000": {"title": "X", "magnet": "m", "totally_new": 1}}),
        encoding="utf-8",
    )

    entry = State.load().get("movie:x:2000")

    assert entry is not None
    assert entry.title == "X"
