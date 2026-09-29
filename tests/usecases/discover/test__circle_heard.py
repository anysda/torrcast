"""Mirror of what the clients of one circle say: whole for the screen, heard for the memory."""

from __future__ import annotations

from typing import Any, cast

from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover._circle_heard import _gone, _heard, _whole


class _Told:
    """A client that tells what it heard, as Prowlarr does."""

    def __init__(self, whole: bool, heard: bool, *gone: tuple[str, ...]) -> None:
        self._whole, self._heard = whole, heard
        self._gone = gone or ((), (), ())

    def whole(self) -> bool:
        return self._whole

    def heard(self) -> bool:
        return self._heard

    def gone(self) -> tuple[tuple[str, ...], ...]:
        return self._gone


def _client(value: Any) -> IndexerClient:
    return cast("IndexerClient", value)


def test_a_client_that_cannot_tell_proved_nothing() -> None:
    """A circle from disk or a fake has no word on its indexers: neither whole nor heard."""
    assert _whole(_client(object())) is False
    assert _heard(_client(object())) is False


def test_a_circle_prowlarr_cut_short_is_heard_but_not_whole() -> None:
    """The screen still says cut; the memory keeps it, for nobody asked kept silent."""
    told = _client(_Told(False, True))
    assert (_whole(told), _heard(told)) == (False, True)


def test_a_client_without_its_own_word_on_hearing_is_heard_only_when_whole() -> None:
    class _WholeOnly:
        def __init__(self, whole: bool) -> None:
            self._whole = whole

        def whole(self) -> bool:
            return self._whole

    assert _heard(_client(_WholeOnly(True))) is True
    assert _heard(_client(_WholeOnly(False))) is False


def test_each_name_that_fell_out_is_told_once_under_its_strongest_reason() -> None:
    """Taken away beats refused, refused beats silent: a name is never counted twice."""
    first = _Told(False, False, ("Knaben", "RuTor"), ("YTS",), ("JacRed",))
    second = _Told(False, False, ("YTS", "JacRed"), (), ("RuTor",))
    silent, banned, refused = _gone([_client(first), _client(second), _client(object())])
    assert (silent, banned, refused) == (("Knaben",), ("YTS",), ("JacRed", "RuTor"))
