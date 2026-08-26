"""Зеркало :mod:`torrcast.usecases.choice._pick_plan`: вопрос «Что смотрим?».

Дефолт - та картина, о которой говорят честные строки про смену (:func:`first_alive`),
и цифра в скобках имеет смысл ровно потому, что рядом напечатан список и человек видит,
от чего отказывается.
"""

from __future__ import annotations

import pytest

from tests.usecases.choice.world import Outside, Waited, film, parts, plan
from torrcast.domain.not_found_error import NotFoundError
from torrcast.usecases.choice._pick_plan import _pick_plan
from torrcast.usecases.choice.swap_note import swap_note

VHS = film("Cars 2006 DVDRip XviD", seeders=100, codec="XviD", quality=None)


def test_the_menu_is_printed_before_the_question_so_the_number_has_a_meaning() -> None:
    """Список печатается всегда, а последней строкой идёт то, что случится по Enter.

    Строка стоит именно ПЕРЕД вопросом: терминал после длинного вывода показывает его
    хвост, и шапка длинного меню уезжает за экран вместе с ним. Спросить тут есть о
    чём: верх меню - мёртвая документалка с другим именем, и дефолт прошёл мимо неё.
    """
    world = Outside()
    moana = parts(
        ("Моана: романтика золотого века", 1926, 1), ("Моана", 2016, 222), ("Моана 2", 2024, 140)
    )

    picked = _pick_plan(moana, asked="моана", environment=world)

    assert world.said[0].splitlines() == [
        "  1. Моана: романтика золотого века (1926)",
        "  2. Моана (2016)",
        "  3. Моана 2 (2024)",
    ]
    assert world.said[1] == "Enter - «Моана (2016)», пункт 2 из 3"
    assert world.asked == [("Что смотрим?", 3, 2)]
    assert picked is moana[1], "пустой Enter - это дефолт"


def test_the_number_the_person_answered_is_the_picture_that_goes_on() -> None:
    """Ответ номером - это выбор человека, и он исполняется буквально."""
    world = Outside(answers=[1])
    moana = parts(
        ("Моана: романтика золотого века", 1926, 1), ("Моана", 2016, 222), ("Моана 2", 2024, 140)
    )

    assert _pick_plan(moana, asked="моана", environment=world) is moana[0]


def test_namesakes_by_year_are_taken_liveliest_without_a_question() -> None:
    """🔴 TC-812. Тёзки по году больше не спрашивают: берётся самая живая, и не молча.

    Решение владельца 26-08-2026: «включать самую живую это показатель того что картина
    популярна а варианты будут уже за --menu». Строка называет взятую годом, число
    остальных и ключ; список не печатается - отвечать на него больше не просят.
    """
    world = Outside()
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    picked = _pick_plan(mummy, asked="мумия", environment=world)

    assert picked is mummy[1], "самая живая из одноимённых"
    assert world.asked == [], "вопроса не было"
    assert world.said == [
        "беру «Мумия (2017)» - самая живая из одноимённых, у лучшей её раздачи сидов 58; "
        "других картин под этим именем: 1, их список: cast мумия --menu"
    ]


def test_namesakes_need_no_terminal_either() -> None:
    """Вопроса на тёзках нет - значит и терминал не нужен: берётся и в трубе, и в cron."""
    world = Outside(tty=False)
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    assert _pick_plan(mummy, asked="мумия", environment=world) is mummy[1]
    assert world.asked == []


def test_a_single_picture_is_no_choice_and_the_question_is_not_asked() -> None:
    """Одна картина - спрашивать не о чем, а меню всё равно печатается."""
    world = Outside()
    single = parts(("Мумия", 1999, 47))

    assert _pick_plan(single, environment=world) is single[0]
    assert world.asked == []


def test_the_only_picture_found_being_another_part_of_the_franchise_is_refused() -> None:
    """🔴 TC-814. Одна картина, и она чужая часть - отказ, а не молчаливый показ.

    `cast лёд` включал «Лёд 3» 2024 года, ни словом об этом не сказав: меню при одной
    картине не задаётся, и страж перескока сюда не доходил.
    """
    world = Outside()
    ice = [plan("Лёд 3", 2024, part=3, seeders=3)]

    with pytest.raises(NotFoundError) as refusal:
        _pick_plan(ice, asked="лёд", environment=world)

    assert "первой части в выдаче нет" in str(refusal.value)
    assert "«Лёд 3 (2024)»" in str(refusal.value)
    assert world.asked == [], "выбирать было не из чего, и вопроса тут нет"


def test_the_menu_flag_passes_ahead_of_the_lone_other_part_refusal() -> None:
    """🔴 TC-812. ``--menu`` пропускается вперёд отказа: список поднимается и из одного пункта.

    «лёд» нашёл только «Лёд 3» - без флага это отказ (молча такое не включаем), а с
    флагом человек просил список: строка про чужую часть печатается над ним, и ответ
    называет сам человек.
    """
    world = Outside(answers=[1])
    ice = [plan("Лёд 3", 2024, part=3, seeders=3)]

    picked = _pick_plan(ice, asked="лёд", environment=world, menu=True)

    assert picked is ice[0]
    assert world.said[0].startswith("«лёд»: первой части в выдаче нет"), "отказ стал строкой"
    assert world.said[1].splitlines() == ["  1. Лёд 3 (2024)"]
    assert world.asked == [("Что смотрим?", 1, 1)]


def test_a_single_picture_of_the_asked_franchise_still_goes_on_without_a_word() -> None:
    """Номер назван самим человеком - найденное и есть спрошенное, показ идёт молча."""
    world = Outside()
    ice = [plan("Лёд 3", 2024, part=3, seeders=3)]

    assert _pick_plan(ice, asked="лёд 3", environment=world) is ice[0]
    assert world.asked == []


def test_a_number_named_by_the_flag_replaces_the_question_and_not_the_choice() -> None:
    """``--pick N`` - названный человеком выбор, тот же номер, что стоит у пункта меню.

    Вопрос тогда не задаётся вовсе, и терминал не нужен: молчаливой подмены тут не
    бывает - номер назвал сам человек по списку на экране.
    """
    world = Outside(tty=False)
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    assert _pick_plan(mummy, pick=2, environment=world) is mummy[1]
    assert world.asked == []
    assert world.said[0].splitlines()[1] == "  2. Мумия (2017)", "список всё равно на экране"


def test_the_flag_number_is_checked_against_the_table_it_came_from() -> None:
    """Номер из ``cast releases`` адресует ТУ картину, что стояла под ним в таблице.

    Состав выдачи гуляет от захода к заходу: под тем же номером сегодня может стоять
    другая картина. Сверка с запомненной таблицей пропускает только совпадение, и
    картина проговаривается вслух - номер молчит.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))
    world = Outside(tty=False, pinned=(mummy[1].picture.key, "Мумия (2017)"))

    assert _pick_plan(mummy, pick=2, asked="мумия", environment=world) is mummy[1]
    assert world.said[-1] == "играю «Мумия (2017)» - пункт 2, названный флагом --pick"


def test_a_flag_number_pointing_at_another_picture_is_a_refusal_not_a_show() -> None:
    """Под номером сейчас ДРУГАЯ картина - отказ, называющий обе, а не молчаливый показ.

    В таблице «мумия» под двойкой стояла «Мумия (1999)», а в новой выдаче под ней
    «Мумия (2017)»: сыграть её - значит подменить кино без единой строки.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))
    world = Outside(tty=False, pinned=(mummy[0].picture.key, "Мумия (1999)"))

    with pytest.raises(NotFoundError) as refusal:
        _pick_plan(mummy, pick=2, asked="мумия", environment=world)

    said = str(refusal.value)
    assert "«Мумия (1999)»" in said and "«Мумия (2017)»" in said
    assert "cast releases мумия" in said
    assert world.asked == [], "вопроса не было - был отказ"


def test_a_flag_number_without_a_remembered_table_is_taken_as_named() -> None:
    """Таблицы этого запроса не было - сверять не с чем, номер берётся как назван."""
    world = Outside(tty=False)
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    assert _pick_plan(mummy, pick=2, asked="мумия", environment=world) is mummy[1]


def test_the_printed_menu_remembers_its_order_for_the_next_run() -> None:
    """Меню запоминает свой порядок тем же словом, что и таблица ``cast releases``.

    Номер пункта человек видит и в меню: выйти и назвать его флагом ``--pick N`` в
    следующем запуске - тот же ход, что и по таблице, и сверяться он обязан так же.
    """
    world = Outside()
    moana = parts(
        ("Моана: романтика золотого века", 1926, 1), ("Моана", 2016, 222), ("Моана 2", 2024, 140)
    )

    _pick_plan(moana, asked="моана", environment=world)

    assert world.remembered == [
        (
            "моана",
            [
                (moana[0].picture.key, "Моана: романтика золотого века (1926)"),
                (moana[1].picture.key, "Моана (2016)"),
                (moana[2].picture.key, "Моана 2 (2024)"),
            ],
        )
    ]


def test_the_list_shown_for_a_flag_number_is_remembered_too() -> None:
    """Список под ``--pick N`` - тоже показанный список: его порядок запоминается."""
    world = Outside(tty=False)
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    _pick_plan(mummy, pick=2, asked="мумия", environment=world)

    assert [query for query, _shown_rows in world.remembered] == ["мумия"]


def test_a_refused_flag_number_remembers_nothing() -> None:
    """Отказ стоит до показа списка: порядку, которого человек не видел, в памяти нечего."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))
    world = Outside(tty=False, pinned=(mummy[0].picture.key, "Мумия (1999)"))

    with pytest.raises(NotFoundError):
        _pick_plan(mummy, pick=2, asked="мумия", environment=world)

    assert world.remembered == []


def test_a_number_outside_the_list_is_an_honest_error_and_not_a_quiet_first_item() -> None:
    """Номера нет в списке - честная ошибка: тихо взять первый пункт значило бы подменить кино."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    with pytest.raises(NotFoundError, match="подходит картин: 2, номера 5 нет"):
        _pick_plan(mummy, pick=5, environment=Outside())


def test_without_a_terminal_we_refuse_out_loud_and_say_how_to_name_the_picture() -> None:
    """🔴 Спрашивать есть о чём, а терминала нет - отказываемся вслух.

    Дефолт прошёл мимо верха меню (мёртвая документалка с другим именем), и цифра в
    скобках имеет смысл ровно потому, что рядом напечатан список и человек видит, от
    чего отказывается; без терминала видеть его некому.
    """
    world = Outside(tty=False)
    moana = parts(
        ("Моана: романтика золотого века", 1926, 1), ("Моана", 2016, 222), ("Моана 2", 2024, 140)
    )

    with pytest.raises(NotFoundError) as refusal:
        _pick_plan(moana, asked="моана", environment=world)

    said = str(refusal.value)
    assert "терминала нет - вслепую не выбираю" in said
    assert "«Моана»" in said and "--pick N" in said
    assert world.asked == [], "спрашивать было некого, и висеть мы не стали"


def test_a_default_that_would_swap_a_part_of_the_franchise_is_taken_away_entirely() -> None:
    """🔴 TC-373. Дефолта нет вовсе: строка про первую часть, а номер называет человек.

    Вопрос задаётся БЕЗ дефолта - пустой Enter тут не ответ: он включил бы «Тачки 2»
    вместо просимых «Тачек», то есть ровно ту подмену, о которой строка и говорит.
    """
    world = Outside(answers=[3])
    cars = [
        plan("Тачки", 2006, part=1, pool=[VHS]),
        plan("Тачки 2", 2011, part=2, seeders=40),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]

    picked = _pick_plan(cars, asked="тачки", environment=world)

    assert world.said[1].startswith("«Тачки (2006)» не играет")
    assert world.asked == [("Что смотрим?", 3, None)], "дефолта у вопроса нет"
    assert picked is cars[2]
    assert not any(line.startswith("Enter - ") for line in world.said), "обещать Enter нечем"


def test_a_default_that_leaves_the_exactly_named_picture_takes_the_liveliest() -> None:
    """🔴 TC-812. Страж «имя названо целиком» берёт живейшую вслух, а не спрашивает.

    «блич s1e1»: у «Блича» 2004 года рой ниже порога живости - взята живая одноимённая
    линейка 2022 года, и строка называет обе картины, причину и ключ ``--menu``.
    Вопрос без дефолта (TC-715) остался за явным ``--menu``.
    """
    world = Outside()
    bleach = [
        plan("Блич", 2004, kind="tv", seeders=3, asked_series=True),
        plan("Блич: Тысячелетняя кровавая война", 2022, kind="tv", seeders=40, asked_series=True),
    ]

    picked = _pick_plan(bleach, asked="блич", environment=world)

    assert picked is bleach[1], "взята самая живая - названная не играет"
    assert world.asked == [], "вопроса на обычном пути больше нет"
    assert world.said == [
        "«блич» - это «Блич (2004, сериал)», но не играет: рой у неё мёртв - сидов 3; "
        "беру самую живую - «Блич: Тысячелетняя кровавая война (2022, сериал)»; "
        "всего подошло картин 2; другая: cast блич --menu"
    ]


def test_the_named_guard_still_asks_without_a_default_behind_the_menu_flag() -> None:
    """За явным ``--menu`` страж имени по-прежнему отдаёт номер человеку: дефолта нет."""
    world = Outside(answers=[2])
    bleach = [
        plan("Блич", 2004, kind="tv", seeders=3, asked_series=True),
        plan("Блич: Тысячелетняя кровавая война", 2022, kind="tv", seeders=40, asked_series=True),
    ]

    picked = _pick_plan(bleach, asked="блич", environment=world, menu=True)

    assert world.said[1].startswith("«блич» - это «Блич (2004, сериал)»")
    assert world.asked == [("Что смотрим?", 2, None)], "дефолта у вопроса нет"
    assert picked is bleach[1], "взята та картина, чей номер назвал человек"
    assert not any(line.startswith("Enter - ") for line in world.said), "обещать Enter нечем"


def test_several_pictures_are_not_a_reason_to_ask_when_the_top_is_the_one_asked() -> None:
    """🔴 Подошло три картины, а спрашивать не о чем: первая часть жива и стоит сверху.

    Список тут не печатается вовсе: меню читают там, где на него отвечают, а перед
    показом, который уже начался, читать его некому. Вместо списка - одна строка про
    решение, и в ней есть ход к соседним частям.
    """
    world = Outside()
    cars = [
        plan("Тачки", 2006, part=1, seeders=66),
        plan("Тачки 2", 2011, part=2, seeders=71),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]

    picked = _pick_plan(cars, asked="тачки", environment=world)

    assert picked is cars[0]
    assert world.asked == [], "вопроса не было"
    assert world.said == [
        "беру «Тачки (2006)» - подошло картин 3; другая: cast releases тачки и --pick N"
    ]


def test_the_menu_flag_raises_the_list_where_the_device_would_take_it_itself() -> None:
    """🔴 TC-802. «Покажи, что ещё есть» - это флаг ``--menu``, а не отсутствие решения.

    Без флага «тачки» включаются сами: тачками зовут ровно их, и вопрос тут был лишним.
    С флагом поднимается тот же список и тот же дефолт - зритель просил выбор и получает
    его, включая соседние части франшизы.
    """
    world = Outside()
    cars = [
        plan("Тачки", 2006, part=1, seeders=66),
        plan("Тачки 2", 2011, part=2, seeders=71),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]

    picked = _pick_plan(cars, asked="тачки", environment=world, menu=True)

    assert picked is cars[0], "пустой Enter - это по-прежнему дефолт"
    assert world.asked == [("Что смотрим?", 3, 1)], "список подняли - о нём и спрашивают"
    assert world.said[0].splitlines()[1] == "  2. Тачки 2 (2011)"


def test_a_picture_the_lines_are_silent_about_needs_no_terminal_either() -> None:
    """Спрашивать не о чем - значит и терминал не нужен: висеть и отказываться не на чем.

    Ровно в этом месте отказ был больнее всего: на стыке серий консоли уже нет, а
    картина есть, и «вслепую не выбираю» означало не показ вместо показа.
    """
    world = Outside(tty=False)
    cars = [
        plan("Тачки", 2006, part=1, seeders=66),
        plan("Тачки 2", 2011, part=2, seeders=71),
    ]

    picked = _pick_plan(cars, asked="тачки", environment=world)

    assert picked is cars[0]
    assert world.said[0].startswith("беру «Тачки (2006)»")


def test_the_taken_namesake_is_the_one_the_honest_lines_are_about() -> None:
    """🔴 Взятая тёзка - ровно та картина, про которую сказано обеими строками.

    Живее всех тут сам дефолт, поэтому взятие не сменило картину, а перестало быть
    вопросом (TC-812): строка взятия называет «Титаник» 1997 года и варианты за
    ``--menu``, а предстартовая строка про смену (:func:`swap_note`) говорит, почему
    мимо прошёл верх меню - мёртвый «Титаник» 1943 года.
    """
    world = Outside()
    titanic = parts(("Титаник", 1943, 1), ("Титаник", 1953, 2), ("Титаник", 1997, 165))

    picked = _pick_plan(titanic, asked="титаник", environment=world)

    assert picked is titanic[2], "самая живая из одноимённых - она же и дефолт"
    assert world.asked == [], "тёзки больше не спрашивают (TC-812)"
    assert world.said == [
        "беру «Титаник (1997)» - самая живая из одноимённых, у лучшей её раздачи сидов 165; "
        "других картин под этим именем: 2, их список: cast титаник --menu"
    ]
    assert swap_note(titanic, picked, "титаник") == (
        "спросили «титаник» - беру «Титаник (1997)», а не «Титаник (1943)»: "
        "рой у неё мёртв - сидов 1"
    ), "картина сменилась - и об этом сказано"


def test_the_answered_menu_is_unsubscribed_from_the_reference_and_closed() -> None:
    """Меню отвечено: сперва отписка от справки, потом отпущенный экран.

    Останься подписка - опоздавшая на миллисекунду строка писала бы уже в чужой вывод, по
    которому в этот момент едет показ.
    """
    world = Outside()
    facts = Waited()
    moana = parts(
        ("Моана: романтика золотого века", 1926, 1), ("Моана", 2016, 222), ("Моана 2", 2024, 140)
    )

    _pick_plan(moana, facts, asked="моана", environment=world)

    assert facts._seen is None
    assert world.painted is not None and world.painted.closed
