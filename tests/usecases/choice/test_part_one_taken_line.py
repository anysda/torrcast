"""Зеркало строки взятия после стража первой части."""

from tests.usecases.choice.world import plan
from torrcast.domain.catalogs.choice.en import en
from torrcast.domain.catalogs.choice.ru import ru
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice.part_one_taken_line import part_one_taken_line


def test_the_guard_the_taken_part_and_the_menu_door_are_named() -> None:
    cars = [plan("Тачки", 2006, part=1, seeders=2), plan("Тачки 2", 2011, part=2, seeders=40)]

    assert part_one_taken_line(cars, 2, "тачки") == phrase(
        "choice.part_one_dead_why_taken",
        picture="Тачки (2006)",
        why=phrase("choice.why_dead_swarm", seeds=2),
        taken="Тачки 2 (2011)",
        asked="тачки",
    )


def test_the_line_that_starts_a_show_does_not_ask_for_a_number() -> None:
    """Без ``--menu`` показ начинается сам: «назови номер» рядом с «беру» - противоречие.

    Прежняя строка клеила к фразе меню «вместо неё другую часть сам не включаю - вот что
    есть, назови номер» хвост «беру первую живую», и зритель «Брата» читал оба сразу.
    """
    for book, refusal in ((ru(), "сам не включаю"), (en(), "do not start")):
        for key in ("absent", "dead", "dead_why"):
            assert refusal not in book[f"choice.part_one_{key}_taken"], key
            assert refusal in book[f"choice.part_one_{key}"], "у меню отказ остаётся"
