"""Кто владеет числом в файле настроек: код или человек.

🔴 TC-549. Установка собирает конфиг заново из умолчаний кода, а из прежнего файла
переносит только названное человеком. Прежде полярность была обратной - конфиг
сохранялся, а вычищался поимённый ЧЁРНЫЙ список настроенных чисел, - и всякое поднятое
умолчание приходилось дописывать в тот список руками. Забытое молча жило на старом
числе: ``warm_budget_gb`` в него не попал, и у поставивших продукт раньше бюджет
прогрева остался 20 ГБ против 30 в коде.

Установку тут гоняем в песочнице (``TORRCAST_NO_ROOT``, все каталоги под ``tmp_path``)
и одной фазой ``config``: меряется ровно перекладка настроек, а не установка пакетов.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.config import Config
from torrcast.domain.owned_config_keys import OWNED_BY_HUMAN

REPO = Path(__file__).parents[1]

#: Ключ, который установка обязана взять из config.xml самого Prowlarr, а не из
#: прежнего конфига: его она измеряет, а не помнит.
MEASURED_APIKEY = "apikey-measured-from-prowlarr"


def _install(box: Path, seeded: dict[str, Any] | None = None) -> dict[str, Any]:
    """Прогнать фазу настроек установщика в песочнице и вернуть получившийся конфиг."""
    config_dir, state_dir, bin_dir = box / "etc", box / "var", box / "bin"
    for directory in (config_dir, state_dir, bin_dir, box / "prowlarr-data"):
        directory.mkdir(parents=True, exist_ok=True)
    (box / "prowlarr-data" / "config.xml").write_text(
        f"<Config><ApiKey>{MEASURED_APIKEY}</ApiKey></Config>\n", encoding="utf-8"
    )
    if seeded is not None:
        (config_dir / "config.json").write_text(json.dumps(seeded), encoding="utf-8")
    done = subprocess.run(
        [str(REPO / "install.sh")],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "TORRCAST_PHASES": "config",
            "TORRCAST_NO_ROOT": "1",
            "TORRCAST_NO_SYSTEMD": "1",
            "TORRCAST_PREFIX": str(box),
            "TORRCAST_CONFIG_DIR": str(config_dir),
            "TORRCAST_STATE_DIR": str(state_dir),
            "TORRCAST_BIN_DIR": str(bin_dir),
            "TORRCAST_MOTD": str(box / "motd"),
            "TORRCAST_MOTD_D": str(box / "motd.d"),
        },
    )
    assert done.returncode == 0, done.stdout + done.stderr
    written: Any = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    assert isinstance(written, dict)
    return written


def test_a_reinstall_returns_a_tuned_number_to_the_default_of_the_code(tmp_path: Path) -> None:
    """Число, которого человек не называл, установку не переживает.

    ``warm_budget_gb`` - тот самый забытый ключ: в чёрный список прежней установки он не
    попал, и у поставивших раньше бюджет прогрева оставался 20 ГБ. ``warm_rate`` рядом -
    ровно такой же забытый, и красным он становится по той же причине, а не отдельным
    правилом.
    """
    written = _install(
        tmp_path / "old",
        {
            "tv": "192.0.2.10",
            "warm_budget_gb": 20,
            "warm_rate": 9.0,
            "bitrate_warn_mbit": 20.0,
        },
    )

    assert "warm_budget_gb" not in written
    assert "warm_rate" not in written
    assert "bitrate_warn_mbit" not in written


def test_the_default_the_code_carries_is_what_the_product_then_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Мера - не отсутствие ключа, а число, которое получит сам продукт.

    Пустое место в файле и есть умолчание кода, но проверять надо ответ продукта:
    именно его человек и увидит на прогреве.
    """
    box = tmp_path / "read"
    _install(box, {"tv": "192.0.2.10", "warm_budget_gb": 20})

    monkeypatch.setenv("TORRCAST_CONFIG", str(box / "etc" / "config.json"))

    assert load_config().warm_budget_gb == Config().warm_budget_gb


def test_a_reinstall_keeps_what_the_human_typed_by_hand(tmp_path: Path) -> None:
    """Названное человеком установку переживает: адрес, источники, ключи бота.

    Токен бота человек добыл у BotFather и заново не наберёт, а адреса источников мог
    увести на чужую машину - из кода ни того, ни другого не вывести.
    """
    written = _install(
        tmp_path / "kept",
        {
            "tv": "192.0.2.10",
            "receiver": "mock",
            "receiver_profile": "android_tv",
            "torrserver_url": "http://192.0.2.20:8090",
            "prowlarr_url": "http://192.0.2.20:9696",
            "token": "1234:bot-token",
            "chat_id": "77",
            "proxy": "socks5://127.0.0.1:1080",
            "language": "ru",
        },
    )

    assert written["tv"] == "192.0.2.10"
    assert written["receiver"] == "mock"
    assert written["receiver_profile"] == "android_tv"
    assert written["torrserver_url"] == "http://192.0.2.20:8090"
    assert written["prowlarr_url"] == "http://192.0.2.20:9696"
    assert written["token"] == "1234:bot-token"
    assert written["chat_id"] == "77"
    assert written["proxy"] == "socks5://127.0.0.1:1080"
    assert written["language"] == "ru"


def test_the_apikey_comes_from_prowlarr_itself_not_from_the_old_config(tmp_path: Path) -> None:
    """Ключ Prowlarr в белом списке, но измеренный сейчас правдивее запомненного.

    Prowlarr переставили - ключ у него новый, и конфиг обязан назвать новый.
    """
    written = _install(tmp_path / "apikey", {"tv": "192.0.2.10", "prowlarr_apikey": "stale"})

    assert written["prowlarr_apikey"] == MEASURED_APIKEY


def test_a_reinstall_leaves_the_watch_state_alone(tmp_path: Path) -> None:
    """Выбор озвучки и закладка показа установку переживают.

    Живут они не в конфиге, а в состоянии, и установка каталог состояния только заводит.
    """
    box = tmp_path / "state"
    (box / "var").mkdir(parents=True)
    chosen = {"title": "Моана 2", "magnet": "m", "voice": "Дубляж", "audio": 2}
    state = {"movie:moana-2:2024": chosen}
    (box / "var" / "state.json").write_text(json.dumps(state), encoding="utf-8")

    _install(box, {"tv": "192.0.2.10", "warm_budget_gb": 20})

    assert json.loads((box / "var" / "state.json").read_text(encoding="utf-8")) == state


def test_saving_the_receiver_address_writes_no_threshold_the_human_never_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 TC-669. ``cast --tv`` меняет один адрес и не дописывает чужих чисел.

    Запись всего дата-класса вмораживала в файл каждое умолчание кода. Стоило это
    дважды: установка получала полный чисел файл, из которого их же и вычищала, а след
    (``config_keys``) считал файловым КАЖДЫЙ порог и врал про источник числа.
    """
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))

    save_config(Config(tv="192.0.2.10"))
    written: Any = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))

    assert set(written) == OWNED_BY_HUMAN


def test_a_first_install_writes_the_config_the_code_describes(tmp_path: Path) -> None:
    """Первая установка кладёт конфиг с нуля - и кладёт его закрытым.

    Ветка эта отдельная от повторной, и раньше режим ей давал ``umask`` - он же
    оставался висеть на всей остальной установке. Теперь режим ставится файлу прямо, и
    мерить его надо здесь: без прежнего конфига переносить нечего, и промах виден
    только на первом заходе.
    """
    box = tmp_path / "first"
    written = _install(box)

    assert written["tv"] is None
    assert written["prowlarr_apikey"] == MEASURED_APIKEY
    assert set(written) & set(Config.__dataclass_fields__) - OWNED_BY_HUMAN == {
        "transport",
        "hls_base_url",
        "hls_port",
        "hls_cert",
        "hls_key",
        "hls_dir",
    }
    assert (box / "etc" / "config.json").stat().st_mode & 0o777 == 0o600
