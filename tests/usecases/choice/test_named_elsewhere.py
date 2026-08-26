"""Зеркало :mod:`torrcast.usecases.choice.named_elsewhere`: дефолта нет, когда он уходит
с картины, чьё имя названо целиком.

🔴 TC-715, решение владельца 20-08-2026 - вариант «в»: на этом классе прибор не берёт
ни точно названную картину, ни ту, что раздают, а показывает список и ждёт номера.
Класс узкий, и оба его стража проверены замером по корпусу-100: номерованная франшиза
(«рэмбо») остаётся на правиле «первая живая часть», а имя, совпавшее со вторым именем
или алиасом самого дефолта («spirited away»), подменой не является вовсе.

🔴 TC-812: вопрос остался за явным ``--menu`` - на обычном пути сработавший страж берёт
самую живую вслух (:mod:`torrcast.usecases.choice.named_take`). Зеркало того пути -
:mod:`tests.usecases.choice.test_named_take`; здесь проверяется строка пути вопроса.
"""

from __future__ import annotations

from tests.usecases.choice.world import parts, plan
from torrcast.usecases.choice.certain_default import certain_default
from torrcast.usecases.choice.named_elsewhere import named_elsewhere


def test_a_dead_exactly_named_picture_stops_the_default_and_names_the_reason() -> None:
    """«блич s1e1»: у названного «Блича» 2004 рой 3 сида - ниже порога живости.

    Дефолт уезжал на «Тысячелетнюю кровавую войну» 2022 года - другой сериал под тем же
    именем. Теперь дефолта нет: строка называет обе картины и причину, номер зовёт
    человек.
    """
    bleach = [
        plan("Блич", 2004, kind="tv", seeders=3, asked_series=True),
        plan("Блич: Тысячелетняя кровавая война", 2022, kind="tv", seeders=40, asked_series=True),
    ]

    assert named_elsewhere(bleach, "блич") == (
        "«блич» - это «Блич (2004, сериал)»; не играет: рой у неё мёртв - сидов 3; "
        "вместо неё другую картину («Блич: Тысячелетняя кровавая война (2022, сериал)») "
        "сам не включаю - вот что есть, назови номер"
    )


def test_alive_namesakes_by_year_are_all_named_and_the_choice_is_the_persons() -> None:
    """«чернобыль s1e5»: спрошенное - «Чернобыль» 2019 или 2022, а неправы оба ответа.

    Названные картины живы - причина не в них, а в том, что дефолтом по хронологии встаёт
    более старая живая одноимённая. Строка обязана назвать обеих тёзок по году, а не
    одну из них.
    """
    chernobyl = [
        plan("Чернобыль: Последнее предупреждение", 1991, seeders=10, asked_series=True),
        plan("Чернобыль. Зона отчуждения", 2014, kind="tv", seeders=60, asked_series=True),
        plan("Чернобыль", 2019, kind="tv", seeders=79, asked_series=True),
        plan("Чернобыль", 2022, kind="tv", seeders=50, asked_series=True),
    ]

    assert named_elsewhere(chernobyl, "чернобыль") == (
        "«чернобыль» - это «Чернобыль (2019, сериал)», «Чернобыль (2022, сериал)», "
        "а дефолтом встаёт другая картина - «Чернобыль. Зона отчуждения (2014, сериал)» "
        "(первая живая по хронологии); какую из них смотреть, сам не решаю - "
        "вот что есть, назови номер"
    )


def test_a_numbered_franchise_stays_on_the_first_live_part_rule() -> None:
    """«рэмбо»: сериал-тёзка «РэмбО» 2022 назван целиком, но это территория франшизы.

    Там дефолт - первая живая часть (решение владельца), и свой страж у неё уже есть
    (:func:`part_one_swap`). Вопрос без дефолта здесь отнял бы молчаливое взятие
    «Первой крови» - ровно ту строгость, которую карточка велит держать.
    """
    rambo = [
        plan("Рэмбо: Первая кровь", 1982, part=1, seeders=74),
        plan("Рэмбо 2", 1985, part=2, seeders=50),
        plan("РэмбО", 2022, kind="tv", seeders=2),
    ]

    assert named_elsewhere(rambo, "рэмбо") == ""


def test_a_name_matched_by_the_default_itself_is_no_substitution() -> None:
    """«spirited away» - второе имя самого дефолта: спрошенная картина и взята.

    Без сверки оригинала, второго имени и алиасов ограждение отключалось бы от одной
    смены раскладки - и корпус терял молчаливое взятие «Унесённых призраками» 2001.
    """
    spirited = [
        plan("Унесённые призраками", 2001, original="Spirited Away", seeders=120),
        plan("Унесённые призраками: движущиеся картинки", 2011, seeders=10),
    ]

    assert named_elsewhere(spirited, "spirited away") == ""


def test_the_exactly_named_default_needs_no_question() -> None:
    """Дефолт и есть целиком названная картина - подмены нет, и строки нет."""
    mummy = parts(("Мумия", 1999, 58), ("Мумия", 2017, 47))

    assert named_elsewhere(mummy, "мумия") == ""


def test_a_part_named_by_its_number_changes_nothing() -> None:
    """Номер назван явно - спрошенное уже отобрано до меню, спрашивать не о чём."""
    bleach = [
        plan("Блич", 2004, kind="tv", seeders=3, asked_series=True),
        plan("Блич: Тысячелетняя кровавая война", 2022, kind="tv", seeders=40, asked_series=True),
    ]

    assert named_elsewhere(bleach, "блич 2") == ""


def test_a_menu_of_one_picture_was_never_this_choice() -> None:
    """Картина одна - дефолту не с кого уходить, и вопроса тут не было вовсе."""
    assert named_elsewhere([plan("Блич", 2004, kind="tv", seeders=3)], "блич") == ""


def test_the_silent_take_is_not_softened_by_this_guard() -> None:
    """Молчаливое взятие не стало мягче: названная целиком соседка его отменяет.

    Верх меню жив и стоит первым - прежние строки молчат, и прежде дефолт брался молча.
    Но запрос назвал целиком ДРУГУЮ картину меню - и молча брать здесь подмена.
    """
    plans = [
        plan("Чернобыль. Зона отчуждения", 2014, kind="tv", seeders=60),
        plan("Чернобыль", 2019, kind="tv", seeders=79),
    ]

    assert named_elsewhere(plans, "чернобыль") != ""
    assert not certain_default(plans, "чернобыль")
