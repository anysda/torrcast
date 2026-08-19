"""Зеркало :mod:`torrcast.usecases.doctor_probe`: общее у всех проб самопроверки."""

from torrcast.usecases.doctor_probe import _INDEXER_TIMEOUT, _TIMEOUT


def test_a_live_search_is_given_more_patience_than_an_ordinary_probe() -> None:
    """Живой поиск отвечает дольше проверки связи, и сроки у них поэтому разные."""
    assert _TIMEOUT < _INDEXER_TIMEOUT
