"""Зеркало :mod:`torrcast.domain.host_health`."""

import pytest

from torrcast.domain.ffmpeg_pace import FfmpegPace
from torrcast.domain.host_health import HostHealth


@pytest.fixture(autouse=True)
def _russian_lines(_russian_product: None) -> None:
    """Предмет модуля - русское словоблюдие самопроверки, поэтому язык назван вслух.

    Умолчание продукта английское (:mod:`torrcast.domain.catalogs.tongue`), и без этой
    строки набор мерил бы английские надписи, а рассказывал бы про русские.
    """


def test_a_missing_terminal_is_a_warning_not_a_failure() -> None:
    """Не интерактивный запуск - это законный режим: вопросы возьмут дефолты."""
    line, ok = HostHealth.terminal(False, None)
    assert ok and line.startswith("внимание"), line
    assert "дефолты" in line


def test_an_unreadable_input_mode_says_so_instead_of_lying() -> None:
    """Режим ввода не прочитался - кириллица не проверена, а не «работает»."""
    line, ok = HostHealth.terminal(True, None)
    assert ok and "не проверена" in line, line


def test_the_switch_of_iutf8_is_visible_in_the_line() -> None:
    """Человек должен видеть, включили мы режим сами или он уже стоял."""
    assert "уже включён" in HostHealth.terminal(True, True)[0]
    assert "включаем сами" in HostHealth.terminal(True, False)[0]


def test_a_non_utf8_locale_is_a_failure() -> None:
    """Русские названия побьются при записи в файл - это «плохо»."""
    line, ok = HostHealth.locale("koi8-r", "LANG=ru_RU.KOI8-R")
    assert not ok and "не UTF-8" in line, line
    assert "LANG=ru_RU.KOI8-R" in line


def test_a_utf8_locale_passes_by_encoding_or_by_environment() -> None:
    """Достаточно одного признака: кодировки процесса либо переменных окружения."""
    assert HostHealth.locale("utf-8", "")[1]
    assert HostHealth.locale("ansi_x3.4-1968", "LC_ALL=ru_RU.UTF-8")[1]


def test_an_empty_locale_still_prints_something_readable() -> None:
    """Пустая кодировка и пустое окружение не должны давать пустую строку."""
    assert "пусто" in HostHealth.locale("", "")[0]


#: Честный темп: все три числа далеко внутри допуска (margin 3 с сверх базовой линии).
_HONEST = FfmpegPace(baseline_seconds=0.1, burst_seconds=0.1, entry_seconds=0.1)


def test_ffmpeg_with_an_inert_burst_flag_is_a_failure() -> None:
    """TC-1048. ffmpeg 8.0.1 печатает -readrate_initial_burst в справке, но флаг инертен -
    burst у него стоит почти столько же, сколько чтение без темпа вовсе.
    """
    inert = FfmpegPace(baseline_seconds=0.1, burst_seconds=7.7, entry_seconds=0.1)
    line, ok = HostHealth.ffmpeg(inert, "ffmpeg version 8.0.1")
    assert not ok and "-readrate_initial_burst инертен" in line, line
    assert line.startswith("плохо   ffmpeg version 8.0.1")


def test_ffmpeg_pacing_from_the_start_of_the_file_is_a_failure() -> None:
    """TC-1048. Burst честен, но посадка -ss вглубь файла всё равно ждёт с начала -
    именно это вешает перемотку намертво на боевой команде.
    """
    from_start = FfmpegPace(baseline_seconds=0.1, burst_seconds=0.1, entry_seconds=11.5)
    line, ok = HostHealth.ffmpeg(from_start, "ffmpeg version 8.0.1")
    assert not ok and "темп считается от начала файла" in line, line


def test_a_missing_ffmpeg_is_a_failure_without_a_version() -> None:
    """Программа не запускается - паковать поток нечем, версии тут неоткуда взяться."""
    line, ok = HostHealth.ffmpeg(None, None)
    assert not ok and "не запускается" in line, line


def test_a_nameless_version_is_replaced_by_the_program_name() -> None:
    """Версия молчит - в строке всё равно должно стоять имя программы."""
    assert HostHealth.ffmpeg(_HONEST, None)[0].startswith("ок      ffmpeg,")


def test_a_long_version_line_is_cut_to_sixty_characters() -> None:
    """Первая строка ffmpeg длинная: в вердикте от неё нужен только заголовок."""
    line, ok = HostHealth.ffmpeg(_HONEST, "f" * 200)
    assert ok and "f" * 60 in line and "f" * 61 not in line
