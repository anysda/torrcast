"""Проверяет признак «запрос похож на аниме»: по нему Nyaa идёт в основной круг."""

from torrcast.domain.anime_query import anime_query


def test_прямые_слова_про_аниме_читаются_в_любой_графике() -> None:
    """Японские жанры, OVA, метка [TV] - тот же узкий список, что судит имена раздач."""
    assert anime_query("боруто аниме")
    assert anime_query("Naruto [TV]")
    assert anime_query("Steins Gate OVA")


def test_латиница_без_кино_маркеров_трактуется_в_пользу_вызова() -> None:
    """Оригинальное имя аниме от имени картины не отличить, а полноту аниме ронять
    нельзя (TC-229)."""
    assert anime_query("Frieren")
    assert anime_query("Steins Gate")


def test_русский_запрос_без_аниме_слов_nyaa_не_тревожит() -> None:
    """Замер 09-08-2026: на таких запросах Nyaa пуст в 79% случаев."""
    assert not anime_query("матрица")
    assert not anime_query("дюна 2021")


def test_кино_маркер_в_латинском_запросе_отменяет_признак() -> None:
    """Год, movie, season, s01 - у аниме-запроса их не бывает."""
    assert not anime_query("Dune 2021")
    assert not anime_query("Barbie movie")
    assert not anime_query("Breaking Bad season 1")
    assert not anime_query("The Wire s01")
