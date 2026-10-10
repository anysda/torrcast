"""Сохранённая раздача возвращается до повтора запроса после рестарта службы."""

from torrcast.adapters.torrserver.restart_recovery import RestartRecovery

KEY = "0123456789abcdef0123456789abcdef01234567"
MAGNET = f"magnet:?xt=urn:btih:{KEY}"


def test_a_get_recovers_the_known_magnet() -> None:
    recovery = RestartRecovery()
    added: list[str] = []
    recovery.remember(KEY, MAGNET)

    restore = recovery.for_request(
        "/torrents", {"action": "get", "hash": KEY.upper()}, added.append
    )

    assert restore is not None
    restore()
    assert added == [MAGNET]
