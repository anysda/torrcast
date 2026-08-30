"""Проверяет отказ «ничего не нашлось»: он обязан назвать выпавшие звенья каталога."""

import pytest

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.nothing_found import nothing_found


@pytest.fixture(autouse=True)
def _russian_lines(_russian_product: None) -> None:
    """Предмет модуля - русская фраза отказа, поэтому язык назван вслух.

    Умолчание продукта английское (:mod:`torrcast.domain.catalogs.tongue`), и без этой
    строки набор мерил бы английский отказ, а рассказывал бы про русский.
    """


def test_честный_ноль_остаётся_честным() -> None:
    """🔴 Ограждение к TC-291: «ничего не нашлось» СУЩЕСТВУЕТ. Все ответили, все отдали
    ноль, отметок об отказах нет - это честная пустая полка."""
    error = nothing_found("матрица")
    assert isinstance(error, NotFoundError)
    assert str(error) == "по запросу «матрица» ничего не нашлось"


def test_бан_назван_в_урезанном_каталоге() -> None:
    """«Ничего не нашлось» - утверждение о КАТАЛОГЕ, а бан забирает его половину."""
    error = nothing_found("матрица", banned=("Knaben",))
    assert "каталог сейчас урезан" in str(error)
    assert "Prowlarr увёл в недоступные Knaben" in str(error)


def test_отказ_за_пустой_выдачей_назван_отдельно_от_молчания() -> None:
    """🔴 TC-291. Отказ, спрятанный за ``200 []``, и молчание в свой бюджет - разные
    причины урезанного каталога, и смешать их значит спрятать одну из них."""
    error = nothing_found("матрица", refused=("Knaben",), silent=("RuTor",))
    assert "отказ у Knaben; молчит RuTor" in str(error)


def test_все_три_причины_перечисляются_подряд() -> None:
    error = nothing_found("матрица", banned=("YTS",), refused=("Knaben",), silent=("RuTor",))
    assert str(error) == (
        "по запросу «матрица» ничего не нашлось; каталог сейчас урезан - "
        "Prowlarr увёл в недоступные YTS; отказ у Knaben; молчит RuTor"
    )
