"""Проверяет строку запуска показа: чем поднимается, что пробрасывается, чем метится."""

from __future__ import annotations

import subprocess
import sys

import pytest

from torrcast.adapters.systemd import start_play_unit as module
from torrcast.domain.infra_error import InfraError
from torrcast.domain.unit_naming import _PASS_ENV, _UNIT_NAME, _UNIT_TAG


def _answers(seen: list[tuple[str, ...]], code: int = 0) -> object:
    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        seen.append((tool, *args))
        return subprocess.CompletedProcess([tool, *args], code, "", "systemd-run: не вышло")

    return call


def test_the_show_is_started_by_the_composition_root_of_the_same_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Юнит поднимает ``-m torrcast.runtime``, а не пакет команд: показу нужны порты.

    Пакет команд разворачивали из модуля в каталог, а строка запуска осталась прежней -
    показ падал «No module named torrcast.cli.__main__», и ни один сухой тест этого не
    видел. Интерпретатор тоже обязан быть тем же самым: юнит не наследует ни venv, ни PATH.
    """
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(module, "_systemd", _answers(seen))
    module.start_play_unit("бочи-1")

    argv = list(seen[-1])
    assert argv[0] == "systemd-run"
    assert argv[argv.index("-m") + 1] == "torrcast.runtime", "юнит поднимает не корень композиции"
    assert sys.executable in argv, "юнит обязан идти тем же интерпретатором"
    assert f"--unit={_UNIT_NAME}" in argv and "--collect" in argv
    assert f"--description={_UNIT_TAG}бочи-1" in argv, "по описанию ищут ключ играющего показа"
    assert argv[-2:] == ["--play-key", "бочи-1"]


def test_the_handles_of_this_run_are_passed_into_the_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ручки прогона переезжают в юнит: иначе он возьмёт прод-пути вместо нынешних.

    Пробрасывается ровно перечисленное (:data:`_PASS_ENV`) и только заданное: пустая
    ручка в ``--setenv`` перебила бы умолчание пустой строкой.
    """
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(module, "_systemd", _answers(seen))
    monkeypatch.setenv(_PASS_ENV[0], "/иное/место")
    for name in _PASS_ENV[1:]:
        monkeypatch.delenv(name, raising=False)
    module.start_play_unit("ключ")

    passed = [item for item in seen[-1] if item.startswith("--setenv=")]
    assert passed == [f"--setenv={_PASS_ENV[0]}=/иное/место"]


def test_a_previous_show_is_put_out_before_the_new_one_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Прошлый показ гасится ДО запуска нового: два показа в один телевизор не играют."""
    order: list[str] = []

    def put_out(unit: str = "") -> None:
        order.append("гасим")

    def run(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        order.append(tool)
        return subprocess.CompletedProcess([tool, *args], 0, "", "")

    monkeypatch.setattr(module, "stop_play_unit", put_out)
    monkeypatch.setattr(module, "_systemd", run)
    module.start_play_unit("ключ")

    assert order == ["гасим", "systemd-run"]


def test_a_unit_that_did_not_start_is_told_about_out_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """Не поднялся юнит - беда наружу словами, а не молчаливый «показ пошёл»."""
    monkeypatch.setattr(module, "_systemd", _answers([], code=1))
    with pytest.raises(InfraError, match="не запустился юнит"):
        module.start_play_unit("ключ")
