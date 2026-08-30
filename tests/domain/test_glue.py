"""Зеркало :mod:`torrcast.domain.glue`: тёзки, сведённые в одну картину."""

from torrcast.domain.glue import glue
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(title: str, year: int | None, original: str | None = None) -> Picture:
    return Picture(
        title=title,
        year=year,
        original=original,
        releases=[Release(raw_name=f"{title} {year}", title=title, original=original)],
    )


def test_namesakes_of_neighbouring_years_become_one_picture() -> None:
    """Год у раздач одной картины расходится на единицу: это она же, а не вторая."""
    found = glue([_picture("Брат", 1997), _picture("Брат", 1998)])

    assert len(found) == 1
    assert len(found[0].releases) == 2


def test_namesakes_of_distant_years_stay_two_pictures() -> None:
    """Между 1997 и 2019 - другое кино с тем же именем, и склейка была бы подменой."""
    found = glue([_picture("Брат", 1997), _picture("Брат", 2019)])

    assert len(found) == 2


def test_different_names_are_never_glued() -> None:
    found = glue([_picture("Брат", 1997), _picture("Сестра", 1998)])

    assert sorted(p.title for p in found) == ["Брат", "Сестра"]


def test_the_three_d_copy_is_the_same_picture() -> None:
    """«Аватар» и «Аватар 3D» - одна картина, показанная по-разному."""
    found = glue([_picture("Аватар", 2009), _picture("Аватар 3D", 2009)])

    assert len(found) == 1


def test_a_form_word_no_longer_splits_one_picture_in_two() -> None:
    """🎯 TC-904. Одна выдача зовёт фильм «Gekijouban X», другая - голым «X», и до сих пор
    он стоял в меню двумя пунктами. Пункт один, и раздачи обеих половин лежат в его пуле."""
    found = glue(
        [
            _picture(
                "Клинок, рассекающий демонов: Бесконечный поезд",
                2020,
                "Kimetsu no Yaiba: Mugen Ressha-Hen",
            ),
            _picture(
                "Клинок, рассекающий демонов: Поезд «Бесконечный»",
                2020,
                "Gekijouban Kimetsu no Yaiba: Mugen Ressha Hen",
            ),
        ]
    )

    assert len(found) == 1
    assert len(found[0].releases) == 2


def test_the_pair_split_by_transliteration_converges_by_the_russian_name() -> None:
    """«Блич»: оригиналы развела транслитерация подзаголовка, и мирит их русское имя."""
    apart = glue(
        [
            _picture("Блич Фильм 4", 2010, "Bleach Movie 4: The Hell Verse"),
            _picture("Блич Дзигоку-хэн", 2010, "Gekijouban Bleach: Jigoku-hen"),
        ]
    )

    assert len(apart) == 2

    found = glue(
        [
            _picture("Блич Фильм 4: Врата Ада", 2010, "Bleach Movie 4: The Hell Verse"),
            _picture("Блич: Врата Ада", 2010, "Gekijouban Bleach: Jigoku-hen"),
        ]
    )

    assert len(found) == 1
    assert len(found[0].releases) == 2


def test_parts_told_apart_by_subtitle_stay_two_pictures() -> None:
    """🔴 Сторож против подмены: третий и седьмой фильмы это РАЗНЫЕ картины, и снять при
    слове формы весь хвост значило бы свести их в одну."""
    found = glue(
        [
            _picture(
                "Наруто Фильм 3: Хранители Королевства Полумесяца",
                2006,
                "Naruto Movie 3: Guardians of the Crescent Moon Kingdom",
            ),
            _picture(
                "Наруто Фильм 7: Затерянная Башня",
                2006,
                "Naruto Movie 7: The Lost Tower",
            ),
        ]
    )

    assert len(found) == 2


def test_a_bare_part_number_is_the_whole_name_and_keeps_the_pictures_apart() -> None:
    """🔴 Подзаголовка нет, и номер - всё, что о части сказано: «Наруто Фильм 3» и «Наруто
    Фильм 7» обязаны остаться двумя пунктами, иначе номер снят вместе с картиной."""
    found = glue([_picture("Наруто Фильм 3", 2006), _picture("Наруто Фильм 7", 2006)])

    assert len(found) == 2
