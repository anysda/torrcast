"""Проверяет строку запуска показа: чем поднимается, что пробрасывается, чем метится."""

from __future__ import annotations

import subprocess
import sys

import pytest

from torrcast.adapters.systemd._systemd_call import SystemdCall
from torrcast.adapters.systemd.start_play_unit import start_play_unit
from torrcast.domain.infra_error import InfraError
from torrcast.domain.unit_naming import _PASS_ENV, _UNIT_NAME, _UNIT_TAG


def _answers(seen: list[tuple[str, ...]], code: int = 0) -> SystemdCall:
    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        seen.append((tool, *args))
        return subprocess.CompletedProcess([tool, *args], code, "", "systemd-run: не вышло")

    return call


def test_the_show_is_started_by_the_composition_root_of_the_same_interpreter() -> None:
    """🔴 Юнит поднимает ``-m torrcast.runtime``, а не пакет команд: показу нужны порты.

    Пакет команд разворачивали из модуля в каталог, а строка запуска осталась прежней -
    показ падал «No module named torrcast.cli.__main__», и ни один сухой тест этого не
    видел. Интерпретатор тоже обязан быть тем же самым: юнит не наследует ни venv, ни PATH.
    """
    seen: list[tuple[str, ...]] = []
    start_play_unit("бочи-1", call=_answers(seen))

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
    monkeypatch.setenv(_PASS_ENV[0], "/иное/место")
    for name in _PASS_ENV[1:]:
        monkeypatch.delenv(name, raising=False)
    start_play_unit("ключ", call=_answers(seen))

    passed = [item for item in seen[-1] if item.startswith("--setenv=")]
    assert passed == [f"--setenv={_PASS_ENV[0]}=/иное/место"]


def test_a_previous_show_is_put_out_before_the_new_one_starts() -> None:
    """Прошлый показ гасится ДО запуска нового: два показа в один телевизор не играют.

    Обе операции идут одним и тем же ходом к systemd, поэтому порядок виден целиком, а
    не со слов подделки: сперва ``systemctl stop`` того же юнита, и только потом запуск.
    """
    seen: list[tuple[str, ...]] = []
    start_play_unit("ключ", call=_answers(seen))

    assert [row[0] for row in seen] == ["systemctl", "systemd-run"]
    assert seen[0] == ("systemctl", "stop", _UNIT_NAME)


def test_a_unit_that_did_not_start_is_told_about_out_loud() -> None:
    """Не поднялся юнит - беда наружу словами, а не молчаливый «показ пошёл»."""
    with pytest.raises(InfraError, match=r"unit .* did not start"):
        start_play_unit("ключ", call=_answers([], code=1))
