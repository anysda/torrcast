"""Зеркало :mod:`torrcast.usecases.choice`: чем сценарий выбора объясняется человеку.

Отбор дефолта, меню и подмены сторожит большой набор CLI. Здесь - та строка, которой
таблица объясняет, почему релиз не дефолт. Строка обязана говорить ровно то, что сделает
показ: обещай она отказ там, где показ состоится, - человек обошёл бы стороной живое, а
обещай показ там, где его не будет, - выбрал бы чёрный экран.

Веса тут настоящие: раздачу взвешивает то же ранжирование, что и на живом запуске, поэтому
вес задаётся размером раздачи и длительностью картины, а не подсунутым числом.
"""

from __future__ import annotations

from typing import Any

from torrcast.domain.release import Release
from torrcast.usecases.choice import warned

#: Десятичный гигабайт: в них считают размер раздачи и трекеры, и наша прикидка веса.
GB = 1000**3

#: Два часа фильма - в них пересчитывается размер раздачи, когда её взвешивают.
RUNTIME = 7200.0

#: Практический потолок приёмника, планка перекода куска и потолок отбора.
WARN_MBIT = 16.0
RECODE_AT_MBIT = 10.0
HARD_MBIT = 25.0


def film(gigabytes: float, **fields: Any) -> Release:
    """Фильм одной раздачей: в двух часах её размер и даёт тот самый вес в Мбит/с."""
    return Release(
        raw_name="Кино 2020 1080p",
        title="Кино",
        quality="1080p",
        size=int(gigabytes * GB),
        **fields,
    )


def test_a_light_release_is_not_marked_at_all() -> None:
    """Лёгкому релизу сказать нечего, и молчание тут - правильный ответ.

    Появись у него пометка - таблица предупреждала бы обо всём подряд, и настоящее
    предупреждение потерялось бы среди шума.
    """
    assert warned(film(6), RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == ""


def test_a_release_over_the_receivers_ceiling_is_called_heavy() -> None:
    """Вес выше практического потолка приёмника - это «тяжёлый», и человек это видит.

    Порог тут не украшение: на таком весе приёмник встаёт в ребуфер раз в 30-60 секунд, и
    каждый подвис стоит секунд пропущенного фильма.
    """
    assert warned(film(18), RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == "тяжёлый"


def test_a_release_over_the_recode_line_promises_a_recode_and_not_a_refusal() -> None:
    """Между планкой перекода и потолком приёмника релиз играбелен, и это не брак.

    Тяжёлые куски поедут перекодированными - честное предупреждение, а не отказ. Назови
    таблица такой релиз тяжёлым - человек обошёл бы стороной то, что прекрасно играет.
    """
    assert warned(film(10), RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == "перекодируем"


def test_hevc_is_named_by_what_the_show_will_actually_do_with_it() -> None:
    """«Не берём» осталось правдой ровно там, где перекодирование выключено.

    С включённым перекодом такой релиз играет, перекодированный целиком, и таблица обязана
    говорить то же, что и показ. Иначе человек видит отказ там, где показ бы состоялся.
    """
    hevc = film(6, codec="HEVC")

    assert warned(hevc, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == "перекодирую целиком"
    assert warned(hevc, RUNTIME, WARN_MBIT) == "не берём"


def test_an_unknown_weight_produces_no_weight_marks_at_all() -> None:
    """«Не знаю» и «лёгкий» - разные ответы, и вторым первый притворяться не смеет.

    Имя раздачи молчит о числе серий - вес одной серии посчитать не из чего: «9 ГБ» на
    восемь серий это единицы Мбит/с, а не десятки. Сочти молчание нулём - и такие раздачи
    получали бы пометку по выдуманному числу, а врать тут нечем.
    """
    silent = Release(raw_name="Сериал S01", title="Сериал", kind="tv", season=1, size=9 * GB)

    assert warned(silent, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == ""


def test_an_unknown_weight_still_leaves_the_codec_mark_in_place() -> None:
    """Молчание весов гасит пометки по весу, но не то, что известно из имени.

    Кодек в имени назван, и решение о сплошном перекоде принимается по нему: потеряй
    строка эту пометку - человек не узнал бы о самой дорогой части пути.
    """
    silent_hevc = Release(
        raw_name="Сериал S01 HEVC",
        title="Сериал",
        kind="tv",
        season=1,
        codec="HEVC",
        size=9 * GB,
    )

    said = warned(silent_hevc, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT)

    assert said == "перекодирую целиком"
