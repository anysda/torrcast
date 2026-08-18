"""Зеркало ручательства имени добора: каталог подписал этим именем ту же самую картину."""

from __future__ import annotations

from tests.usecases.discover.world import franchise, row
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.discover._vouched import _vouched

_BLUE = franchise("blue exorcist", [row("Blue Exorcist - 01 [1080p]", "a")])
_FRUITS = franchise("fruits basket", [row("Fruits Basket (2019) WEB-DL 1080p", "b")])


def test_a_name_that_proved_itself_vouches_for_a_yearless_picture() -> None:
    """Года у латинских раздач обычно нет вовсе - и спорить с годом справки нечем."""
    assert _vouched(_BLUE, Origin(title="Blue Exorcist", year=2011), proven=True) is True


def test_a_name_read_off_a_stranger_release_vouches_for_nothing() -> None:
    """``The Climbers`` из выдачи «Восхождения» - не доказательство, а чужая подпись."""
    assert _vouched(_BLUE, Origin(title="Blue Exorcist", year=2011), proven=False) is False


def test_a_year_that_argues_with_the_facts_is_a_namesake() -> None:
    """Справка знает год, картина под этим именем называет свой, и они врозь - тёзка."""
    assert _vouched(_FRUITS, Origin(title="Fruits Basket", year=2001), proven=True) is False


def test_a_year_within_a_single_step_is_the_same_thing() -> None:
    """Год производства против года проката - допуск в один год, как везде."""
    assert _vouched(_FRUITS, Origin(title="Fruits Basket", year=2020), proven=True) is True


def test_nothing_arrived_and_there_is_nothing_to_vouch_for() -> None:
    """Картин под именем добора не приехало - ручаться не за что."""
    assert _vouched([], Origin(title="Fruits Basket"), proven=True) is False
