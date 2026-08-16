"""Tests for immutable scenario settings."""

from dataclasses import FrozenInstanceError

import pytest

from torrcast.domain.settings import Settings


def test_settings_are_immutable_values() -> None:
    settings = Settings(tv="TV")
    with pytest.raises(FrozenInstanceError):
        settings.tv = "other"  # type: ignore[misc]
