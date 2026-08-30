"""Проверяет снятие строки-указателя: режется ровно она и ничего сверх неё."""

from tests.articles import CARS, CLONE_WARS, SEVEN_SAMURAI
from torrcast.domain.facts.unhatted import unhatted


def test_both_kinds_of_pointer_are_cut_off() -> None:
    """Указатель со словом «см.» кончается точкой, «Не путать с ...» - переносом строки."""
    assert "см." not in unhatted(SEVEN_SAMURAI)
    assert unhatted(SEVEN_SAMURAI).startswith("«Семь самура́ев»")
    assert "Не путать" not in unhatted(CLONE_WARS)
    assert unhatted(CLONE_WARS).startswith("«Звёздные во́йны: Во́йны кло́нов»")


def test_the_articles_own_words_survive_the_cut_whole() -> None:
    """🔴 Указатель снимается ЦЕЛИКОМ и только он: за ним стоит вся выдача о картине.

    Отсюда справка узнаёт вид картины, её год и оригинальное имя, и лишняя срезанная
    строка стоила бы описания не одной картине, а всем, чей паспорт стоит первой фразой.
    Проверяется поэтому не начало, а ХВОСТ: жадный рез начало оставляет похожим.
    """
    assert unhatted(CLONE_WARS).endswith(
        "трёхмерный анимационный сериал 2008 года по вселенной «Звёздных войн», "
        "созданный компаниями Lucasfilm Animation и Lucasfilm Animation Singapore."
    )


def test_a_paragraph_without_a_known_formula_is_not_a_pointer() -> None:
    """Шляпка УЗНАЁТСЯ по формуле, а не угадывается по первому абзацу или первой кавычке.

    Русская Википедия открывает статью о кино ровно кавычкой, и правило «выкинуть всё до
    кавычки» съело бы описание у каждой второй картины.
    """
    assert unhatted(CARS).startswith("«Та́чки» (англ. Cars) — американский")
    own = "«О́ко» (англ. The Eye) — фильм ужасов 2008 года.\n\nСнят братьями Пан."
    assert unhatted(own).startswith("«О́ко»")
