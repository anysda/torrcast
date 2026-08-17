"""Часть медиатракта; публичный фасад — :mod:`torrcast.stream`."""

from __future__ import annotations

from torrcast.domain.unit_naming import _UNIT_NAME
from torrcast.ports.journal import journal

__all__ = [
    "TRACE",
    "TYPE_CHECKING",
    "_ASSET_RE",
    "_RANGE_RE",
    "_TYPES",
    "_UNIT_NAME",
    "Any",
    "ClassVar",
    "Final",
    "HlsServer",
    "InfraError",
    "Path",
    "_Handler",
    "_Server",
    "_opt_str",
    "_scope",
    "_systemd",
    "contextlib",
    "hls_base",
    "http",
    "json",
    "os",
    "our_address",
    "re",
    "socket",
    "ssl",
    "start_play_unit",
    "stop_play_unit",
    "subprocess",
    "sys",
    "threading",
    "time",
    "unit_active",
    "unit_key",
    "unit_why",
    "why",
]

from importlib import import_module
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    _stream_core = import_module("torrcast.stream_core")
    _PASS_ENV, _UNIT_TAG = _stream_core._PASS_ENV, _stream_core._UNIT_TAG
    segment_slot = import_module("torrcast.stream_probe").segment_slot


import contextlib
import http.server
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final

from torrcast.adapters.filesystem.state import Config
from torrcast.domain.infra_error import InfraError


class _Feed(Protocol):
    """Достаточная для HTTP-адаптера часть поставщика сегментов."""

    out: Path

    def manifest(self) -> bytes: ...

    def segment(self, slot: int) -> Path | None: ...


_package = import_module("torrcast")
why = _package.why


def _scope() -> list[str]:
    """Юнит системный, когда мы root (так после ``install.sh``), иначе
    пользовательский (так на dev). Постоянных юнитов у нас нет ни там, ни там — только
    transient на время показа.
    """
    return [] if os.geteuid() == 0 else ["--user"]


def _systemd(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [tool, *_scope(), *args], capture_output=True, text=True, check=False, timeout=60
    )


def start_play_unit(key: str, unit: str = _UNIT_NAME) -> None:
    """Запустить показ в transient-юните: ``cast`` завершился — показ продолжается,
    логи бесплатно в journald. Переменные окружения проброшены, иначе юнит возьмёт
    прод-пути конфига и состояния вместо dev-овских.
    """
    stop_play_unit(unit)
    env = [f"--setenv={n}={os.environ[n]}" for n in _PASS_ENV if n in os.environ]
    done = _systemd(
        "systemd-run", f"--unit={unit}", "--collect", "--quiet",
        f"--description={_UNIT_TAG}{key}", *env,
        sys.executable, "-m", "torrcast.cli", "--play-key", key,
    )  # fmt: skip
    if done.returncode != 0:
        raise InfraError(f"не запустился юнит {unit}: {done.stderr.strip()[:120] or 'systemd-run'}")


def stop_play_unit(unit: str = _UNIT_NAME) -> None:
    """Погасить transient-юнит и дождаться его смерти: по SIGTERM сторож дописывает
    позицию в state. Отсутствие юнита ошибкой не считается.
    """
    _systemd("systemctl", "stop", unit)


def unit_active(unit: str = _UNIT_NAME) -> bool:
    """Идёт ли показ прямо сейчас."""
    return _systemd("systemctl", "is-active", unit).stdout.strip() == "active"


def unit_key(unit: str = _UNIT_NAME) -> str:
    """Ключ состояния играющего показа — из ``--description`` юнита. Свежайшая запись в
    state для этого не годится: рядом мог писать другой ход, и ``status`` соврал бы.
    """
    found = _systemd("systemctl", "show", unit, "-p", "Description", "--value").stdout.strip()
    return found[len(_UNIT_TAG) :].strip() if found.startswith(_UNIT_TAG) else ""


def unit_why(unit: str = _UNIT_NAME) -> str:
    """Последняя внятная строка САМОГО ПОКАЗА из journald — наружу без трейсбеков.

    🔴 Спрашивают отсюда одно: почему на экране нет картинки, - и отвечать на это
    бухгалтерией systemd нельзя. Замер 16-08-2026 на живой приставке: показ умер, не дав
    ни кадра, и человек у консоли получил «показ не запустился: torrcast-play.service:
    Consumed 5.884s CPU time, 175.4M memory peak». Про беду в этой строке нет ничего:
    последними в журнал юнита пишет не показ, а systemd - о запуске, остановке и
    потраченном процессоре. Поэтому свои строки отбираются по автору записи, а глубина
    поиска берётся с запасом на его послесловие.
    """
    done = _systemd(
        "journalctl", "-u", unit, "-n", "30", "--no-pager",
        "-o", "json", "--output-fields=MESSAGE,SYSLOG_IDENTIFIER",
    )  # fmt: skip
    ours: list[str] = []
    for line in done.stdout.splitlines():
        with contextlib.suppress(ValueError, TypeError):
            record = json.loads(line)
            if record.get("SYSLOG_IDENTIFIER") != "systemd":
                text = str(record.get("MESSAGE") or "").strip()
                if text:
                    ours.append(text)
    return ours[-1][:160] if ours else "в журнале пусто"


def _opt_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


#: Отдаём ровно манифест и сегменты сетки, и ничего больше: каталог наружу не открыт.
_ASSET_RE: Final = re.compile(r"^(?:v\d+\.ts|index\.m3u8)$")
_TYPES: Final = {".m3u8": "application/vnd.apple.mpegurl", ".ts": "video/mp2t"}
_RANGE_RE: Final = re.compile(r"bytes=(\d*)-(\d*)")
#: ``TORRCAST_TRACE=1`` - раздача пишет в журнал каждый запрос приёмника (:meth:`_Handler._trace`).
TRACE: Final = bool(os.environ.get("TORRCAST_TRACE"))


class _Handler(http.server.BaseHTTPRequestHandler):
    """Манифест и сегменты: CORS на всех ответах, Range на сегментах, ноль лишних путей.

    Range обязателен: ресивер Q70D переспрашивает куски диапазонами (известная
    особенность приёмника), а без ``Access-Control-Allow-Origin: *`` Chromecast молча
    не играет.

    Манифест берётся не с диска, а у :class:`Feed`: он описывает весь фильм, а не то,
    что успело упаковаться. Запрос сегмента тоже уходит в ``Feed`` —
    именно там запрос неупакованного места превращается в перемотку.
    """

    protocol_version = "HTTP/1.1"
    server_version = "torrcast"
    root: Path = Path()
    feed: ClassVar[_Feed | None] = None
    #: Откуда взят кусок, который сейчас отдаём (:data:`torrcast.trace.PACKED` /
    #: :data:`torrcast.trace.WARMED`). Ставит :meth:`_read`, читает :meth:`_log_segment`.
    _src: str = "pack"

    def do_GET(self) -> None:
        self._serve(body=True)

    def do_HEAD(self) -> None:
        self._serve(body=False)

    def do_OPTIONS(self) -> None:
        self._head(204, 0, "text/plain")

    def _serve(self, body: bool) -> None:
        began = time.monotonic()
        name = self.path.split("?")[0].lstrip("/")
        if not _ASSET_RE.fullmatch(name):
            self._head(404, 0, "text/plain")
            return
        data = self._read(name)
        if data is None:
            self._head(404, 0, "text/plain")
            self._trace(name, began, "404")
            return
        self._trace(name, began, f"{len(data) / 1e6:.1f} МБ")
        suffix = ".m3u8" if name.endswith(".m3u8") else ".ts"
        ctype, total = _TYPES[suffix], len(data)
        span = self._range(total)
        if span is None:
            self._head(200, total, ctype)
        elif not span:
            self._head(416, 0, ctype, (("Content-Range", f"bytes */{total}"),))
            return
        else:
            first, last = span
            data = data[first : last + 1]
            self._head(206, len(data), ctype, (("Content-Range", f"bytes {first}-{last}/{total}"),))
        if body:
            sent = time.monotonic()
            self.wfile.write(data)
            took = time.monotonic() - sent
            self._sent(name, len(data), took)
            self._log_segment(name, began, len(data), took)

    def _read(self, name: str) -> bytes | None:
        """Тело ответа: манифест на весь фильм или сегмент, дождавшись упаковки.

        Заодно запоминает, ОТКУДА взят кусок (:attr:`_src`): решает это
        :meth:`Feed.segment`, а в след пишет :meth:`_log_segment`, и передать источник
        между ними больше нечем - наружу уходят одни байты.
        """
        if name.endswith(".m3u8"):
            return self.feed.manifest() if self.feed is not None else None
        path = self.root / name
        if self.feed is not None:
            found = self.feed.segment(segment_slot(name))
            if found is None:
                return None
            path = found
            trace = import_module("torrcast").trace

            self._src = trace.PACKED if found.parent == self.feed.out else trace.WARMED
        try:
            return path.read_bytes()
        except OSError:  # вычистило окном ровно между проверкой и чтением
            return None

    def _range(self, size: int) -> tuple[int, int] | tuple[()] | None:
        found = _RANGE_RE.fullmatch(self.headers.get("Range", "").strip())
        if not found:
            return None
        head, tail = found.group(1), found.group(2)
        if not head:
            first, last = max(0, size - int(tail or 0)), size - 1
        else:
            first, last = int(head), min(int(tail) if tail else size - 1, size - 1)
        return (first, last) if first <= last < size else ()

    def _head(self, code: int, length: int, ctype: str, extra: tuple[Any, ...] = ()) -> None:
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        # Кэшировать нельзя ничего: манифест дописывается на ходу, а после перепаковки
        # (перемотка назад глубже окна) под теми же именами сегментов лежит
        # уже другое место фильма - кэш приёмника показал бы старое.
        self.send_header("Cache-Control", "no-store")
        for key, value in extra:
            self.send_header(key, value)
        self.end_headers()

    def _trace(self, name: str, began: float, got: str) -> None:
        """Что попросил приёмник, сколько ждал ответа и что получил (``TORRCAST_TRACE=1``).

        Без этого подвис не измерить: снаружи он выглядит одинаково и
        когда он ждёт нас, и когда он перестал спрашивать вовсе, — а лечится это по-разному.
        """
        if not TRACE:
            return
        span = self.headers.get("Range", "")
        print(
            f"запрос {name}{' ' + span if span else ''} · ждал {time.monotonic() - began:.1f} с"
            f" · {got}",
            flush=True,
        )

    def _sent(self, name: str, size: int, seconds: float) -> None:
        """Сколько времени кусок **уезжал в телевизор** (``TORRCAST_TRACE=1``).

        Не то же самое, что :meth:`_trace`: тот меряет, сколько мы искали кусок, а этот —
        сколько заняла отдача по сети. Без этого числа не отличить «показ споткнулся о
        нарезку» от «канал до ТВ не тянет этот кусок»: с диска всё отдаётся мгновенно, а
        уезжает ровно столько, сколько позволяет линк.
        """
        if not TRACE or seconds <= 0:
            return
        print(
            f"отдал {name} · {size / 1e6:.1f} МБ за {seconds:.1f} с"
            f" · {size * 8 / seconds / 1e6:.1f} Мбит/с",
            flush=True,
        )

    def _log_segment(self, name: str, began: float, size: int, took: float) -> None:
        """Каждый отданный сегмент - в недельный след: номер, вес, время, ожидание, ИСТОЧНИК.

        Источник (:attr:`_src`) - живая упаковка или прогретое. Без него в ленте не видно
        главного: показ идёт кусками ДВУХ производителей, и разбор «почему приёмник
        споткнулся вот здесь» упирался в то, что по записи нельзя сказать, чей это был
        кусок и не сменился ли производитель ровно на этом месте.

        🔴 Это горячий путь. :func:`torrcast.trace.emit` только кладёт запись в очередь -
        ни ``open``, ни ``write``, ни ``flush`` тут не случается, показ не ждёт журнал.
        Отдельно от ``TORRCAST_TRACE`` (:meth:`_sent`): тот пишет в консоль по требованию, а
        след ведётся всегда. Манифест не пишем - он не сегмент и дёргается на каждый опрос.
        """
        if not name.endswith(".ts"):
            return

        journal().segment(
            slot=segment_slot(name),
            mb=size / 1e6,
            sent=took,
            wait=time.monotonic() - began - took,
            src=self._src,
        )

    def log_message(self, fmt: str, *args: Any) -> None:
        pass


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


def our_address(tv: str) -> str:
    """Наш адрес **с той стороны, с которой нас видит ТВ**, или пусто, если маршрута нет.

    У хоста может быть несколько интерфейсов — скажем, ``10.0.1.5`` в общей сети и
    ``10.0.100.5`` в сегменте телевизора. Ядро выбирает исходящий адрес по маршруту,
    поэтому спрашиваем его же: сокет никуда не подключается по-настоящему (UDP, ни одного
    пакета), но имя ему присваивается ровно то, которое ТВ увидит источником. Так поток
    идёт в одном L2, а не лишним хопом через SNAT маршрутизатора.
    """
    if not tv:
        return ""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((tv, 8009))
        return str(sock.getsockname()[0])
    except OSError:
        return ""
    finally:
        sock.close()


def hls_base(config: Config) -> str:
    """База URL, под которой ТВ забирает манифест и сегменты.

    Имени здесь нет и быть не должно: адрес собирается из транспорта, нашего адреса со
    стороны ТВ и порта — DNS в пути показа не участвует. ``hls_base_url`` в конфиге,
    если он задан, перебивает всё: это запасной выход на случай, когда прямой путь
    почему-то не работает.
    """
    if config.hls_base_url:
        return config.hls_base_url.rstrip("/")
    host = our_address(config.tv or "")
    if not host:
        raise InfraError(f"не вижу маршрута до ТВ {config.tv or '(адрес не задан)'}")
    return f"{config.transport}://{host}:{config.hls_port}"
