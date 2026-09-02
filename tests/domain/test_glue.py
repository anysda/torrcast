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


def test_an_edition_tail_no_longer_splits_one_picture_in_two() -> None:
    """🎯 TC-910. Рядом с настоящим пунктом стоял второй, почти пустой, отличавшийся
    только служебным хвостом издания. Пункт один, и обе половины лежат в его пуле."""
    found = glue(
        [
            _picture("Врата Штейна", 2011),
            _picture("Врата Штейна: Полное издание", 2011),
        ]
    )

    assert len(found) == 1
    assert len(found[0].releases) == 2


def test_the_directors_cut_joins_the_picture_it_recut() -> None:
    """Другой монтаж той же картины: выбор монтажа - дело отбора раздачи, не меню."""
    found = glue(
        [
            _picture("Властелин колец: Возвращение короля", 2003),
            _picture("Властелин Колец: Возвращение Короля. Режиссерская версия", 2003),
        ]
    )

    assert len(found) == 1
    assert len(found[0].releases) == 2


def test_extras_are_a_separate_work_and_stay_a_separate_item() -> None:
    """🔴 Встречный сторож против жадности: «Дополнительные материалы» это ДРУГАЯ работа
    с другим хронометражом, и склейка подсунула бы зрителю не тот фильм."""
    found = glue(
        [
            _picture("Игра престолов", 2011),
            _picture("Игра Престолов: Дополнительные материалы", 2011),
        ]
    )

    assert len(found) == 2


def test_a_documentary_about_the_picture_is_not_its_edition() -> None:
    """🔴 «Расширенная версия» - перевод «Expanded», и так зовётся документальный фильм О
    картине. Хвост похож на издание, а за ним чужая работа."""
    found = glue(
        [
            _picture("Чужие", 1986, "Aliens"),
            _picture("Чужие: Расширенная версия", 1986, "Aliens Expanded"),
        ]
    )

    assert len(found) == 2


def test_the_adaptation_mark_does_not_split_one_picture_in_two() -> None:
    """🔴 TC-969. Выдача звала один и тот же сериал то «Sakusei Byoutou», то «Sakusei
    Byoutou The Animation», и в меню он стоял двумя пунктами: живым и мёртвым."""
    found = glue(
        [
            _picture("Sakusei Byoutou", None),
            _picture("Sakusei Byoutou The Animation", None),
        ]
    )

    assert len(found) == 1
    assert len(found[0].releases) == 2


def test_the_form_word_still_keeps_a_film_out_of_the_series_pool() -> None:
    """Встречный сторож: слово ФОРМЫ между видами не шум, а единственная улика, и
    примета экранизации снимается по своему списку, а не заодно с ним."""
    found = glue(
        [
            Picture(
                title="Naruto Shippuuden",
                year=None,
                kind="tv",
                releases=[Release(raw_name="Naruto Shippuuden", title="Naruto Shippuuden")],
            ),
            Picture(
                title="Naruto Shippuuden Movie",
                year=None,
                kind="movie",
                releases=[
                    Release(raw_name="Naruto Shippuuden Movie", title="Naruto Shippuuden Movie")
                ],
            ),
        ]
    )

    assert len(found) == 2
