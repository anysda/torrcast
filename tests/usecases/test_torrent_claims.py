"""Держатели раздач внутри процесса: снимает каждый свою отметку, снос ждёт последнего."""

from __future__ import annotations

import gc

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
