"""Быстрый ответ карточки до готовности круга раздач."""

from web.preview import _year


def test_a_preview_year_rejects_a_route_without_a_real_year() -> None:
    """Без точного года ключ не даёт права назвать факты картины."""
    assert _year("2014") == 2014
    assert _year("2014.5") is None
    assert _year("1700") is None
