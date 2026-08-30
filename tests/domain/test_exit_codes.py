"""Коды возврата ``cast`` не меняются: по ним судят и оболочка, и systemd."""

from torrcast.domain.exit_codes import EXIT_CANCELLED, EXIT_INFRA, EXIT_NOT_FOUND, EXIT_OK


def test_exit_codes_keep_their_meaning() -> None:
    assert (EXIT_OK, EXIT_NOT_FOUND, EXIT_INFRA) == (0, 1, 2)


def test_cancelling_is_neither_success_nor_failure() -> None:
    """🔴 TC-926. Отмена - своё число: ни ноль (показа не было), ни двойка (аварии нет)."""
    assert EXIT_CANCELLED == 3
    assert EXIT_CANCELLED not in (EXIT_OK, EXIT_NOT_FOUND, EXIT_INFRA)
