"""Проверки закрытого файла настройки Telegram."""

import json
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from tgbot.config import CONFIG_ENV, Config

#: Ключи показа в том же файле: их мастер настройки не знает и знать не должен.
PRODUCT_KEYS = {
    "tv": "10.0.0.50",
    "receiver": "chromecast",
    "prowlarr_url": "http://127.0.0.1:9696",
    "prowlarr_apikey": "ключ",
    "torrserver_url": "http://127.0.0.1:8090",
    "transport": "http",
    "hls_port": 8080,
    "hls_dir": "/dev/shm/torrcast",
    "warm": True,
    "language": "ru",
}


def test_path_is_overridden_and_saved_with_mode_0600(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    path = tmp_path / "telegram.json"
    monkeypatch.setenv(CONFIG_ENV, str(path))
    Config("token", "-100", "http://proxy:80").save()
    assert Config.load() == Config("token", "-100", "http://proxy:80")
    assert path.stat().st_mode & 0o777 == 0o600
    assert Config.remove()
    assert not path.exists()


def test_the_bot_writer_leaves_the_keys_of_the_product_alone(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """🔴 Файл общий: запись своего дата-класса целиком стирала настройку показа."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps(PRODUCT_KEYS, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(path))

    Config("token", "-100", "").save()

    written = json.loads(path.read_text(encoding="utf-8"))
    assert {key: written.get(key) for key in PRODUCT_KEYS} == PRODUCT_KEYS
    assert written["token"] == "token"


def test_removing_the_bot_settings_keeps_the_keys_of_the_product(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Снятие бота уносит три своих ключа, а не общий файл целиком."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({**PRODUCT_KEYS, "token": "token", "chat_id": "-100"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_ENV, str(path))

    assert Config.remove()

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written == PRODUCT_KEYS


def test_a_broken_file_stops_the_bot_write_instead_of_wiping_the_neighbour(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Разобрать чужие ключи нечем, поэтому запись отказывается, а не пишет поверх."""
    path = tmp_path / "config.json"
    path.write_text('{"tv": "10.0.0.50", ', encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(path))

    with pytest.raises(ValueError):
        Config("token", "-100", "").save()

    assert path.read_text(encoding="utf-8") == '{"tv": "10.0.0.50", '
