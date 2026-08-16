"""Проверки выбора доверенного сертификата."""

from torrcast.domain.trust_anchor import trust_anchor


def test_unreadable_certificate_is_returned() -> None:
    assert trust_anchor("/missing/cert.pem") == "/missing/cert.pem"
