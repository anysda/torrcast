"""Зеркало формы поиска: план круга поиска - контрактный пункт меню с номером ``pick``."""

from __future__ import annotations

from typing import Any, cast

from hass.search_results import search_results
from torrcast.domain.facts.fact import Fact
from torrcast.domain.json_value import JsonValue
from torrcast.domain.kind import Kind
from torrcast.domain.numbered_line import _numbered_line
from torrcast.domain.picture import Picture
from torrcast.usecases.choice.head_line import head_line
from torrcast.usecases.select.plan import Plan


def _plan(title: str, year: int, kind: Kind = "movie", original: str = "") -> Plan:
    return Plan(
        picture=Picture(title=title, year=year, kind=kind, original=original or None),
        ranked=[],
        runtime=0.0,
        warn_mbit=0.0,
    )


def _records(results: list[JsonValue]) -> list[dict[str, Any]]:
    """Записи выдачи под своим видом: договор обещает объекты, а не любой JSON."""
    assert all(isinstance(result, dict) for result in results), "запись выдачи - объект"
    return cast("list[dict[str, Any]]", results)


def test_plans_become_picks_numbered_from_one_in_the_products_own_order(
    _russian_product: None,
) -> None:
    """Оригинальное имя едет полем записи: у части находок русской статьи нет вовсе.

    Пустая строка на его месте - это «продукт про оригинал не знает», и картинку такой
    находке ищут по одному русскому имени.

    Язык назван поимённо: ``named`` собирается каталогом надписей, и на умолчании форма
    записи мерилась бы английской, а читалась как «форма вообще».
    """
    plans = [_plan("Тачки", 2006), _plan("Тачки 2", 2011)]

    assert search_results(plans, 2) == [
        {
            "pick": 1,
            "key": "movie:тачки:2006",
            "title": "Тачки",
            "shown": "Тачки",
            "named": "Тачки (2006)",
            "year": 2006,
            "kind": "movie",
            "original": "",
            "default": False,
        },
        {
            "pick": 2,
            "key": "movie:тачки-2:2011",
            "title": "Тачки 2",
            "shown": "Тачки 2",
            "named": "Тачки 2 (2011)",
            "year": 2011,
            "kind": "movie",
            "original": "",
            "default": True,
        },
    ]


def test_the_name_a_person_reads_is_the_one_the_product_speaks(_english: None) -> None:
    """Подпись находки решает продукт, а не карточка: под EN картину зовут оригиналом.

    Ровно тем же правилом её зовёт меню ``cast`` того же серва
    (:func:`torrcast.domain.spoken_title.spoken_title`). Без готового поля один запрос на
    одном стенде давал человеку две выдачи: карточка звала картину «Назад в будущее»,
    пока меню звало её ``Back to the Future``.
    """
    plans = [_plan("Назад в будущее", 1985, original="Back to the Future")]

    assert _records(search_results(plans, 1))[0]["shown"] == "Back to the Future"


def test_a_picture_without_an_english_name_keeps_its_own(_english: None) -> None:
    """Английского имени нет вовсе - подписью остаётся СОБСТВЕННОЕ имя картины.

    Ни пустоты, ни транслита: выбрать пункт, у которого нет имени, человек не может.
    """
    plans = [_plan("Ёлки", 2010)]

    assert _records(search_results(plans, 1))[0]["shown"] == "Ёлки"


def test_under_russian_the_card_is_answered_in_russian(_russian_product: None) -> None:
    """Другая ветка того же правила: язык продукта русский - и подпись русская."""
    plans = [_plan("Назад в будущее", 1985, original="Back to the Future")]

    assert _records(search_results(plans, 1))[0]["shown"] == "Назад в будущее"


def test_the_raw_name_stays_in_the_record_because_the_poster_is_looked_up_by_it(
    _english: None,
) -> None:
    """Подпись подменять ``title`` не вправе: по нему находке ищут картинку.

    :func:`hass.hit_ask._about` строит по этому полю просьбу о постере, а она спрашивает
    РУССКИЙ раздел Википедии и кладёт найденное на общую с карточкой плеера полку
    (:func:`hass.poster_name.poster_name`). Английское имя в ``title`` увело бы поиск не
    туда, а на полке завело бы вторую запись про ту же картину.
    """
    plans = [_plan("Назад в будущее", 1985, original="Back to the Future")]
    record = _records(search_results(plans, 1))[0]

    assert record["title"] == "Назад в будущее"
    assert record["original"] == "Back to the Future"


def test_a_series_is_called_a_series_in_the_line_and_a_film_is_not(_russian_product: None) -> None:
    """Пометка вида едет готовой строкой: в списке видно, что пункт - сериал.

    Обе стороны названы порознь: у сериала пометка ЕСТЬ, у фильма её НЕТ. Утверждение
    про одну сторону оставляло бы вторую голой - список, помечающий вообще всё, ничем
    не лучше списка, не помечающего ничего.
    """
    plans = [_plan("Чернобыль", 2019, kind="tv"), _plan("Чернобыль", 2021)]
    records = _records(search_results(plans, 1))

    assert records[0]["named"] == "Чернобыль (2019, сериал)"
    assert records[1]["named"] == "Чернобыль (2021)"


def test_the_line_is_the_one_the_console_menu_prints_for_the_same_picture(
    _russian_product: None,
) -> None:
    """Правило одно на оба места: строка записи - строка пункта меню ``cast``.

    Сверяется не с переписанным сюда ожиданием, а с самой
    :func:`~torrcast.usecases.choice.head_line.head_line`, которой меню консоли эту
    строку и печатает: разъедутся - покраснеет тут, а не на стенде у человека.
    Номер с точкой и справка - украшения консоли, их снимает срез.

    Картина под нумерованной линейкой франшизы сверяется отдельно
    (:func:`test_a_picture_under_the_numbered_line_reads_the_same_on_both_sides`): раньше
    консоль подписывала её иначе, чем карточка, и сверка тут была бы не о том.
    """
    plans = [
        _plan("Чернобыль", 2019, kind="tv"),
        _plan("Ёлки", 2010),
        _plan("Назад в будущее", 1985, original="Back to the Future"),
    ]
    records = _records(search_results(plans, 1))

    assert not _numbered_line([plan.picture for plan in plans])[1], "хвоста линейки тут нет"

    for number, (plan, record) in enumerate(zip(plans, records, strict=True), start=1):
        console = head_line(number, plan.picture, Fact())

        assert record["named"] == console.removeprefix(f"  {number}. ")


def test_a_picture_under_the_numbered_line_reads_the_same_on_both_sides(
    _russian_product: None,
) -> None:
    """Картина под линейкой франшизы подписана как все - и одинаково с двух сторон.

    Раскол живой: «Мультачки» стоят ПОД нумерованными «Тачками», и это утверждается,
    а не подразумевается - иначе тест мерил бы обычную картину. Подпись, объяснявшую
    отставание, владелец снял 04-09-2026 из ПРОДУКТА, а не с одной стороны: на «наруто»
    она стояла в консоли на 18 строках из 27, а в карточке, где линейки нет вовсе, на
    20 из 20.

    Красным становятся обе беды сразу. Вернётся подпись в общее правило - разойдётся
    дословная строка консоли; вернётся она только в карточку или только в консоль -
    разойдутся две стороны между собой.
    """
    numbered = [
        Picture(title="Тачки", year=2006, part=1),
        Picture(title="Тачки 2", year=2011, part=2),
    ]
    under = Picture(title="Тачки: Мультачки", year=2008)
    pictures = [*numbered, under]
    plans = [Plan(picture=p, ranked=[], runtime=0.0, warn_mbit=0.0) for p in pictures]
    records = _records(search_results(plans, 1))

    assert [p.key for p in _numbered_line(pictures)[1]] == [under.key], "пункт стоит под линейкой"
    assert head_line(3, under, Fact()) == "  3. Тачки: Мультачки (2008)"

    for number, (picture, record) in enumerate(zip(pictures, records, strict=True), start=1):
        console = head_line(number, picture, Fact())

        assert record["named"] == console.removeprefix(f"  {number}. ")


def test_a_picture_with_no_year_is_dated_the_way_the_console_dates_it(
    _russian_product: None,
) -> None:
    """Года нет - в строке стоит ``(?)``, а не пустота: это различитель тёзок.

    Карточка тут показывала голое имя, консоль - ``(?)``: одна картина, две подписи.
    Года нет у четверти картин корпуса, поэтому расхождение видно не в углу.
    """
    undated = Picture(title="Bleach", year=None, kind="tv")
    plans = [Plan(picture=undated, ranked=[], runtime=0.0, warn_mbit=0.0)]

    assert _records(search_results(plans, 1))[0]["named"] == "Bleach (?, сериал)"


def test_a_russian_only_name_says_so_because_the_line_is_picked_from(_english: None) -> None:
    """Под EN у пункта без английского имени стоит та же пометка, что и в меню консоли.

    Из этого списка ВЫБИРАЮТ, и человек обязан видеть, что имя у пункта одно и оно
    по-русски (:func:`torrcast.usecases.choice._named._named`, ``item=True``).
    """
    plans = [_plan("Ёлки", 2010)]

    assert _records(search_results(plans, 1))[0]["named"] == "Ёлки (2010) - Russian title only"


def test_exactly_one_record_is_flagged_default_and_it_is_the_taken_number() -> None:
    """Поле ``default`` - весь договор с карточкой: она ставит помеченный пункт первым."""
    plans = [_plan("Тачки", 2006), _plan("Тачки 2", 2011), _plan("Тачки 3", 2017)]

    for taken in (1, 2, 3):
        records = _records(search_results(plans, taken))
        flagged = [record["pick"] for record in records if record["default"]]

        assert flagged == [taken], f"взятой обязана быть ровно одна запись, номер {taken}"


def test_an_empty_menu_is_an_empty_list_not_a_refusal() -> None:
    """Отказ - забота круга поиска (:mod:`torrcast.usecases.discover.search_circle`);
    пустой список плана этот шаг не сочиняет и не превращает во что-то другое."""
    assert search_results([], 0) == []
