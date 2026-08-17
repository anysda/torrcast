"""Держит раздачу HLS на время показа; поднимает её сценарий показа."""

from __future__ import annotations

import contextlib
import http.server
import socket
import ssl
import threading
from pathlib import Path
from typing import Any

from torrcast.adapters.http_server._feed import _Feed
from torrcast.adapters.http_server._handler import _Handler
from torrcast.domain.infra_error import InfraError
from torrcast.domain.why import why


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    #: Контекст TLS или ``None`` - тогда раздача идёт голым http (дефолт).
    ctx: ssl.SSLContext | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        #: Живые соединения приёмника. Нужны ровно затем, чтобы их можно было закрыть
        #: (:meth:`drop_live`): раздача HTTP/1.1, приёмник держит один keep-alive на весь
        #: показ, а ``server_close`` закрывает только слушающий сокет.
        self._live: set[Any] = set()
        super().__init__(*args, **kwargs)

    def get_request(self) -> tuple[Any, Any]:
        # Слушающий сокет остаётся обычным TCP, рукопожатие уходит в рабочий поток:
        # иначе один полуоткрытый коннект вешает весь accept.
        sock, addr = super().get_request()
        sock.settimeout(60)
        if self.ctx is not None:
            sock = self.ctx.wrap_socket(sock, server_side=True, do_handshake_on_connect=False)
        self._live.add(sock)
        return sock, addr

    def shutdown_request(self, request: Any) -> None:
        self._live.discard(request)
        super().shutdown_request(request)

    def drop_live(self) -> None:
        """Закрыть соединения приёмника — раздача кончилась вместе с этим показом.

        ⚠️ Без этого «раздача остановлена» не значит «раздача молчит». Потоки-обработчики
        демонические и ``server_close`` их не ждёт (``block_on_close`` при
        ``daemon_threads``), а приёмник ходит по HTTP/1.1 и держит **одно** соединение на
        весь показ. На стыке серий оно переживало и упаковку, и раздачу прошлой серии: LOAD
        следующей уходил в тот же сокет, и отвечал на него уже остановленный
        :class:`Feed` — манифест прошлой серии и мгновенный 404 на ``v0.ts``. Дальше
        приёмник отвечал ``IDLE/ERROR``, и зритель видел 15 с чёрного экрана (замер
        живого Q70D).
        """
        for sock in list(self._live):
            self._live.discard(sock)
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)

    def handle_error(self, request: Any, client_address: Any) -> None:
        pass  # битое рукопожатие или оборванный приёмник - не наша авария


class HlsServer:
    """Раздача HLS с того же хоста, где стоит torrcast: в облако поток не уходит.

    Дефолт — голый http: ТВ ходит по IP, ни серта, ни имени, ни DNS в пути
    показа нет. ``tls=True`` включает прежнюю https-раздачу — код жив и работает, но
    требует серта, которому доверяет ТВ (Chromecast self-signed молча не принимает).
    """

    def __init__(
        self,
        root: Path,
        cert: str = "",
        key: str = "",
        host: str = "0.0.0.0",
        port: int = 8080,
        tls: bool = False,
        feed: _Feed | None = None,
    ):
        self.root, self.cert, self.key, self.host, self.port = root, cert, key, host, port
        self.tls = tls
        self.feed = feed
        self._server: _Server | None = None

    def start(self) -> None:
        ctx = None
        if self.tls:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            try:
                ctx.load_cert_chain(self.cert, self.key)
            except (OSError, ssl.SSLError) as exc:
                raise InfraError(f"не читается серт {self.cert}: {why(exc)}") from exc
        handler = type("_Bound", (_Handler,), {"root": self.root, "feed": self.feed})
        try:
            server = _Server((self.host, self.port), handler)
        except OSError as exc:
            raise InfraError(f"порт {self.port} занят или недоступен: {why(exc)}") from exc
        server.ctx = ctx
        self._server = server
        threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True
        ).start()

    def stop(self) -> None:
        """Погасить раздачу целиком: и слушающий сокет, и живые соединения приёмника.

        Второе так же обязательно, как первое (:meth:`_Server.drop_live`): показ, который
        остановлен, обязан замолчать, а не досказывать прошлую серию в keep-alive.
        """
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server.drop_live()
            self._server = None
