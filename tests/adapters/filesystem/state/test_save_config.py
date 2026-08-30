"""Запись настроек: файл появляется вместе с каталогом и читается обратно тем же."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.config import Config
from torrcast.domain.torrcast_error import TorrcastError

#: Ключи телеграм-бота в общем файле. Значения выдуманы: боевому токену в наборе не место.
BOT_KEYS = {"token": "1:проба", "chat_id": "-100", "proxy": "socks5://127.0.0.1:1080"}


def test_what_was_saved_is_what_is_read_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Запись и чтение - одна раскладка: разойдись они, настройка молча теряется."""
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))

    save_config(Config(tv="10.0.0.50"))

    assert load_config().tv == "10.0.0.50"


def test_the_directory_is_made_on_the_way_because_the_first_run_has_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Первичная настройка идёт до того, как каталог настроек кто-либо завёл."""
    path = tmp_path / "ещё-нет" / "config.json"
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))

    save_config(Config(tv="10.0.0.50"))

    assert path.exists()


def test_the_product_writer_leaves_the_keys_of_the_telegram_bot_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """🔴 Файл общий: своя запись целиком уносила боевой токен бота (TC-934)."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**BOT_KEYS, "tv": "10.0.0.1"}), encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))

    save_config(Config(tv="10.0.0.50"))

    written = json.loads(path.read_text(encoding="utf-8"))
    assert {key: written.get(key) for key in BOT_KEYS} == BOT_KEYS
    assert written["tv"] == "10.0.0.50"


def test_a_broken_file_stops_the_write_instead_of_wiping_the_neighbour(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Разобрать чужие ключи в битом файле нечем, поэтому запись отказывается словом."""
    path = tmp_path / "config.json"
    path.write_text('{"token": "1:проба", ', encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))

    with pytest.raises(TorrcastError, match="broken config"):
        save_config(Config(tv="10.0.0.50"))

    assert path.read_text(encoding="utf-8") == '{"token": "1:проба", '


def test_nothing_temporary_is_left_next_to_the_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Запись атомарная, но мусор после себя она оставлять не имеет права."""
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))

    save_config(Config(tv="10.0.0.50"))

    assert [path.name for path in tmp_path.iterdir()] == ["config.json"]
