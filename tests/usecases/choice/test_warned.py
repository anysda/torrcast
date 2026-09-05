"""Зеркало :mod:`torrcast.usecases.choice.warned`: почему релиз не дефолт.

Пометка обязана говорить ровно то, что сделает показ: обещай она отказ там, где показ
состоится, - человек обошёл бы стороной живое; обещай показ там, где его не будет, -
выбрал бы чёрный экран.
"""

from __future__ import annotations

import pytest

from tests.usecases.choice.world import RUNTIME, film
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.recodes_whole import recodes_whole
from torrcast.usecases.choice.warned import warned

WARN_MBIT = 16.0
RECODE_AT_MBIT = 10.0
HARD_MBIT = 25.0

#: Как кодек зовётся в имени раздачи для каждого ключа, которым его зовёт профиль.
_NAMED: dict[str, str] = {"hevc": "HEVC", "mpeg4": "MPEG-4"}


@pytest.mark.parametrize("key", sorted(CAUTIOUS.recode_codecs))
def test_every_codec_the_show_recodes_whole_is_marked_and_not_only_hevc(key: str) -> None:
    """Пометку решает ТОТ ЖЕ набор кодеков, что и показ, а не отдельная проверка на HEVC.

    Проверка на один кодек стояла тут и знала HEVC, а набор приёмника с TC-299 шире:
    mpeg4 показ тоже берёт сплошным перекодом, и на такой раздаче таблица молчала. Человек
    читал пустую графу, а на запуске получал самую дорогую часть пути - ту, о которой
    строка обязана предупредить до ответа, а не после.
    """
    assert recodes_whole(key, 0, CAUTIOUS), "кодек взят из набора самого приёмника"
    assert key in _NAMED, f"набор приёмника вырос на {key}: назови его словом имени раздачи"

    light = film("Кино 2020 DVDRip", codec=_NAMED[key], size_gb=1.4)

    assert warned(light, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == phrase(
        "choice.mark_recode_all"
    )
    assert warned(light, RUNTIME, WARN_MBIT) == phrase("choice.mark_not_taken")


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

    assert said == ", ".join([phrase("choice.mark_recode_all"), phrase("choice.mark_heavy")])


def test_the_codec_is_named_before_the_weight_because_it_costs_the_most() -> None:
    """Порядок пометок не случаен: сперва то, что решает про весь путь показа."""
    heavy_hevc = film("Кино 2020 BDRemux HEVC 1080p", codec="HEVC", size_gb=18.0)

    said = warned(heavy_hevc, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT)

    assert said.split(", ") == [
        phrase("choice.mark_recode_all"),
        phrase("choice.mark_heavy"),
    ]


def test_only_one_weight_mark_is_said_and_it_is_the_worst_of_them() -> None:
    """Пометки по весу друг друга исключают: тяжёлый релиз не «ещё и перекодируем».

    Скажи строка обе - человек читал бы обещание перекода там, где показа не будет
    вовсе, и решал бы по младшей из двух бед.
    """
    heavy = film("Кино 2020 BDRemux 1080p", size_gb=18.0)

    assert warned(heavy, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == phrase(
        "choice.mark_heavy"
    )


def test_the_ceiling_is_the_last_allowed_value_and_not_the_first_forbidden_one() -> None:
    """Потолок назван «выше этого», и ровно на нём релиз ещё чист.

    Сдвинь черту на включающую - и таблица начала бы ругать «тяжёлым» ровно ту раздачу,
    которую приёмник берёт без единого ребуфера.
    """
    at_ceiling = film("Кино 2020 BDRemux 1080p", size_gb=WARN_MBIT * RUNTIME / 8000.0)

    assert warned(at_ceiling, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == phrase(
        "choice.mark_recode_parts"
    )


def test_a_light_release_says_nothing_so_that_a_real_warning_is_not_lost_in_noise() -> None:
    """Лёгкому релизу сказать нечего, и молчание тут - правильный ответ."""
    assert warned(film(size_gb=6.0), RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == ""
