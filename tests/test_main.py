"""Зеркало точки входа моста: порт, юнит и все места, где пакет обязан быть назван."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from hass.main import PORT_ENV, _port
from hass.serve import PORT

REPO = Path(__file__).parents[1]
INSTALL = (REPO / "install.sh").read_text(encoding="utf-8")
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


def _body(name: str) -> str:
    return INSTALL.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]


def test_the_port_is_the_agreed_one_unless_the_environment_says_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PORT_ENV, raising=False)
    assert _port() == PORT == 8479

    monkeypatch.setenv(PORT_ENV, "18479")
    assert _port() == 18479

    # Мусор в переменной не повод не подняться вовсе: порт остаётся договорным.
    monkeypatch.setenv(PORT_ENV, "восемь")
    assert _port() == PORT


def test_the_bridge_unit_runs_the_same_way_the_bot_unit_does() -> None:
    bridge = _body("setup_ha_unit")
    bot = _body("setup_bot_unit")

    assert 'write_unit torrcast-ha "мост torrcast для Home Assistant"' in bridge
    assert '"$PREFIX/venv/bin/torrcast-ha"' in bridge
    # 🔴 Хозяин у обоих юнитов один, и это не совпадение: файл-пульт общий, и разойдись
    # они по пользователям - слово моста легло бы туда, куда показ не смотрит.
    # Хозяина не задаёт ни один из них: write_unit не пишет User=, то есть оба идут от root.
    assert "User=" not in _body("write_unit")
    assert "User=" not in bridge and "User=" not in bot
    # Включается сразу: мастера у моста нет и настраивать в нём нечего.
    assert "systemctl enable --now torrcast-ha.service" in bridge
    # Но не вслепую: юнита на диске нет - включать нечего. Живьём эту ветку меряет
    # стадия `installer language contract`, ставящая установщик без прав на /etc/systemd.
    assert "[ -f /etc/systemd/system/torrcast-ha.service ] || return 0" in bridge
    assert "setup_bot_unit; setup_ha_unit;" in INSTALL


def test_the_package_is_named_in_every_list_that_ships_it() -> None:
    assert PYPROJECT["project"]["scripts"]["torrcast-ha"] == "hass.main:main"
    assert "hass" in PYPROJECT["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "hass" in PYPROJECT["tool"]["mypy"]["files"]
    assert "hass" in PYPROJECT["tool"]["ruff"]["lint"]["isort"]["known-first-party"]
    # Сторож раскладки обязан мерить мост наравне с ботом: пакет вне его охвата растёт
    # без длины, без зеркал и без слоёв.
    gate = (REPO / "scripts" / "structure_gate.py").read_text(encoding="utf-8")
    assert '(root / "hass").rglob("*.py")' in gate
    # Тарбол собирается белым списком: забыть тут - молча.
    assert '"$src/hass"' in (REPO / "scripts" / "release.sh").read_text(encoding="utf-8")
