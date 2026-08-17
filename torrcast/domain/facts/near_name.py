"""Почти то же имя: сверка последнего шага справки; зовёт разбор описки."""

from __future__ import annotations

from torrcast.domain.facts.same_name import same_name
from torrcast.domain.facts.settings import _ODD_WEIGHT, _PHRASE_WORDS
from torrcast.domain.same_word import same_word
from torrcast.domain.slugify import slugify
from torrcast.domain.transliterate import transliterate


def _near_name(title: str, heading: str) -> bool:
    """Почти то же имя: одна буква расхождения либо одно слово, которое имя перевешивает.

    Сверка последнего шага (:func:`_misremembered`), и она нарочно тесная - подсказки
    Википедии на «Сальтберн» приносят и «Сальтерас», и «Сальтенья», и «Салитерник, Цви».

    * **то же имя** (:func:`same_name`) - в том числе в другой транскрипции;
    * **одно слово** - имя из трёх и более слов, в котором ровно одно стоит не то:
      «мужчина который удивил всех» против «человек который удивил всех». Слов должно быть
      поровну и на своих местах: перестановки и пропуски сюда не входят, а само расхождение
      обязано перевесить совпавшим (:func:`_outweighed`).

    ⚠️ Второе послабление всё равно доказывает меньше первого: перевесить умеет и соседняя
    часть франшизы («Планета обезьян: Война» против «Планета обезьян: Революция»). Отсюда
    отметка :attr:`Origin.guessed` - имя, найденное этой сверкой, гейту добора не
    доказательство.
    """
    if same_name(title, heading):
        return True
    name = heading.split(" (")[0]
    for want, base in (
        (slugify(title), slugify(name)),
        (slugify(transliterate(title)), slugify(transliterate(name))),
    ):
        if not want or not base:
            continue
        mine, theirs = want.split("-"), base.split("-")
        if len(mine) >= _PHRASE_WORDS and len(mine) == len(theirs):
            odd = [
                spot
                for spot, (one, two) in enumerate(zip(mine, theirs, strict=True))
                if not same_word(one, two)
            ]
            if not odd or (len(odd) == 1 and _outweighed(mine, theirs, odd[0])):
                return True
    return False


def _outweighed(mine: list[str], theirs: list[str], spot: int) -> bool:
    """Перевешивает ли совпавшая часть имени то единственное слово, что разошлось.

    🔴 TC-284. Одного слова из трёх мало само по себе: так расходятся и описка, и разные
    картины. Считаем БУКВАМИ, а не словами - разница между двумя случаями в том, сколько
    имени осталось стоять за совпадением:

    * «мужчина который удивил всех» и «Человек, который удивил всех» - совпало «который
      удивил всех», семнадцать букв против семи; спорит одно слово, а имя держат три;
    * «Все мы незнакомцы» и «Все мы убийцы» - совпало «Все мы», пять букв против десяти.
      Совпало тут ровно то, чем подсказчик Википедии искал (общее начало), и картину это
      не называет вовсе: под «Все мы» лежит что угодно.

    Мерка сверялась на 36 парах имён (описки, другие переводы, соседние части франшиз,
    однофамильцы): по одному слову из трёх проходили все 18 чужих картин, с этим весом -
    пять, и ни одна верная пара не потерялась.
    """
    kept = sum(len(word) for place, word in enumerate(mine) if place != spot)
    return kept >= _ODD_WEIGHT * max(len(mine[spot]), len(theirs[spot]))
