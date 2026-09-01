"""Проверяет, что «почему нет картинки» отвечает последняя строка журнала показа."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import torrcast.adapters.launchd.job_why as job_why_module
from torrcast.adapters.launchd.job_why import job_why
from torrcast.domain.unit_naming import _UNIT_NAME


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Журнал задания на время теста живёт в его личном каталоге, а не в общем."""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path / f"{_UNIT_NAME}.log"


def test_the_last_word_is_taken_from_the_log_of_the_show(log: Path) -> None:
    """🔴 Отбирать свои строки по автору, как у systemd, не нужно: в файле только показ.

    journald на macOS нет - оба потока задания пишутся в этот файл, и последняя
    непустая его строка и есть ответ человеку у консоли.
    """
    log.write_text("рой молчит про раздачу\nкартинки не было ни разу\n\n", encoding="utf-8")
    assert job_why() == "картинки не было ни разу"


def test_a_log_without_lines_says_so_instead_of_inventing_a_reason(log: Path) -> None:
    """Своих строк нет - так и говорим; отсутствие файла - тот же ответ, а не авария."""
    assert job_why() == "the log is empty"
    log.write_text("", encoding="utf-8")
    assert job_why() == "the log is empty"


def test_a_very_long_line_is_cut_before_it_reaches_the_console(log: Path) -> None:
    """Наружу уходит строка, а не портянка: трейсбек в консоли человеку не ответ."""
    log.write_text("я" * 500, encoding="utf-8")
    assert job_why() == "я" * 160


def test_only_the_tail_of_a_long_log_is_read(log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """За долгий показ журнал растёт, а нужна одна строка - файл читается с хвоста."""
    monkeypatch.setattr(job_why_module, "_TAIL", 60)
    log.write_text("старая строка, не нужная ответу\nкартинки не было ни разу\n", encoding="utf-8")
    assert job_why() == "картинки не было ни разу"


def test_a_cut_line_is_not_an_answer(log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Срез хвоста пришёлся на середину единственной строки - ответа нет, а не обрубок.

    Обрезанная посередине utf-8 строка - битые знаки вместо причины; честный ответ про
    такую строку - «в журнале пусто».
    """
    monkeypatch.setattr(job_why_module, "_TAIL", 20)
    log.write_text("причина, не влезшая в хвост целиком\n", encoding="utf-8")
    assert job_why() == "the log is empty"


def test_an_unreadable_log_cannot_kill_the_answer_about_the_job(log: Path) -> None:
    """Отказ чтения журнала сам становится причиной, а не обрывает команду."""
    log.mkdir()  # каталог вместо файла: чтение отказывает
    assert job_why().startswith("reason unavailable:")
