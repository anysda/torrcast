"""Зеркало :mod:`torrcast.domain.looks_anime`: аниме, узнанное по самому имени раздачи."""

from torrcast.domain.looks_anime import looks_anime


def test_the_word_of_the_genre_names_the_anime() -> None:
    """Источник аниме бывает обычным трекером - тогда об этом говорит только имя."""
    assert looks_anime("Наруто аниме 1080p")
    assert looks_anime("Naruto OVA")


def test_an_ordinary_film_does_not_look_like_anime() -> None:
    assert not looks_anime("Брат 1997 BDRip")


def test_a_form_mark_in_round_brackets_still_names_the_anime() -> None:
    """🔴 TC-1005. Скобочный «ТВ-N» тут форма, а не телеканал: лукбехайнд НЕ переносить.

    Литерал `\\bтв-\\d` стоит и в серийной метке (`_SERIES_HINT_RE`), и здесь, и там
    круглые скобки правкой TC-985 отбиты: `Dub (ТВ-3)` зовёт канал. Слепой перенос той
    правки сюда снимает признак аниме с имени ниже - других примет в нём нет.
    """
    assert looks_anime("[AnimediaTv]Naruto: Shippuuden / Наруто (ТВ-2) [153 из xxx] 720p")
