"""Зеркало :mod:`torrcast.domain.digest._show_line`: куски, план и всё, что мешало играть."""

from __future__ import annotations

from tests.domain.digest.rows import rec
from torrcast.domain.digest._show_line import _show_line
from torrcast.domain.trace_sources import WARMED

STAMP = "+   0.0с "


def test_an_event_of_another_phase_is_not_this_readers_business() -> None:
    """``None`` - «не моё событие»; пустая строка - «моё, и печатать его не надо»."""
    assert _show_line(rec("evict"), STAMP, False) is None
    assert _show_line(rec("segment", slot=1, src=WARMED), STAMP, False) == ""


def test_only_the_seam_of_a_segment_gets_printed_and_the_source_is_named_in_russian() -> None:
    """Кусков сотни - печатается смена источника, и зовётся она по-русски, а не кодом поля."""
    told = _show_line(rec("segment", slot=7, src=WARMED), STAMP, True)

    assert told is not None
    assert "v7: источник сменился на прогретое" in told
    assert WARMED not in told


def test_the_plan_says_how_both_producers_encode() -> None:
    """Решение о кодировании - строка ленты, а не разбор аргументов ffmpeg постфактум."""
    told = _show_line(rec("plan", pack="copy", warm="recode", spots=5), STAMP, False)

    assert told is not None
    assert "упаковка - копия, прогрев - перекод, точечный перекод 5" in told


def test_a_plan_without_spot_recodes_says_nothing_about_them() -> None:
    """Ноль точечных перекодов - не новость, и хвоста строки он не заслуживает."""
    told = _show_line(rec("plan", pack="copy", warm="copy", spots=0), STAMP, False)

    assert told is not None
    assert "точечный перекод" not in told


def test_the_asked_source_is_called_a_source_and_not_the_network() -> None:
    """Служба ответила (или не ответила) нам сама - «сеть» тут была бы догадкой."""
    asked = _show_line(rec("offline", asked=True, why="TorrServer молчит"), STAMP, False)
    network = _show_line(rec("offline", why="обрыв"), STAMP, False)

    assert asked is not None and asked.startswith(f"{STAMP}источник: ")
    assert network is not None and network.startswith(f"{STAMP}сеть: ")


def test_a_seek_without_a_picture_is_a_separate_outcome_and_not_a_zero_wait() -> None:
    """Картинки не было вовсе - это исход, а не нулевое ожидание.

    Нулём его печатала как раз старая метрика, верившая слову приёмника, - и перемотка «в
    никуда» была неотличима от мгновенной.
    """
    quick = _show_line(rec("seek", frm=10.0, to=600.0, wait=1.5), STAMP, False)
    never = _show_line(
        rec("seek", frm=10.0, to=600.0, wait=None, why="приёмник молчит"), STAMP, False
    )

    assert quick is not None and "картинка через 1.5 с" in quick
    assert never is not None and "картинки так и не было: приёмник молчит" in never


def test_a_reload_tells_a_missing_code_apart_from_no_code_at_all() -> None:
    """Поля нет - молчим; поле есть и пустое - так и сказано: это разные новости."""
    coded = _show_line(rec("reload", pos=60.0, tries=2, error=7), STAMP, False)
    blank = _show_line(rec("reload", pos=60.0, tries=2, error=None), STAMP, False)
    silent = _show_line(rec("reload", pos=60.0, tries=1), STAMP, False)

    assert coded is not None and ", код 7" in coded
    assert blank is not None and ", без кода" in blank
    assert silent is not None and "код" not in silent


def test_a_show_that_never_gave_a_frame_is_not_called_extinguished_at_zero() -> None:
    """«Погас на 0:00:00» и «не дал ни кадра» - две разные аварии, и поле ``shown``
    их разделяет: первую человек успел посмотреть, вторая - «включил и не включилось»."""
    dark = _show_line(rec("dark", pos=1272.4, why="приёмник молчит", shown=True), STAMP, False)
    never = _show_line(rec("dark", pos=0.0, why="приёмник молчит", shown=False), STAMP, False)

    assert dark is not None and "показ погас на 21:12: приёмник молчит" in dark
    assert never is not None and "показ не дал ни кадра: приёмник молчит" in never
    assert "погас" not in never


def test_an_old_dark_record_without_the_field_is_an_extinguished_show() -> None:
    """Записи прежних версий поля ``shown`` не несут - все они про погасший показ."""
    told = _show_line(rec("dark", pos=1272.4, why="приёмник молчит"), STAMP, False)

    assert told is not None and "показ погас на 21:12" in told
