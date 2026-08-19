"""Зеркало :mod:`torrcast.domain._release_fields`: поля разобранной раздачи."""

from __future__ import annotations

from dataclasses import fields

from torrcast.domain._release_fields import _ReleaseFields
from torrcast.domain.release import Release


def test_the_parsed_fields_ride_into_the_release_and_only_the_name_is_required() -> None:
    """Поля приезжают в раздачу целиком, а обязательны у неё только имя и название."""
    release = Release(raw_name="Кино.1999.1080p", title="Кино")

    assert {field.name for field in fields(_ReleaseFields)} <= {
        field.name for field in fields(Release)
    }
    assert (release.seeders, release.copies, release.kind) == (0, 1, "movie")
