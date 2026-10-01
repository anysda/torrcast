"""Держатели раздач внутри процесса: снимает каждый свою отметку, снос ждёт последнего."""

from __future__ import annotations

import gc
import threading

import pytest

from torrcast.usecases.torrent_claims import TorrentClaims


class _Owner:
    """Держатель: страница, отбор показа или разбор серий."""


def test_the_last_holder_frees_the_release_and_not_the_first() -> None:
    claims, card, show = TorrentClaims(), _Owner(), _Owner()
    claims.claim("h", card)
    claims.claim("h", show)

    assert claims.unclaim("h", card) is False, "раздачу ещё держит отбор показа"
    assert claims.claimed("h") is True
    assert claims.unclaim("h", show) is True
    assert claims.claimed("h") is False


def test_claiming_twice_is_one_claim() -> None:
    claims, card = TorrentClaims(), _Owner()
    claims.claim("h", card)
    claims.claim("h", card)

    assert claims.unclaim("h", card) is True


def test_an_unknown_release_is_free_and_an_empty_hash_is_never_held() -> None:
    claims = TorrentClaims()
    claims.claim("", _Owner())

    assert claims.claimed("") is False
    assert claims.unclaim("никто", _Owner()) is True


def test_a_holder_gone_to_the_collector_holds_nothing() -> None:
    """Стенд, брошенный на исключении без уборки, не держит раздачу вечно."""
    claims = TorrentClaims()
    claims.claim("h", _Owner())
    gc.collect()

    assert claims.claimed("h") is False


def test_kept_holds_for_the_block_and_lets_go_on_an_error() -> None:
    claims, show = TorrentClaims(), _Owner()
    with pytest.raises(RuntimeError), claims.kept("h", show):
        assert claims.claimed("h") is True
        raise RuntimeError("показ не поднялся")

    assert claims.claimed("h") is False


def test_a_release_is_held_while_its_add_is_still_answering() -> None:
    """🔴 Отметка до ``add``: снос другого держателя в эту секунду раздачу не выдернет."""
    claims, card, show = TorrentClaims(), _Owner(), _Owner()
    magnet = f"magnet:?xt=urn:btih:{'c' * 40}"
    claims.claim("c" * 40, card)
    freed: list[bool] = []

    def add(asked: str) -> str:
        freed.append(claims.unclaim("c" * 40, card))  # карточка убирает, пока идёт add
        return "c" * 40

    assert claims.adding(magnet, show, add) == "c" * 40
    assert freed == [False], "отбор показа держал раздачу уже во время add"
    assert claims.unclaim("c" * 40, show) is True


def test_a_failed_add_leaves_no_claim() -> None:
    claims, show = TorrentClaims(), _Owner()

    def add(asked: str) -> str:
        raise RuntimeError("служба лежит")

    with pytest.raises(RuntimeError):
        claims.adding(f"magnet:?xt=urn:btih:{'d' * 40}", show, add)

    assert claims.claimed("d" * 40) is False


@pytest.mark.machine
def test_dropping_asks_the_claims_again_and_holds_off_an_add_until_it_is_done() -> None:
    """Проверка «ничья ли» внутри сноса спрашивает отметки снова: замок повторного входа."""
    claims, holder = TorrentClaims(), _Owner()
    order: list[str] = []

    def add(magnet: str) -> str:
        order.append("add")
        return "e" * 40

    took = threading.Thread(
        target=claims.adding, args=(f"magnet:?xt=urn:btih:{'e' * 40}", holder, add)
    )

    def drop(torrent_hash: str) -> bool:
        took.start()
        took.join(0.3)
        order.append("drop")
        return not claims.claimed(torrent_hash)

    dropped: list[bool] = []
    sweep = threading.Thread(target=lambda: dropped.append(claims.dropping("e" * 40, drop)))
    sweep.start()
    sweep.join(3)
    took.join(3)
    assert dropped == [True], "проверка внутри сноса встала на своём же замке"
    assert order == ["drop", "add"]


def test_a_base32_magnet_is_claimed_by_the_hex_the_service_answers_with() -> None:
    claims, holder = TorrentClaims(), _Owner()
    seen: list[bool] = []
    hexed = "000102030405060708090a0b0c0d0e0f10111213"

    def add(magnet: str) -> str:
        seen.append(claims.claimed(hexed))
        return hexed

    claims.adding("magnet:?xt=urn:btih:AAAQEAYEAUDAOCAJBIFQYDIOB4IBCEQT", holder, add)

    assert seen == [True], "до ответа службы раздача уже отмечена своим hex"
