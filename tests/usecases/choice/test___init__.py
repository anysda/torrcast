"""Зеркало :mod:`torrcast.usecases.choice`: чем сценарий выбора мерит и объясняет картины.

Меню, подмены и порядок вопросов сторожит большой набор CLI. Здесь - две вещи, которые
решает сам сценарий: чем он ВЕСИТ картину, выбирая дефолт, и той строкой, которой таблица
объясняет, почему релиз не дефолт. Строка обязана говорить ровно то, что сделает показ:
обещай она отказ там, где показ состоится, - человек обошёл бы стороной живое, а обещай
показ там, где его не будет, - выбрал бы чёрный экран.

Веса тут настоящие: раздачу взвешивает то же ранжирование, что и на живом запуске, поэтому
вес задаётся размером раздачи и длительностью картины, а не подсунутым числом. Правила
отбора и порог живости тоже настоящие: сценарий спрашивает их у собранного окружения, того
же, что и на живом запуске.
"""

from __future__ import annotations

from typing import Any

from torrcast.domain.picture import Picture
from torrcast.domain.rank_settings import ALIVE_SEEDERS
from torrcast.domain.release import Release
from torrcast.usecases.choice import fitness, liveliness, warned
from torrcast.usecases.select import _Plan

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


def picture_of(*releases: Release) -> _Plan:
    """План по одной картине: пул раздач и та же длительность, что и во взвешивании."""
    return _Plan(
        picture=Picture(title="Кино", year=2020),
        ranked=list(releases),
        runtime=RUNTIME,
        warn_mbit=WARN_MBIT,
    )


def test_a_picture_is_worth_nothing_when_its_only_release_has_no_swarm_behind_it() -> None:
    """«Стоит смотреть» требует ЖИВОЙ раздачи, а не просто годной по правилам отбора.

    Обе мерки картины считают сиды годных раздач, и различает их ровно порог живости.
    Раздача под порогом годна по правилам, но играть ею нечем: рой не отдаст куски. Пропусти
    такую в вес - и дефолт меню садился бы на картину, у которой показ обречён, вместо
    соседней с живым роем: человек нажимал бы Enter в чёрный экран.
    """
    dying = picture_of(film(6, seeders=ALIVE_SEEDERS - 1))

    assert liveliness(dying) == ALIVE_SEEDERS - 1, "годность правилам отбора мерка видит"
    assert fitness(dying) == 0, "а смотреть картину нечем: живой раздачи у неё нет"


def test_a_release_exactly_at_the_liveliness_threshold_counts_as_alive() -> None:
    """Порог живости включающий: ровно на нём раздача ещё живая, а не «почти».

    Число одно на весь инструмент, и второго значения у слова «живая» тут нет: тем же
    порогом считает живые картины :func:`alive_numbers`. Сделай сравнение строгим - и
    картина ровно на пороге пропадала бы из меню у одной мерки и оставалась у другой.
    """
    at_threshold = picture_of(film(6, seeders=ALIVE_SEEDERS))

    assert fitness(at_threshold) == ALIVE_SEEDERS


def test_the_weight_of_a_picture_is_its_liveliest_release_and_not_the_top_of_the_queue() -> None:
    """Вес картины берётся у САМОЙ ЖИВОЙ годной раздачи, а не у первой в очереди.

    Очередь сортируется не сидами: наверху стоит то, что лучше СМОТРЕТЬ. Считай вес по
    верху - и картина с 22 раздачами весила бы пятью сидами своего верха при 97 у годного
    соседа ниже, то есть проигрывала бы однораздачной тёзке (живой случай «Мальтийского
    сокола»). Мёртвый сосед при этом вес не тянет: он в счёт не идёт вовсе.
    """
    queue = picture_of(
        film(6, seeders=ALIVE_SEEDERS),
        film(7, seeders=97),
        film(6, seeders=ALIVE_SEEDERS - 1),
    )

    assert fitness(queue) == 97


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


def test_a_release_sitting_exactly_on_a_line_is_still_on_the_good_side_of_it() -> None:
    """Потолок и планка - это последнее ДОПУСТИМОЕ значение, а не первое запрещённое.

    Обе черты названы «выше этого», и ровно на черте релиз ещё чист: потолок приёмника -
    то, что он тянет, а планка перекода - то, что уезжает копией. Сдвинь любую из них на
    включающую - и таблица начала бы ругать ровно ту раздачу, которая играет как надо:
    сперва предупреждением о перекоде там, где его не будет, а потом и «тяжёлый» на том,
    что приёмник берёт без единого ребуфера.
    """
    at_ceiling = film(14.4)
    at_recode_line = film(9)

    assert warned(at_ceiling, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) != "тяжёлый"
    assert warned(at_recode_line, RUNTIME, WARN_MBIT, RECODE_AT_MBIT, HARD_MBIT) == ""


def test_above_the_lower_of_the_two_ceilings_the_whole_file_is_promised_to_be_recoded() -> None:
    """Когда потолок сплошного перекода НИЖЕ практического, он и решает - и это не отказ.

    У высокого кадра потолком становится меньшая из двух черт (``min(warn, hard)``): такой
    релиз приёмник копией не тянет, но сплошной перекод его спасает. Назови его «тяжёлым» -
    и человек обошёл бы стороной то, что играет; промолчи - и он ждал бы копию там, где
    уедет перекод. Ровно на черте файл ещё копийный, поэтому обещания перекода на ней нет.
    """
    above = warned(film(18), RUNTIME, warn_mbit=25.0, recode_at=10.0, hard_mbit=16.0)
    at_line = warned(film(14.4), RUNTIME, warn_mbit=25.0, recode_at=10.0, hard_mbit=16.0)

    assert above == "перекодирую целиком"
    assert at_line == "перекодируем", "ровно на черте сплошного перекода ещё нет"


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
