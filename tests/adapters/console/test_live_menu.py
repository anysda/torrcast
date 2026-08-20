"""Зеркало :mod:`torrcast.adapters.console.live_menu`: список на экране и его строка.

Строка переписывается курсором и обязана вернуть его туда, где он стоял: человек в этот
момент набирает ответ. Без терминала не переписывается ничего - управляющие
последовательности в журнале были бы мусором.
"""

from __future__ import annotations

import io
import sys

import pytest

from torrcast.adapters.console.live_menu import LiveMenu

MENU = ["  1. Тачки (2006)", "  2. Тачки 2 (2011)", "  3. Тачки 3 (2017)"]


class Screen(io.StringIO):
    """Поток, который отвечает «я терминал»: другого признака живости у показа нет."""

    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _size(monkeypatch: pytest.MonkeyPatch) -> None:
    """Размер терминала спрашивается у среды - и в зеркале он назван, а не угадан."""
    monkeypatch.setenv("COLUMNS", "40")
    monkeypatch.setenv("LINES", "24")


def test_the_menu_is_printed_at_once_and_without_a_single_control_sequence() -> None:
    """Список печатается обычной печатью: до справки он уже целиком на экране."""
    screen = Screen()

    with LiveMenu(screen) as menu:
        menu.show(MENU)

    assert screen.getvalue() == "\n".join(MENU) + "\n"
    assert "\033" not in screen.getvalue()


def test_a_line_is_rewritten_where_it_stands_and_the_cursor_comes_back() -> None:
    """Курсор запоминается, поднимается на строку пункта и возвращается обратно.

    Три строки меню, переписывается первая: подниматься надо на все три - строка пункта
    плюс те две, что легли под ней.
    """
    screen = Screen()

    with LiveMenu(screen) as menu:
        menu.show(MENU)
        screen.truncate(0), screen.seek(0)
        menu.redraw(0, "  1. Тачки (2006) · IMDb 7.1")

    assert screen.getvalue() == "\0337\033[3A\r  1. Тачки (2006) · IMDb 7.1\033[K\0338"


def test_lines_printed_after_the_menu_are_counted_by_the_menu_itself() -> None:
    """Между списком и курсором ложатся чужие строки, и счёт ведёт сам показ.

    Не считай их - и меню подняло бы курсор на две строки выше нужного, переписав чужой
    текст: строка про Enter и ответ вопроса печатаются не показом, а соседними модулями.
    """
    screen = Screen()

    with LiveMenu(screen) as menu:
        menu.show(MENU)
        print("Enter - «Тачки (2006)», пункт 1 из 3")
        print("нужен номер от 1 до 3")
        screen.truncate(0), screen.seek(0)
        menu.redraw(2, "  3. Тачки 3 (2017) · IMDb 6.7")

    assert screen.getvalue().startswith("\0337\033[3A\r")


def test_the_question_prompt_does_not_move_the_count_because_it_has_no_line_break() -> None:
    """Приглашение вопроса стоит на той же строке экрана, и счёт оно не меняет."""
    screen = Screen()

    with LiveMenu(screen) as menu:
        menu.show(MENU)
        sys.stdout.write("Что смотрим? [1]: ")
        screen.truncate(0), screen.seek(0)
        menu.redraw(2, "  3. Тачки 3 (2017) · IMDb 6.7")

    assert screen.getvalue().startswith("\0337\033[1A\r")


def test_a_line_that_grew_taller_than_it_was_is_not_rewritten_at_all() -> None:
    """Строка, переставшая влезать в ширину, сдвинула бы всё, что под ней.

    Ширина сорок; с украшениями строка перестаёт влезать в одну строку экрана - и такую
    мы не переписываем вовсе: пункт остаётся голым, а список - целым.
    """
    screen = Screen()

    with LiveMenu(screen) as menu:
        menu.show(MENU)
        screen.truncate(0), screen.seek(0)
        menu.redraw(0, "  1. Тачки (2006) · IMDb 7.1 · 1 ч 57 мин")

    assert screen.getvalue() == ""


def test_a_line_that_scrolled_off_the_top_of_the_screen_is_left_alone() -> None:
    """Уехавшую за верх экрана строку не поднять: курсор упрётся и затрёт чужое."""
    screen = Screen()

    with LiveMenu(screen) as menu:
        menu.show([f"  {number}. Ван Пис (1999)" for number in range(1, 36)])
        screen.truncate(0), screen.seek(0)
        menu.redraw(0, "  1. Ван Пис (1999) · IMDb 9.0")
        menu.redraw(34, "  35. Ван Пис (1999) · IMDb 9.0")

    assert screen.getvalue() == "\0337\033[1A\r  35. Ван Пис (1999) · IMDb 9.0\033[K\0338"


def test_without_a_terminal_nothing_is_rewritten_and_the_output_stays_plain() -> None:
    """Без терминала строка уже ушла в поток: переписывать нечего и незачем."""
    plain = io.StringIO()

    with LiveMenu(plain) as menu:
        assert not menu.live
        menu.show(MENU)
        menu.redraw(0, "  1. Тачки (2006) · IMDb 7.1")

    assert plain.getvalue() == "\n".join(MENU) + "\n"
    assert sys.stdout is not plain, "чужой поток без терминала не подменяется"


def test_the_stream_of_the_process_is_given_back_when_the_menu_is_answered() -> None:
    """Меню отвечено - поток вывода возвращается как был, и счёт больше не ведётся."""
    screen = Screen()
    before = sys.stdout

    menu = LiveMenu(screen)
    menu.show(MENU)
    assert sys.stdout is not before, "пока меню на экране, чужая печать считается"
    menu.close()

    assert sys.stdout is before
    screen.truncate(0), screen.seek(0)
    menu.redraw(0, "  1. Тачки (2006) · IMDb 7.1")
    assert screen.getvalue() == "", "закрытое меню не пишет в терминал ничего"
