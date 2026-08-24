"""То же ли имя картины: заголовок против запроса; зовёт гейт добора."""

from __future__ import annotations

import os.path

from torrcast.domain.facts.akin import akin
from torrcast.domain.facts.settings import _NEAR_LETTERS
from torrcast.domain.slugify import slugify
from torrcast.domain.transliterate import transliterate


def same_name(title: str, heading: str) -> bool:
    """То же ли это имя картины: заголовок статьи против того, что назвал человек.

    Сверка тесная нарочно - ею гейт добора решает, можно ли верить имени со справки там,
    где сверить его больше не с чем
    (:func:`~torrcast.usecases.discover._second_language._second_language`). Годится только само
    имя: точное (:func:`akin` знает и другой порядок слов, и слитное написание) либо в другой
    транскрипции - одна буква расхождения, «сальтберн» и «солтберн». Коротким именам и она не
    прощается: у имени из пяти букв одна буква разницы - это уже другое имя («Психо» и «Психи»).

    ⚠️ Одно слово из нескольких сюда НЕ входит, и это вся разница с :func:`_near_name`.
    «Все мы незнакомцы» и «Все мы убийцы» расходятся ровно в одном слове из трёх - и это
    разные картины (2023 и 1952 годов), а не описка.

    🔴 TC-338. Два соседних случая тоже не то же имя, хотя формально близки:

    * **номер части - не описка**: «Крепкий орешек 2» и «Крепкий орешек 3» различаются
      одной буквой-цифрой, и разбор «одна правка по слагу» признавал их одним именем.
      Цифра в имени - это другая часть франшизы, а не неверно нажатая клавиша: расхождение
      единственной цифрой имени не прощается (:func:`_digit_edit`);
    * **часть франшизы - не целое**: на голое «матрица» статья «Матрица: Перезагрузка»
      отвечать не вправе - это одна из частей, а не названное имя. Поэтому :func:`akin`
      зовётся с ``longer=False``: запрос, длиннее заголовка («Властелин колец: Братство
      кольца» против статьи «Властелин колец»), по-прежнему то же имя, а вот заголовок,
      продолжающий запрос частью франшизы, - нет. Угадать такую статью по сходству теперь
      не выйдет уже в :func:`_misremembered`, и до гейта она не доезжает вовсе.
    """
    if akin(title, heading, longer=False):
        return True
    wanted = slugify(title).split("-")
    base_words = slugify(heading.split(" (")[0]).split("-")
    if (
        len(wanted) == len(base_words) + 2
        and wanted[-len(base_words) :] == base_words
        and all(len(word) <= 3 for word in wanted[:2])
    ):
        return True
    name = heading.split(" (")[0]
    # Сверяем однородное с однородным: «Сальтберн» и «Солтберн» расходятся на две буквы
    # («а»/«о» и мягкий знак), а те же имена транслитом - ``saltbern`` и ``soltbern`` -
    # ровно на одну. Мягкий знак имя не различает, и латинская пара это знает.
    for want, base in (
        (slugify(title), slugify(name)),
        (slugify(transliterate(title)), slugify(transliterate(name))),
    ):
        if (
            want
            and base
            and len(want) >= _NEAR_LETTERS
            and _one_edit(want, base)
            and not _digit_edit(want, base)
        ):
            return True
    return False


def _one_edit(one: str, two: str) -> bool:
    """Различаются ли строки не больше чем на одну букву (вставка, пропуск или замена)."""
    if abs(len(one) - len(two)) > 1:
        return False
    short, long = sorted((one, two), key=len)
    head = len(os.path.commonprefix([short, long]))
    if short == long:
        return True
    if len(short) == len(long):
        return short[head + 1 :] == long[head + 1 :]
    return short[head:] == long[head + 1 :]


def _digit_edit(one: str, two: str) -> bool:
    """Единственная разница строк - цифра: номер части («орешек-2»/«орешек-3»), а не описка.

    Зовётся вслед за :func:`_one_edit`, поэтому разница ровно одна и стоит она на первом
    несовпавшем месте. Одна цифра имени - другая часть франшизы, и прощать её как
    неверно нажатую клавишу значило бы пускать «Час пик 3» за «Час пик 2».
    """
    short, long = sorted((one, two), key=len)
    if short == long:
        return False
    head = len(os.path.commonprefix([short, long]))
    if len(short) == len(long):
        return short[head].isdigit() and long[head].isdigit()
    return long[head].isdigit()
