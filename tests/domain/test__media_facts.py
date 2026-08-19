"""Зеркало :mod:`torrcast.domain._media_facts`: поля паспорта медиафайла."""

from torrcast.domain._media_facts import _MediaFacts
from torrcast.domain.media import Media


def test_the_passport_fields_ride_into_media_and_stay_frozen() -> None:
    """Поля приезжают в паспорт целиком, а сам он остаётся неизменяемым значением."""
    assert isinstance(Media(), _MediaFacts)
    assert Media(duration=7.0, height=1080) == Media(duration=7.0, height=1080)
