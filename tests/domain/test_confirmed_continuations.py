"""Зеркало :mod:`torrcast.domain.confirmed_continuations`: что дописывается к франшизе."""

from torrcast.domain.confirmed_continuations import confirmed_continuations
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(title: str, year: int, original: str | None, copies: int = 1) -> Picture:
    releases = [Release(raw_name=title, title=title) for _ in range(copies)]
    return Picture(title=title, year=year, original=original, releases=releases)


BASE = [_picture("Матрица", 1999, "The Matrix", copies=9)]


def test_a_part_whose_original_name_shares_the_root_is_added() -> None:
    """Продолжение подтверждается латинским именем: русское название расходится всегда."""
    later = [_picture("Матрица: Перезагрузка", 2003, "The Matrix: Reloaded")]
    groups = {"матрица": BASE, "матрица-перезагрузка": later}

    found = confirmed_continuations(groups, "матрица", BASE)

    assert [p.title for p in found] == ["Матрица: Перезагрузка"]


def test_a_namesake_from_another_franchise_is_not_added() -> None:
    """Имя начинается так же, а корень оригинала другой - это чужая картина."""
    stranger = [_picture("Матрица времени", 2017, "ARQ")]
    groups = {"матрица": BASE, "матрица-времени": stranger}

    assert confirmed_continuations(groups, "матрица", BASE) == []


def test_a_part_older_than_the_franchise_itself_is_not_a_continuation() -> None:
    """Продолжение позже начала: вышедшее раньше первой части ею не продолжается."""
    earlier = [_picture("Аниматрица", 1995, "The Matrix: Animatrix")]
    groups = {"матрица": BASE, "матрица-аниматрица": earlier}

    assert confirmed_continuations(groups, "матрица", BASE) == []


def test_a_franchise_without_a_single_original_name_confirms_nothing() -> None:
    """Подтверждать нечем: без латинского корня добор был бы догадкой по началу имени."""
    base = [_picture("Матрица", 1999, None)]
    later = [_picture("Матрица: Перезагрузка", 2003, "The Matrix: Reloaded")]

    assert (
        confirmed_continuations({"матрица": base, "матрица-перезагрузка": later}, "матрица", base)
        == []
    )


def _show(title: str, year: int | None, original: str | None, copies: int = 1) -> Picture:
    releases = [Release(raw_name=title, title=title) for _ in range(copies)]
    return Picture(title=title, year=year, kind="tv", original=original, releases=releases)


MOB = [_show("Моб Психо 100", 2016, "Mob Psycho 100", copies=4)]


def test_mob_psycho_seasons_named_by_a_kind_marker_reach_the_menu() -> None:
    """🔴 TC-901, поимённо. «ТВ-2» и «ТВ-3» это тот же сериал, а не соседняя франшиза.

    Года у таких раздач нет вовсе, и якорь о них не говорит ничего: маркер вида уже
    сказал, что это сезон названного сериала, а латинский корень это подтвердил.
    """
    seasons = [
        _show("Моб Психо 100 ТВ-2", None, "Mob Psycho 100 TV-2"),
        _show("Моб Психо 100 ТВ-3", None, "Mob Psycho 100 TV-3"),
    ]
    groups = {"моб-психо-100": MOB, "моб-психо-100-тв": seasons}

    found = confirmed_continuations(groups, "моб-психо-100", MOB)

    assert [p.title for p in found] == ["Моб Психо 100 ТВ-2", "Моб Психо 100 ТВ-3"]


def test_mob_psycho_ova_is_confirmed_by_an_original_longer_than_the_root() -> None:
    """🔴 TC-901, поимённо. У OVA латинское имя длиннее корня: «Mob Psycho 100 Reigen»."""
    ova = [_show("Моб Психо 100 OVA", None, "Mob Psycho 100 Reigen: Shirarezaru Kiseki")]
    groups = {"моб-психо-100": MOB, "моб-психо-100-ova": ova}

    assert [p.title for p in confirmed_continuations(groups, "моб-психо-100", MOB)] == [
        "Моб Психо 100 OVA"
    ]


def test_mob_psycho_ova_two_is_confirmed_by_the_bare_root_without_a_year() -> None:
    """🔴 TC-901, поимённо. Корень совпал целиком, и мимо меню картину уносил один год."""
    ova = [_show("Моб Психо 100 OVA-2", None, "Mob Psycho 100: Daiikkai Rei toka Soudansho")]
    groups = {"моб-психо-100": MOB, "моб-психо-100-ova": ova}

    assert [p.title for p in confirmed_continuations(groups, "моб-психо-100", MOB)] == [
        "Моб Психо 100 OVA-2"
    ]


GHOUL = [_show("Токийский гуль", 2014, "Tokyo Ghoul", copies=4)]


def test_tokyo_ghoul_second_season_reaches_the_menu() -> None:
    """🔴 TC-901, поимённо. «Tokyo Ghoul √A TV-2» продолжает корень, а не совпадает с ним."""
    season = [_show("Токийский Гуль ТВ-2", 2015, "Tokyo Ghoul A TV-2")]
    groups = {"токийский-гуль": GHOUL, "токийский-гуль-тв": season}

    assert [p.title for p in confirmed_continuations(groups, "токийский-гуль", GHOUL)] == [
        "Токийский Гуль ТВ-2"
    ]


def test_tokyo_ghoul_ova_named_by_a_leading_marker_reaches_the_menu() -> None:
    """🔴 TC-901, поимённо. Маркер стоит В НАЧАЛЕ латинского имени: «OVA Tokyo Ghoul»."""
    ova = [_show("Токийский гуль OVA", 2015, "OVA Tokyo Ghoul")]
    groups = {"токийский-гуль": GHOUL, "токийский-гуль-ova": ova}

    assert [p.title for p in confirmed_continuations(groups, "токийский-гуль", GHOUL)] == [
        "Токийский гуль OVA"
    ]


IT = [_picture("Оно", 2017, "It", copies=9)]


def test_a_namesake_without_a_kind_marker_is_still_refused() -> None:
    """🔴 TC-901, поимённо. «Оно приходит ночью» начинается с имени франшизы и чужое.

    Ровно этот случай и держит список маркеров закрытым: по началу имени - хоть русского,
    хоть латинского - своя картина от чужой неотличима, и раскрывать по нему нельзя.
    """
    stranger = [_picture("Оно приходит ночью", 2017, "It Comes at Night", copies=9)]
    groups = {"оно": IT, "оно-приходит-ночью": stranger}

    assert confirmed_continuations(groups, "оно", IT) == []


TITANIC = [_picture("Титаник", 1997, "Titanic", copies=20)]


def test_a_mockbuster_numbered_after_the_franchise_is_refused() -> None:
    """🔴 TC-901, поимённо. «Титаник 666» это не часть «Титаника»: число маркером не считается."""
    stranger = [_picture("Титаник 666", 2022, "Titanic 666", copies=2)]
    groups = {"титаник": TITANIC, "титаник-666": stranger}

    assert confirmed_continuations(groups, "титаник", TITANIC) == []


SPIRITED = [_picture("Унесенные призраками", 2001, "Spirited Away", copies=9)]


def test_a_making_of_about_the_franchise_is_refused() -> None:
    """🔴 TC-901, поимённо. «Фильм о фильме» не продолжение: «Making of» корня не продолжает."""
    about = [_picture('"Унесенные призраками" - фильм о фильме', 2001, "Making of Spirited Away")]
    groups = {"унесенные-призраками": SPIRITED, "унесенные-призраками-фильм-о-фильме": about}

    assert confirmed_continuations(groups, "унесенные-призраками", SPIRITED) == []


ARCANE = [_show("Arcane", 2021, "Arcane", copies=9)]


def test_arcane_namesakes_are_refused() -> None:
    """🔴 TC-901, поимённо. «Arcane Sorcerer» и «Arcane Soul» чужие в обоих видах.

    Латинского имени у них в каталоге нет, а был бы - корня «arcane» оно не продолжает
    через маркер вида, и раскрытие их всё равно не берёт.
    """
    groups = {
        "arcane": ARCANE,
        "arcane-sorcerer": [_picture("Arcane Sorcerer", 1996, None)],
        "arcane-soul": [_picture("Arcane Soul", 2015, "Arcane Soul")],
    }

    assert confirmed_continuations(groups, "arcane", ARCANE) == []


def test_a_kind_marker_does_not_lift_the_year_of_an_older_namesake() -> None:
    """Маркер снимает пустой год, а не названный: вышедшее раньше базы ею не продолжается."""
    older = [_show("Моб Психо 100 ТВ-0", 1998, "Mob Psycho 100 TV-0")]
    groups = {"моб-психо-100": MOB, "моб-психо-100-тв": older}

    assert confirmed_continuations(groups, "моб-психо-100", MOB) == []
