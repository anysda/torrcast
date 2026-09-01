"""Проверяет задание запуска показа: что пишется в plist, что пробрасывается, чем метится."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from torrcast.adapters.launchd._launchd_call import LaunchdCall
from torrcast.adapters.launchd.start_play_job import start_play_job
from torrcast.domain.infra_error import InfraError
from torrcast.domain.unit_naming import _JOB_KEY_ENV, _PASS_ENV, _UNIT_NAME


def _answers(seen: list[tuple[str, ...]], code: int = 0) -> LaunchdCall:
    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        seen.append((tool, *args))
        return subprocess.CompletedProcess([tool, *args], code, "", "bootstrap: не вышло")

    return call


@pytest.fixture
def files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Файлы задания на время теста живут в его личном каталоге, а не в общем."""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(os, "geteuid", lambda: 502)
    return tmp_path


def _plist(files: Path) -> dict[str, object]:
    return dict(plistlib.loads((files / f"{_UNIT_NAME}.plist").read_bytes()))


def test_the_show_is_started_by_the_composition_root_of_the_same_interpreter(
    files: Path,
) -> None:
    """🔴 Задание поднимает ``-m torrcast.runtime``, а не пакет команд: показу нужны порты.

    Интерпретатор обязан быть тем же самым: задание не наследует ни venv, ни PATH.
    """
    seen: list[tuple[str, ...]] = []
    start_play_job("бочи-1", call=_answers(seen))

    plist = _plist(files)
    assert plist["Label"] == _UNIT_NAME
    assert plist["ProgramArguments"] == [
        sys.executable,
        "-m",
        "torrcast.runtime",
        "--play-key",
        "бочи-1",
    ], "задание поднимает не корень композиции"
    assert plist["RunAtLoad"] is True, "показ поднимается сразу с регистрацией"


def test_the_handles_of_this_run_and_the_key_are_passed_into_the_job(
    files: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ручки прогона переезжают в задание: иначе оно возьмёт прод-пути вместо нынешних.

    Пробрасывается ровно перечисленное (:data:`_PASS_ENV`) и только заданное: пустая
    ручка перебила бы умолчание пустой строкой. Ключ показа едет окружением - по нему
    ``status`` узнаёт, что играет (описания, где его держит systemd, у launchd нет).
    """
    monkeypatch.setenv(_PASS_ENV[0], "/иное/место")
    for name in _PASS_ENV[1:]:
        monkeypatch.delenv(name, raising=False)
    start_play_job("бочи-1", call=_answers([]))

    env = _plist(files)["EnvironmentVariables"]
    assert env == {_PASS_ENV[0]: "/иное/место", _JOB_KEY_ENV: "бочи-1"}


def test_a_previous_show_is_put_out_before_the_new_one_starts(files: Path) -> None:
    """Прошлый показ гасится ДО запуска нового: два показа в один телевизор не играют.

    Обе операции идут одним и тем же ходом к launchd, поэтому порядок виден целиком, а
    не со слов подделки: сперва ``bootout`` того же задания, и только потом запуск.
    Регистрация прошлого задания переживает его процесс, и без выгрузки повторный
    ``bootstrap`` отвечает ошибкой 5.
    """
    seen: list[tuple[str, ...]] = []
    start_play_job("ключ", call=_answers(seen))

    assert [row[1] for row in seen] == ["bootout", "bootstrap"]
    assert seen[0] == ("launchctl", "bootout", f"gui/502/{_UNIT_NAME}")
    assert seen[1] == ("launchctl", "bootstrap", "gui/502", str(files / f"{_UNIT_NAME}.plist"))


def test_the_log_of_the_previous_show_does_not_speak_for_the_new_one(files: Path) -> None:
    """Журнал стирается перед стартом: строки прошлого показа - не причина молчания нового."""
    log = files / f"{_UNIT_NAME}.log"
    log.write_text("прошлый показ молчал\n", encoding="utf-8")
    start_play_job("ключ", call=_answers([]))

    assert not log.exists()
    plist = _plist(files)
    assert plist["StandardOutPath"] == str(log)
    assert plist["StandardErrorPath"] == str(log), "журнал один, как journald у systemd"


def test_a_probe_can_raise_its_own_long_command(files: Path) -> None:
    """Щуп поднимает свою долгую команду под своей меткой, а не чужой показ."""
    start_play_job("ключ", "torrcast.проба", call=_answers([]), program=["/bin/sleep", "600"])

    plist = dict(plistlib.loads((files / "torrcast.проба.plist").read_bytes()))
    assert plist["Label"] == "torrcast.проба"
    assert plist["ProgramArguments"] == ["/bin/sleep", "600"]


def test_a_job_that_did_not_start_is_told_about_out_loud(files: Path) -> None:
    """Не поднялось задание - беда наружу словами, а не молчаливый «показ пошёл»."""
    with pytest.raises(InfraError, match=r"job .* did not start"):
        start_play_job("ключ", call=_answers([], code=5))
