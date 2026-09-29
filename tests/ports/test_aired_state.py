"""Договор достоверности ответа каталога дат."""

from torrcast.ports.aired_state import AiredState


def test_the_catalogue_answer_distinguishes_known_from_unknown() -> None:
    assert list(AiredState) == [AiredState.KNOWN, AiredState.UNKNOWN]
