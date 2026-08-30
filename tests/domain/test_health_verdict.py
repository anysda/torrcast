"""Зеркало :mod:`torrcast.domain.health_verdict`."""

import pytest

from torrcast.domain.health_verdict import HealthVerdict


@pytest.fixture(autouse=True)
def _russian_lines(_russian_product: None) -> None:
    """Предмет модуля - русское словоблюдие самопроверки, поэтому язык назван вслух.

    Умолчание продукта английское (:mod:`torrcast.domain.catalogs.tongue`), и без этой
    строки набор мерил бы английские надписи, а рассказывал бы про русские.
    """


def test_verdicts_keep_their_words_and_their_weight() -> None:
    """Слово слева читает человек, а признак справа считает код возврата."""
    assert HealthVerdict.ok("ffmpeg") == ("ок      ffmpeg", True)
    assert HealthVerdict.warn("ffmpeg") == ("внимание ffmpeg", True)
    assert HealthVerdict.bad("ffmpeg") == ("плохо   ffmpeg", False)


def test_only_a_failure_makes_the_command_red() -> None:
    """«Внимание» - проходная оценка: она объясняет, а не валит вердикт."""
    assert [ok for _, ok in (HealthVerdict.ok("а"), HealthVerdict.warn("б"))] == [True, True]
    assert HealthVerdict.bad("в")[1] is False


def test_a_verdict_is_the_first_word_of_the_line() -> None:
    """Оценку читают глазами по левому краю, поэтому она стоит первым словом."""
    assert [
        line.split()[0]
        for line, _ in (
            HealthVerdict.ok("текст"),
            HealthVerdict.warn("текст"),
            HealthVerdict.bad("текст"),
        )
    ] == ["ок", "внимание", "плохо"]
