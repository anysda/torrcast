"""Наши читатели ``/stream``: снятие ждёт идущего и не открывает нового."""

import http.client
import socket
import threading
import urllib.request
from contextlib import suppress

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


def test_a_removed_torrent_refuses_new_reads_without_asking_until_it_is_added_again() -> None:
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


def test_a_non_stream_address_is_not_counted_as_a_torrent_read() -> None:
    reads = StreamReads()
    reads.close(KEY)

    with reads.opened(
        f"https://example.test/movie.mkv?link={KEY}", lambda: open(__file__, "rb")
    ) as f:
        assert f.read(3) == b'"""'


class _SilentStream:
    """Сервер, который отдаёт начало HTTP-ответа и ждёт, когда клиент оборвёт его."""

    def __init__(self) -> None:
        self.sent = threading.Event()
        self.gone = threading.Event()
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self._connection: socket.socket | None = None
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        port = self._listener.getsockname()[1]
        return f"http://127.0.0.1:{port}/stream?link={KEY}&index=1&play"

    def _serve(self) -> None:
        with self._listener:
            connection, _address = self._listener.accept()
            self._connection = connection
            with connection:
                connection.recv(4096)
                connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nfirst")
                self.sent.set()
                with suppress(ConnectionResetError):
                    connection.recv(1)
                self.gone.set()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
        self._listener.close()
        self._thread.join(1)


@pytest.mark.machine
def test_a_stop_shutdowns_a_real_http_reader_and_the_silent_server_sees_it() -> None:
    """Срок обрывает сокет зависшего ответа, а не только стирает его из учёта."""
    reads = StreamReads()
    stream = _SilentStream()
    reading = threading.Event()
    finished = threading.Event()
    outcome: dict[str, object] = {}

    def read() -> None:
        try:
            with reads.opened(
                stream.url, lambda: urllib.request.urlopen(stream.url, timeout=30)
            ) as answer:
                if answer is None:
                    return
                outcome["head"] = answer.read(5)
                reading.set()
                outcome["tail"] = answer.read(1)
        except (http.client.IncompleteRead, OSError) as exc:
            outcome["tail"] = exc
        finally:
            finished.set()

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        assert stream.sent.wait(1), "сервер не начал ответ"
        assert reading.wait(1), "читатель не дошёл до молчащего тела"
        reads.stop(KEY)
        assert finished.wait(1), "читатель не вышел после stop"
        assert outcome.get("head") == b"first"
        tail = outcome.get("tail")
        assert tail == b"" or (
            isinstance(tail, (http.client.IncompleteRead, OSError))
            and not isinstance(tail, TimeoutError)
        ), f"чтение кончилось не обрывом: {tail!r}"
        assert stream.gone.wait(1), "сервер не увидел EOF или RST от читателя"
        reader.join(1)
        assert not reader.is_alive(), "поток чтения пережил срок"
    finally:
        reads.reopen(KEY)
        stream.close()
