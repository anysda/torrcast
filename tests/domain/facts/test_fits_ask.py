"""Зеркало :mod:`torrcast.domain.facts.fits_ask`: та ли это картина или её тёзка."""

from torrcast.domain.facts.ask import Ask
from torrcast.domain.facts.dated import Dated
from torrcast.domain.facts.fits_ask import fits_ask


def test_a_namesake_of_another_year_does_not_fit() -> None:
    """🔴 Пять находок «Паразиты» разных лет вели в одну статью и делили один постер.

    Сказать человеку, что четыре из них - не они, было нечем: картинка чужой картины
    подписана НАШЕЙ строкой.
    """
    row = Dated("Parasite", "Q61448040", frozenset({2019}), frozenset({"movie"}))
    assert fits_ask(Ask("Паразиты", 2019, "movie"), row, {})
    assert not fits_ask(Ask("Паразиты", 1999, "movie"), row, {})


def test_a_year_that_the_article_kept_quiet_about_comes_from_wikidata() -> None:
    """Годы, добранные пачкой из P577, сверяются наравне с годами из категорий."""
    row = Dated("Parasite", "Q61448040", frozenset(), frozenset({"movie"}))
    assert not fits_ask(Ask("Паразиты", 2019, "movie"), row, {})
    assert fits_ask(Ask("Паразиты", 2019, "movie"), row, {"Q61448040": {2019, 2020}})


def test_a_series_does_not_take_the_poster_of_the_film_of_the_same_year() -> None:
    """«Паразиты» 2019 года - это и фильм, и сериал: без рода строки делили картинку.

    🔴 Строка тут собрана так, как её собирает боевая проводка: русская статья фильма
    называется «Паразиты (фильм)», и уточнение рода в её имени едет полем ``named``
    (:func:`~torrcast.domain.facts.dated_pages.dated_pages`). Оно и есть доказательство,
    что тёзка другого рода у картины ЕСТЬ, а значит наша догадка «сериал» целит именно
    в неё: отменять догадку нечем.
    """
    film = Dated("Parasite", "Q61448040", frozenset({2019}), frozenset({"movie"}), "", "movie")
    assert not fits_ask(Ask("Паразиты", 2019, "tv"), film, {})


def test_an_anthology_under_a_bare_name_keeps_the_poster_of_its_own_film() -> None:
    """🔴 ОТРИЦАТЕЛЬНАЯ ПРОБА на догадку о роде: сверяй один род - и антология без постера.

    Род «сериал» продукт не знает, а угадывает по метке серии в имени раздачи
    (:func:`hass.poster_lookup._kind`), а полнометражная антология раздаётся по новеллам и
    несёт ту же ``s1e1``. «Аниматрица», «Париж, я люблю тебя» и «Бэтмен: Рыцарь Готэма» -
    три из трёх оставались с кадром вместо постера, потому что справку спрашивали про
    сериал, которого нет на свете.

    Отменяет догадку ИМЯ найденной статьи, а не перебор родов: имя голое - тёзки другого
    рода нет, и статья под ним говорит про спрошенную картину. Лишнего похода в сеть это
    не стоит, имя приезжает тем же запросом, что и статья.
    """
    film = Dated("The Animatrix", "Q219776", frozenset({2003}), frozenset({"movie"}))

    assert fits_ask(Ask("Аниматрица", 2003, "tv"), film, {}), (
        "антологии с метками серий отказано в её собственном постере"
    )


def test_the_guess_is_cancelled_only_downwards_and_only_by_the_name() -> None:
    """Послабление одностороннее: фильму статья сериала не достаётся ни при каком имени.

    Род «movie» ставится там, где меток серий нет вовсе, и догадкой он не является -
    отменять нечего. А год сверяется по-прежнему обоими: снятый род не снимает года.
    """
    series = Dated("Fargo", "Q3743949", frozenset({2014}), frozenset({"tv"}))
    anthology = Dated("The Animatrix", "Q219776", frozenset({2003}), frozenset({"movie"}))

    assert not fits_ask(Ask("Фарго", 2014, "movie"), series, {})
    assert not fits_ask(Ask("Аниматрица", 2005, "tv"), anthology, {})


def test_a_year_that_was_never_asked_about_is_not_a_refusal() -> None:
    """Год не спрошен - статья годится: отказ это сказанное ДРУГОЕ, а не несказанное."""
    quiet = Dated("Armitage III", "Q123", frozenset({2002}), frozenset({"movie"}))
    assert fits_ask(Ask("Армитаж: Двойная матрица", None, "movie"), quiet, {})
    assert fits_ask(Ask("Матрица: Путь Нео", None, "other"), quiet, {})


def test_an_article_that_never_calls_itself_a_picture_is_a_refusal() -> None:
    """🔴 ОТРИЦАТЕЛЬНАЯ ПРОБА: пропусти молчащий род - и «Чернобыль» берёт фото станции.

    Живой случай «Чернобыль. Два цвета времени» 1986 года: полнотекстовый поиск приводил
    «Аварию на Чернобыльской АЭС», год у события ровно тот же, а рода событие не называет
    вовсе - оно и не картина. Плитка получала снимок станции под нашей подписью.

    Молчание тут «не знаю», и наравне с «да» оно проходить не должно: категории приезжают
    тем же запросом с обеих сторон, и всякая настоящая картина себя ими называет.
    """
    event = Dated("Chernobyl disaster", "Q486", frozenset({1986}), frozenset())

    assert not fits_ask(Ask("Чернобыль. Два цвета времени", 1986, "tv"), event, {}), (
        "статья, не назвавшая себя картиной, отдала постер"
    )
    assert not fits_ask(Ask("Чернобыль. Два цвета времени", 1986, "movie"), event, {})


def test_a_picture_of_an_unnamed_kind_still_takes_any_article() -> None:
    """Спрошен не фильм и не сериал - сверять род нечем, и строгость тут была бы выдумкой.

    «Матрица: Путь Нео» - игра: род её раздача называет словом ``other``, и требовать от
    статьи киношной категории значило бы отнять у неё постер ни за что.
    """
    event = Dated("The Matrix: Path of Neo", "Q1", frozenset({2005}), frozenset())

    assert fits_ask(Ask("Матрица: Путь Нео", 2005, "other"), event, {})


def test_a_season_between_the_start_and_the_end_belongs_to_its_series() -> None:
    """🔴 ОТРИЦАТЕЛЬНАЯ ПРОБА: сверяй членство в списке - и сезон остаётся без обложки.

    Живой случай «Чернобыль 2. Зона отчуждения»: раздача пишет номер сезона в название,
    а годом ставит 2017 - год этого сезона. Статья сериала называет 2014 и 2019, начало
    и конец показа, и 2017-го в списке нет вовсе.
    """
    series = Dated("Chernobyl: Exclusion Zone", "Q1", frozenset({2014, 2019}), frozenset({"tv"}))

    assert fits_ask(Ask("Чернобыль 2. Зона отчуждения", 2017, "tv"), series, {}), (
        "сезон между началом и концом показа не признан своим сериалом"
    )


def test_a_year_outside_the_run_is_still_a_stranger() -> None:
    """Растяжение тут не отмена сверки: наружу срока сериал никого не пускает."""
    series = Dated("Chernobyl: Exclusion Zone", "Q1", frozenset({2014, 2019}), frozenset({"tv"}))

    assert not fits_ask(Ask("Чернобыль", 2022, "tv"), series, {}), "год за сроком показа принят"
    assert not fits_ask(Ask("Чернобыль", 2013, "tv"), series, {}), "год до начала показа принят"


def test_a_film_has_no_run_to_stretch() -> None:
    """🔴 У фильма даты публикации - разнобой источников, а не показ.

    «Возвращение к источнику» 2004 года приезжало под «Аниматрицу» 2003-го уже при
    допуске в один год; промежуток между фестивалем и прокатом дал бы то же самое.
    """
    film = Dated("The Animatrix", "Q2", frozenset({2003, 2005}), frozenset({"movie"}))

    assert not fits_ask(Ask("Возвращение к источнику", 2004, "movie"), film, {}), (
        "фильму растянули промежуток между датами публикации в срок показа"
    )


def test_a_single_year_is_a_date_and_not_a_run() -> None:
    """Одинокий год растягивать не во что: срок начинается с двух названных концов."""
    once = Dated("Chernobyl", "Q3", frozenset({2019}), frozenset({"tv"}))

    assert not fits_ask(Ask("Чернобыль", 2021, "tv"), once, {})
