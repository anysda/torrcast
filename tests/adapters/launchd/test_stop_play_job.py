"""Проверяет, что погашение показа выгружает задание, терпит его отсутствие и убирает plist."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from torrcast.adapters.launchd._launchd_call import LaunchdCall
from torrcast.adapters.launchd.stop_play_job import stop_play_job
from torrcast.domain.unit_naming import _UNIT_NAME


def _remember(seen: list[tuple[str, ...]], code: int = 0) -> LaunchdCall:
    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        seen.append((tool, *args))
        return subprocess.CompletedProcess([tool, *args], code, "", "")

    return call


@pytest.fixture
def plist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Файлы задания на время теста живут в его личном каталоге, а не в общем."""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(os, "geteuid", lambda: 502)
    return tmp_path / f"{_UNIT_NAME}.plist"


def test_stopping_the_show_boots_the_job_out(plist: Path) -> None:
    """``bootout`` и гасит процесс, и снимает регистрацию - аналога ``--collect`` нет.

    Замени ``bootout`` на ``kill``, и регистрация осталась бы лежать до перезагрузки,
    не пуская следующий показ (повторный ``bootstrap`` отвечает ошибкой 5).
    """
    seen: list[tuple[str, ...]] = []
    stop_play_job(call=_remember(seen))

    assert seen == [("launchctl", "bootout", f"gui/502/{_UNIT_NAME}")]


def test_a_job_that_is_not_there_is_not_an_error(plist: Path) -> None:
    """``cast stop`` без показа обязан молча кончиться: код 3 - «нет процесса»."""
    stop_play_job(call=_remember([], code=3))


def test_the_plist_does_not_outlive_its_job(plist: Path) -> None:
    """Задание транзитное: его файл стирается на гашении, журнал остаётся для why()."""
    plist.write_bytes(b"plist")
    stop_play_job(call=_remember([]))

    assert not plist.exists()


def test_the_unit_name_can_be_named_from_outside(plist: Path) -> None:
    """Метка задания - аргумент с умолчанием: щупы гасят своё задание, а не показ человека."""
    seen: list[tuple[str, ...]] = []
    stop_play_job("torrcast.проба", call=_remember(seen))

    assert seen == [("launchctl", "bootout", "gui/502/torrcast.проба")]
