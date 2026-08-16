"""Коды возврата ``cast`` не меняются: по ним судят и оболочка, и systemd."""

from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_NOT_FOUND, EXIT_OK


def test_exit_codes_keep_their_meaning() -> None:
    assert (EXIT_OK, EXIT_NOT_FOUND, EXIT_INFRA) == (0, 1, 2)
