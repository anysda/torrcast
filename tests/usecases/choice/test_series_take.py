"""Зеркало :mod:`torrcast.usecases.choice.series_take`: сериал под одним именем с фильмом.

🔴 Решение владельца 02-09-2026: «без меню между фильмом и сериалом выбирать сериал».
Вторая половина того же решения - «если я пишу тачки он не должен выбрать тачки байки
мэтра» - тут весит больше первой, и на неё смотрят зеркала ограждений: номерованная
франшиза и мёртвый сериал предпочтение вида не пускают.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, outside, plan
from torrcast.usecases.choice.series_take import series_take


def test_the_series_is_taken_over_the_film_of_the_same_name() -> None:
    """«мастер и маргарита»: дефолт - живой полный метр, а под тем же именем есть сериал."""
    master = [
        plan("Мастер и Маргарита", 2024, seeders=300),
        plan("Мастер и Маргарита", 2005, kind="tv", seeders=40),
    ]

    with outside(Outside()):
        assert series_take(master) == 2


def test_the_liveliest_series_is_taken_when_there_are_several() -> None:
    """Внутри выбранного вида решает живость: правило меняет вид, а не порядок живости."""
    menu = [
        plan("Байки Мэтра", 2006, seeders=300),
        plan("Байки Мэтра", 2008, kind="tv", seeders=20),
        plan("Байки Мэтра", 2012, kind="tv", seeders=90),
    ]

    with outside(Outside()):
        assert series_take(menu) == 3


def test_a_numbered_franchise_keeps_the_kind_out_of_the_choice() -> None:
    """«тачки»: франшиза названа номерами частей - сериал под тем же именем выбор не берёт."""
    cars = [
        plan("Тачки", 2006, part=1, seeders=66),
        plan("Тачки 2", 2011, part=2, seeders=71),
        plan("Тачки: Байки Мэтра", 2008, kind="tv", seeders=300),
    ]

    with outside(Outside()):
        assert series_take(cars) == 0, "номер части в выдаче отключает предпочтение вида"


def test_a_dead_series_is_not_taken_off_a_live_film() -> None:
    """Уводить с живого фильма на пустой рой хуже, чем не слушать вид вовсе."""
    menu = [
        plan("Мастер и Маргарита", 2024, seeders=300),
        plan("Мастер и Маргарита", 2005, kind="tv", seeders=1),
    ]

    with outside(Outside()):
        assert series_take(menu) == 0


def test_a_series_standing_default_is_not_taken_again() -> None:
    """Дефолт и так сериал: менять нечего, и лишняя строка была бы шумом."""
    menu = [
        plan("Мастер и Маргарита", 2005, kind="tv", seeders=300),
        plan("Мастер и Маргарита", 2024, seeders=40),
    ]

    with outside(Outside()):
        assert series_take(menu) == 0


def test_a_menu_of_series_alone_leaves_the_kind_out_of_it() -> None:
    """Спорить видам не о чем: все картины сериалы, и решает между ними живость."""
    bleach = [
        plan("Блич", 2004, kind="tv", seeders=300),
        plan("Блич: Тысячелетняя кровавая война", 2022, kind="tv", seeders=40),
    ]

    with outside(Outside()):
        assert series_take(bleach) == 0


def test_a_menu_of_films_alone_leaves_the_kind_out_of_it() -> None:
    """Сериала нет вовсе - вид ничего не решает, и правило молчит."""
    with outside(Outside()):
        assert series_take([plan("Мумия", 1999, seeders=47), plan("Мумия", 2017, seeders=58)]) == 0


def test_a_series_whose_name_adds_words_is_another_picture() -> None:
    """«звездные войны»: под именем саги стоит сериал-спинофф про другого героя.

    🔴 TC-1004. «Под одним именем» - про имя, а не про франшизу. Живой замер 05-09-2026:
    на «звездные войны» продукт брал «Звёздные войны. Дарт Мол: Повелитель теней» вместо
    «Скрытой угрозы» и вслух звал это одним именем.
    """
    saga = [
        plan("Звёздные войны: Эпизод I - Скрытая угроза", 1999, seeders=300),
        plan("Звёздные войны. Дарт Мол: Повелитель теней", 2026, kind="tv", seeders=90),
    ]

    with outside(Outside()):
        assert series_take(saga) == 0, "лишние слова в имени сериала - другая картина"


def test_a_shorter_name_of_the_same_picture_is_still_taken() -> None:
    """Имя короче - картина та же: каталог держит «Байки Мэтра» и с приставкой, и без неё."""
    mater = [
        plan("Тачки Мультачки: Байки Мэтра", 2006, seeders=300),
        plan("Байки Мэтра", 2008, kind="tv", seeders=90),
    ]

    with outside(Outside()):
        assert series_take(mater) == 2
