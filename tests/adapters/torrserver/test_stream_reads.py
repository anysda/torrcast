"""Наши читатели ``/stream``: снятие ждёт идущего и не открывает нового."""

import pytest

from torrcast.adapters.torrserver.stream_reads import StreamReads

KEY = "abcdef"


def test_a_close_waits_for_the_reader_to_leave() -> None:
    reads = StreamReads()
    url = f"http://torrserver/stream?link={KEY.upper()}&index=1&play"

    with reads.reading(url) as readable:
        assert readable
        assert reads.close(KEY)
        assert reads.busy(KEY)
    assert not reads.busy(KEY)


def test_a_deadline_stops_a_hung_reader_without_reopening_the_torrent() -> None:
    reads = StreamReads()
    url = f"http://torrserver/stream?link={KEY}&index=1&play"

    with reads.reading(url) as readable:
        assert readable
        assert reads.close(KEY)
        reads.stop(KEY)
        assert reads.stopped(url)
        assert not reads.busy(KEY)
    reads.reopen(KEY)


def test_a_cut_torrent_refuses_new_reads_without_asking_until_it_is_added_again() -> None:
    reads = StreamReads()
    url = f"http://torrserver/stream?link={KEY}&index=1&play"
    assert reads.close(KEY.upper()) is False

    def never() -> None:
        pytest.fail("снятую раздачу не спрашивают")

    with reads.opened(url, never) as answer:
        assert answer is None
    reads.reopen(KEY)
    with pytest.raises(OSError), reads.opened(url, lambda: open("/nonexistent", "rb")):
        pass


def test_an_address_without_a_torrent_is_never_cut() -> None:
    reads = StreamReads()
    reads.close(KEY)

    with reads.opened(
        f"https://example.test/movie.mkv?link={KEY}", lambda: open(__file__, "rb")
    ) as f:
        assert f.read(3) == b'"""'
