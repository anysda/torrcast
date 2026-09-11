"""Кто из круга отвечает на ключ карточки: :func:`web.card_lookup.card_lookup`."""

from __future__ import annotations

from torrcast.domain.kind import Kind
from torrcast.domain.picture import Picture
from torrcast.usecases.select.plan import Plan
from web.card_lookup import card_lookup


def _plan(
    title: str,
    year: int,
    original: str = "",
    kind: Kind = "movie",
    also: str = "",
    aliases: tuple[str, ...] = (),
) -> Plan:
    picture = Picture(
        title=title, year=year, kind=kind, original=original or None, also=also, aliases=aliases
    )
    return Plan(picture=picture, ranked=[], runtime=1.0, warn_mbit=12.0)


def test_a_picture_answers_to_the_key_made_of_its_own_name() -> None:
    plan = _plan("Целиком и полностью", 2022, "Bones and All")

    assert card_lookup([plan], "movie:целиком-и-полностью:2022") == (plan, 1)


def test_a_picture_answers_to_the_key_made_of_its_original_name() -> None:
    """Ключ плитки полки собран из имени раздачи, а круг зовёт картину прокатным."""
    plan = _plan("Целиком и полностью", 2022, "Bones and All")

    assert card_lookup([plan], "movie:bones-and-all:2022") == (plan, 1)


def test_the_number_is_the_place_in_the_circle_not_a_flag() -> None:
    """Номер - то, чем «Играть» просит показ ИМЕННО эту картину (ТЗ §4.3)."""
    first = _plan("Энтони Джесельник: Целиком и полностью", 2024, "Anthony Jeselnik: Bones and All")
    second = _plan("Целиком и полностью", 2022, "Bones and All")

    assert card_lookup([first, second], "movie:bones-and-all:2022") == (second, 2)


def test_a_namesake_in_another_year_keeps_its_own_key() -> None:
    """Второй ключ собран правилом ``Picture.key``, а не поиском имени в строке."""
    plan = _plan("Энтони Джесельник: Целиком и полностью", 2024, "Anthony Jeselnik: Bones and All")

    assert card_lookup([plan], "movie:bones-and-all:2022") == (None, 0)


def test_a_series_does_not_answer_to_a_movie_key_of_another_year() -> None:
    """Род и год выведены из раздач, и разойтись вправе только один из двух.

    Разошлись оба - это уже другая картина: замер на стенде `.104` 07-09-2026 отдал по
    запросу «Похищение» три кино-тёзки (1993, 2011, 2019) и сериал 2024 года, и кино
    1993 года на ключ сериала не отвечает.
    """
    plan = _plan("Основание", 2019, "Foundation", kind="tv")

    assert card_lookup([plan], "movie:foundation:2021") == (None, 0)


def test_a_tile_key_answers_when_only_the_year_drifted() -> None:
    """Полке год даёт свежий сезон, кругу - начало сериала; картина та же.

    Замер на стенде `.104` 07-09-2026: плитка «Укрытие» несёт ``tv:укрытие:2026`` (в окне
    ленты одни раздачи сезона 2026), а круг по тому же имени отдаёт ``tv:укрытие:2023``.
    """
    plan = _plan("Укрытие", 2023, "Silo", kind="tv")

    assert card_lookup([plan], "tv:укрытие:2026") == (plan, 1)


def test_a_tile_key_answers_when_only_the_kind_drifted() -> None:
    """Род выводится из имён раздач, и узкий набор полки зовёт сериал кино.

    Тот же замер: плитка несёт ``movie:the-great-escape:2016``, круг по «The Great Escape»
    отдаёт ``tv:the-great-escape:2016`` - год тот же, разошёлся только род.
    """
    plan = _plan("The Great Escape", 2016, kind="tv")

    assert card_lookup([plan], "movie:the-great-escape:2016") == (plan, 1)


def test_the_exact_picture_wins_over_the_one_whose_kind_drifted() -> None:
    """Съехавший род уступает точному совпадению, где бы то ни стояло в круге."""
    drifted = _plan("Укрытие", 2026, "Silo", kind="movie")
    exact = _plan("Укрытие", 2026, "Silo", kind="tv")

    assert card_lookup([drifted, exact], "tv:укрытие:2026") == (exact, 2)


def test_a_namesake_that_shares_neither_kind_nor_year_is_another_picture() -> None:
    """Тот же замер: «Похищение» 1993 года кругу известно, а ключ у него свой."""
    plan = _plan("Похищение", 2024, kind="tv")

    assert card_lookup([plan], "movie:похищение:1993") == (None, 0)


def test_a_key_nobody_owns_is_no_pick_at_all() -> None:
    plan = _plan("Целиком и полностью", 2022, "Bones and All")

    assert card_lookup([plan], "movie:nobody:1900") == (None, 0)


def test_a_tile_key_answers_through_a_typo_when_kind_and_year_both_agree() -> None:
    """Лента и выдача пишут одно имя по-разному: замер на стенде `.104` 11-09-2026 - плитка
    «Идущие за хвостом тигра» 1945 года, круг из раздач «Идушие ...», карточка отвечала 404."""
    plan = _plan("Идушие за хвостом тигра", 1945, "Tora no o wo fumu otokotachi")

    assert card_lookup([plan], "movie:идущие-за-хвостом-тигра:1945") == (plan, 1)


def test_a_typo_is_not_trusted_with_a_drifted_year_or_in_a_short_name() -> None:
    """Опечатка и съехавший год - две натяжки сразу; в коротком имени буква - уже другое имя."""
    drifted = _plan("Идушие за хвостом тигра", 1946)
    short = _plan("Мана", 2020)

    assert card_lookup([drifted], "movie:идущие-за-хвостом-тигра:1945") == (None, 0)
    assert card_lookup([short], "movie:мама:2020") == (None, 0)


def test_the_exactly_named_picture_wins_over_a_typo() -> None:
    typo = _plan("Идушие за хвостом тигра", 1945)
    exact = _plan("Идущие за хвостом тигра", 1945, kind="tv")

    assert card_lookup([typo, exact], "movie:идущие-за-хвостом-тигра:1945") == (exact, 2)


def test_a_picture_answers_to_the_key_made_of_the_name_the_feed_gave_it() -> None:
    """Плитка полки зовёт картину именем ленты раздач, а круг - именем каталога.

    Замер на стенде `.104` 07-09-2026: круг по запросу «Better Days» отдаёт картину
    ``title="Лучшие дни"``, ``original="Shao nian de ni"``, ``also="Better Days"``,
    ``aliases=("better-days",)`` - и ни одно из двух своих имён не даёт ключа полки.
    """
    plan = _plan(
        "Лучшие дни", 2019, "Shao nian de ni", also="Better Days", aliases=("better-days",)
    )

    assert card_lookup([plan], "movie:better-days:2019") == (plan, 1)


def test_a_namesake_with_the_same_alias_in_another_year_is_another_picture() -> None:
    """Год стоит в ключе, и одного алиаса на двоих мало: тот же замер отдал вторым
    номером «Лучшие дни» 2025 года с тем же ``better-days`` в алиасах."""
    older = _plan(
        "Лучшие дни", 2019, "Shao nian de ni", also="Better Days", aliases=("better-days",)
    )
    newer = _plan("Лучшие дни", 2025, "Des jours meilleurs", aliases=("better-days",))

    assert card_lookup([newer, older], "movie:better-days:2019") == (older, 2)
