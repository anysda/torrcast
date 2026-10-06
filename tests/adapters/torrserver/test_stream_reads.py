"""Наши ответы ``/stream``: снятая раздача не читается, идущее чтение снятие обрывает."""

import http.client
import socket
import threading
import time
import urllib.request

import pytest

from torrcast.adapters.torrserver.stream_reads import StreamReads

KEY = "abcdef"


def _silent_server() -> tuple[socket.socket, threading.Event]:
    """Служба, что отдала заголовки на мегабайт и молчит: как раздача без куска."""
    server = socket.create_server(("127.0.0.1", 0))
    gone = threading.Event()

    def serve() -> None:
        conn, _ = server.accept()
        conn.recv(4096)
        conn.sendall(b"HTTP/1.1 206 Partial Content\r\nContent-Length: 1048576\r\n\r\n")
        conn.settimeout(10)
        if conn.recv(1) == b"":  # обрыв клиента служба видит как конец потока
            gone.set()
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    return server, gone


@pytest.mark.machine
def test_a_cut_ends_the_read_in_flight_and_the_service_sees_the_hangup() -> None:
    reads = StreamReads()
    server, gone = _silent_server()
    url = f"http://127.0.0.1:{server.getsockname()[1]}/stream?link={KEY.upper()}&index=1&play"
    failed: list[BaseException] = []

    def read() -> None:
        try:
            with reads.opened(url, lambda: urllib.request.urlopen(url, timeout=10)) as answer:
                answer.read()
        except http.client.IncompleteRead as exc:
            failed.append(exc)

    reader = threading.Thread(target=read)
    reader.start()
    deadline = time.monotonic() + 5
    while not reads.cut(KEY) and time.monotonic() < deadline:
        reads.reopen(KEY)
        time.sleep(0.01)
    reader.join(3)
    server.close()

    assert not reader.is_alive()
    assert failed
    assert gone.wait(3)


def test_a_cut_torrent_refuses_new_reads_without_asking_until_it_is_added_again() -> None:
    reads = StreamReads()
    url = f"http://torrserver/stream?link={KEY}&index=1&play"
    assert reads.cut(KEY.upper()) is False

    def never() -> None:
        pytest.fail("снятую раздачу не спрашивают")

    with reads.opened(url, never) as answer:
        assert answer is None
    reads.reopen(KEY)
    with pytest.raises(OSError), reads.opened(url, lambda: open("/nonexistent", "rb")):
        pass


def test_an_address_without_a_torrent_is_never_cut() -> None:
    reads = StreamReads()
    reads.cut(KEY)

    with reads.opened(
        f"https://example.test/movie.mkv?link={KEY}", lambda: open(__file__, "rb")
    ) as f:
        assert f.read(3) == b'"""'
