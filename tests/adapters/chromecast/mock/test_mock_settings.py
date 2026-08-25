"""Числа сухого приёмника, не зависящие от модели: срок подъёма погасшего показа."""

from __future__ import annotations

from torrcast.adapters.chromecast.mock.mock_settings import _Settings


def test_the_wake_budget_does_not_depend_on_the_receiver_model() -> None:
    """Подъём погасшего показа - как у живого приёмника: попытка тут не одна."""
    assert _Settings.WAKE_TIMEOUT == 60.0, "попытка тут не одна, интервалы держит зовущий"
