"""Зеркало :mod:`torrcast.usecases.choice.warned`: почему релиз не дефолт.

Пометка обязана говорить ровно то, что сделает показ: обещай она отказ там, где показ
состоится, - человек обошёл бы стороной живое; обещай показ там, где его не будет, -
выбрал бы чёрный экран.
"""

from __future__ import annotations

from tests.usecases.choice.world import RUNTIME, film
from torrcast.usecases.choice.warned import warned

WARN_MBIT = 16.0
RECODE_AT_MBIT = 10.0
HARD_MBIT = 25.0


def test_the_marks_are_words_and_carry_no_signs_that_fall_apart_in_a_terminal() -> None:
    """Словами, а не значками: ``⚠`` из вывода убран целиком.

    Смысла в терминале он не нёс, а по ширине разъезжался - и таблица меню переставала
    быть таблицей на первом же узком окне.
    """
    heavy_hevc = film("Кино 2020 BDRemux HEVC 1080p", codec="HEVC", size_gb=18.0)

    said = warned(heavy_hevc, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT)

    assert "⚠" not in said and "!" not in said


def test_two_different_troubles_are_both_named_and_not_swallowed_by_each_other() -> None:
    """Кодек и вес - разные беды, и говорятся они обе, через запятую.

    Оставь строка одну - человек, прочитавший «тяжёлый», не узнал бы про сплошной
    перекод, то есть про самую дорогую часть пути.
    """
    heavy_hevc = film("Кино 2020 BDRemux HEVC 1080p", codec="HEVC", size_gb=18.0)

    said = warned(heavy_hevc, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT)

    assert said == "перекодирую целиком, тяжёлый"


def test_the_codec_is_named_before_the_weight_because_it_costs_the_most() -> None:
    """Порядок пометок не случаен: сперва то, что решает про весь путь показа."""
    heavy_hevc = film("Кино 2020 BDRemux HEVC 1080p", codec="HEVC", size_gb=18.0)

    said = warned(heavy_hevc, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT)

    assert said.split(", ") == ["перекодирую целиком", "тяжёлый"]


def test_only_one_weight_mark_is_said_and_it_is_the_worst_of_them() -> None:
    """Пометки по весу друг друга исключают: тяжёлый релиз не «ещё и перекодируем».

    Скажи строка обе - человек читал бы обещание перекода там, где показа не будет
    вовсе, и решал бы по младшей из двух бед.
    """
    heavy = film("Кино 2020 BDRemux 1080p", size_gb=18.0)

    assert warned(heavy, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == "тяжёлый"


def test_the_ceiling_is_the_last_allowed_value_and_not_the_first_forbidden_one() -> None:
    """Потолок назван «выше этого», и ровно на нём релиз ещё чист.

    Сдвинь черту на включающую - и таблица начала бы ругать «тяжёлым» ровно ту раздачу,
    которую приёмник берёт без единого ребуфера.
    """
    at_ceiling = film("Кино 2020 BDRemux 1080p", size_gb=WARN_MBIT * RUNTIME / 8000.0)

    assert warned(at_ceiling, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == "перекодируем"


def test_a_light_release_says_nothing_so_that_a_real_warning_is_not_lost_in_noise() -> None:
    """Лёгкому релизу сказать нечего, и молчание тут - правильный ответ."""
    assert warned(film(size_gb=6.0), RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == ""
