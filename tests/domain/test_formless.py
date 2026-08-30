"""Зеркало :mod:`torrcast.domain.formless`: чем слово формы отличается от номера части."""

from torrcast.domain.formless import _formless


def test_a_form_word_is_dropped_wherever_it_stands() -> None:
    """«Gekijouban X» и «X» это одна картина: слово формы стоит и спереди, и сзади."""
    assert _formless("gekijouban-kimetsu-no-yaiba-mugen-ressha-hen") == (
        "kimetsu-no-yaiba-mugen-ressha-hen"
    )
    assert _formless("jujutsu-kaisen-0-movie") == "jujutsu-kaisen-0"
    assert _formless("cowboy-bebop-the-movie") == "cowboy-bebop"
    assert _formless("one-piece-film-strong-world") == "one-piece-strong-world"
    assert _formless("gekijou-soushuuhen-code-geass-hangyaku-no-lelouch-i-koudou") == (
        "code-geass-hangyaku-no-lelouch-i-koudou"
    )


def test_the_number_goes_only_together_with_a_surviving_subtitle() -> None:
    """Четвёртую часть отличает подзаголовок, а не четвёрка: без неё имена сходятся."""
    assert _formless("bleach-movie-4-the-hell-verse") == "bleach-the-hell-verse"
    assert _formless("блич-фильм-4-врата-ада") == "блич-врата-ада"
    assert _formless("naruto-the-movie-3-guardians-of-the-crescent-moon-kingdom") == (
        "naruto-guardians-of-the-crescent-moon-kingdom"
    )


def test_a_number_without_a_subtitle_is_the_whole_part_and_stays() -> None:
    """🔴 Голое «Наруто Фильм 3» - это номер и есть картина, снести его значит подменить."""
    assert _formless("наруто-фильм-3") == "наруто-3"
    assert _formless("наруто-фильм-7") == "наруто-7"
    assert _formless("наруто-фильм-3") != _formless("наруто-фильм-7")
    assert _formless("naruto-movie-iii") == "naruto-3"


def test_a_word_outside_the_closed_list_is_not_a_form_word() -> None:
    """Закрытый список и есть ограждение: за ним стрижка внутри имени резала бы живое."""
    assert _formless("оно-приходит-ночью") == "оно-приходит-ночью"
    assert _formless("титаник-666") == "титаник-666"
    assert _formless("человек-который-изменил-все") == "человек-который-изменил-все"


def test_a_key_made_of_a_form_word_alone_is_kept_whole() -> None:
    """Пустого ключа не отдаём: «фильм» это всё, что о картине сказано, и стричь нечего."""
    assert _formless("фильм") == "фильм"
    assert _formless("movie") == "movie"


def test_a_leading_form_word_plus_a_bare_number_stays_whole() -> None:
    """🔴 TC-906: «Movie 43» - настоящее имя, а не двойник со сведённым ключом `43`."""
    assert _formless("movie-43") == "movie-43"
    assert _formless("film-7") == "film-7"
    assert _formless("gekijouban-bleach") == "bleach"
