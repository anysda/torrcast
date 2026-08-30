"""Честная строка вместо дефолта, когда дефолт уходит с картины, названной целиком."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice.alive_numbers import alive_numbers
from torrcast.usecases.choice.asked_kind import asked_kind
from torrcast.usecases.choice.default_note import _passed_why
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.choice.fitness import fitness
from torrcast.usecases.choice.liveliness import liveliness

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def named_elsewhere(plans: list[Plan], asked: str) -> str:
    """Честная строка, когда дефолт уходит с ЦЕЛИКОМ названной картины.

    🔴 TC-715, решение владельца 20-08-2026 - вариант «в»: на запросах «имя названо
    целиком, а дефолт встаёт на другую картину» дефолта нет ВОВСЕ - прибор не берет ни
    точно названную, ни ту, что раздают, а показывает список и ждёт номера. Замер класса
    по корпусу-100: «блич s1e1» (Enter уезжал с «Блича» 2004 на «Тысячелетнюю кровавую
    войну» 2022 - у названного рой 3 сида, ниже порога живости) и «чернобыль s1e5»
    (неправы ОБА ответа: ни верх меню 1991 года, ни первая живая «Зона отчуждения», тогда
    как спрошенное - «Чернобыль» 2019 или 2022).

    🔴 TC-812, решение владельца 26-08-2026: вопрос без дефолта остался только за явным
    ``--menu`` - на обычном пути сработавший страж БЕРЁТ самую живую, и берёт не молча
    (:func:`~torrcast.usecases.choice.named_take.named_take`,
    :func:`~torrcast.usecases.choice.named_taken_line.named_taken_line`). Эта строка
    по-прежнему служит путём вопроса, а условие срабатывания стража живёт здесь и
    зовётся отсюда обоими путями - правило одно, редакция одна.

    Правило «дефолт не вправе уйти с названного имени силой» (вариант «а») НЕ сделано:
    замер показал, что оно исправляет 2 подмены и приводит 2 - «рэмбо» уехал бы с
    «Первой крови» на сериал-тёзку 2022 года, а «кавказская пленница» - на ремейк 2014,
    потому что :func:`slugify` съедает восклицательный знак. Вопрос вместо решения этих
    подмен не приводит: человек видит список и называет номер сам.

    Два стража держат класс узким, и оба проверены замером:

    * номерованная франшиза в меню («рэмбо») - чужая территория: там дефолт - первая
      живая часть (решение владельца), и свой страж уже есть (:func:`part_one_swap`);
    * имя совпало со ВТОРЫМ именем или алиасом самого дефолта («spirited away» - это
      ``also``/``aliases`` у «Унесённых призраками» 2001) - дефолт и есть спрошенная,
      вопроса нет. Без этого стража корпус терял одно из 28 молчаливых взятий.

    Строка называет обе картины и причину, как того требует карточка: умершей названной -
    почему она не играет (три честные ветви :func:`_passed_why`), живой - что дефолтом
    встаёт просто более старая живая одноимённая. Замер по корпусу-100: молчаливых взятий
    (:func:`certain_default`) 28 из 99 и до, и после - строгость не смягчена.
    """
    name, index = split_franchise_index(asked)
    if index is not None or len(plans) < 2:
        return ""
    key = slugify(name)
    if not key:
        return ""
    pictures = [plan.picture for plan in plans]
    films = [p for p in pictures if p.kind != "other"]
    if any(p.part is not None for p in films):
        return ""
    named = [n for n, plan in enumerate(plans, start=1) if key in _slugs(plan.picture)]
    if not named:
        return ""
    default = first_alive(plans)
    if default in named:
        return ""
    numbers = asked_kind(plans)
    chosen = [n for n in named if n in numbers] or named
    whom = ", ".join(phrase("choice.quoted", it=_named(plans[n - 1].picture)) for n in chosen)
    taken = _named(plans[default - 1].picture)
    if why := _unplayable_why(plans, chosen[0], numbers):
        return phrase("choice.named_unplayable", name=name, whom=whom, why=why, taken=taken)
    return phrase("choice.named_not_default", name=name, whom=whom, taken=taken)


def _slugs(picture: Picture) -> set[str]:
    """Все имена картины слагами: название, оригинал, второе имя склейки и алиасы.

    Имя человека сверяется со ВСЕМИ именами картины, а не с одним русским: «cars» и
    «spirited away» зовут те же картины, что и русские названия, и ограждение не вправе
    отключаться от одной смены раскладки.
    """
    return {
        slugify(picture.title),
        slugify(picture.original or ""),
        slugify(picture.also or ""),
    } | set(picture.aliases)


def _unplayable_why(plans: list[Plan], number: int, numbers: list[int]) -> str:
    """Почему названная картина дефолтом стать не могла; пусто - она жива и годна.

    Три честные ветви :func:`_passed_why` (играть нечем, рой мёртв, живого HD нет)
    спрашиваются теми же словами, что и в ней самой. Четвёртая («всего одна раздача»)
    сюда не доходит: названная картина с живым роем и годным HD проиграла не раздачам,
    а хронологии, и причина у неё другая - её называет сама строка.
    """
    plan = plans[number - 1]
    if liveliness(plan) <= 0 or number not in alive_numbers(plans, numbers) or not fitness(plan):
        return _passed_why(plans, number, numbers)
    return ""
