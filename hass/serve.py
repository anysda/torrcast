"""Шесть маршрутов моста поверх стандартной библиотеки. Новой зависимости тут нет.

Авторизации нет намеренно: продукт живёт в домашней сети и наружу не смотрит - ровно
как раздача HLS, которую забирает телевизор. Всё, что мост умеет, лежит в
:class:`hass.bridge.Bridge`; здесь только разбор запроса и коды ответа.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from hass.bridge import COMMANDS, VOLUME, Bridge
from hass.refused_error import RefusedError
from hass.say import SEEKBY
from torrcast.domain.json_value import JsonValue

#: Порт моста. Занят он бывает только другим таким же мостом.
PORT = 8479
#: Слушаем все интерфейсы: Home Assistant приходит из локальной сети, а не с петли.
ANY_INTERFACE = "0.0.0.0"
#: Потолок тела запроса: команды тут короткие, а читать чужой гигабайт мы не обязаны.
BODY_LIMIT = 64 * 1024
STATE, PLAY, CONTROL, NEXT = "/api/state", "/api/play", "/api/control", "/api/next"
SEARCH = "/api/search"
#: Картинку играющей картины раздаёт САМ серв: Home Assistant за ней наружу не ходит,
#: иначе её тянул бы клиент через сеть, где режут по SNI (:mod:`hass.posters`).
POSTER = "/api/poster/"
#: Команды пульта, которым число обязательно (``seekby`` - секунды со знаком).
NEEDS_ARG = (SEEKBY, VOLUME)


class _Handler(BaseHTTPRequestHandler):
    """Разбор запроса и коды ответа; мост кладёт сюда сервер (:func:`serve`)."""

    bridge: Bridge
    server_version = "torrcast-ha"
    sys_version = ""

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path.startswith(POSTER):
            self._picture(path[len(POSTER) :])
            return
        if path != STATE:
            self._answer(404, {"error": "not_found"})
            return
        self._answer(200, self.bridge.state())

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path not in (PLAY, CONTROL, NEXT, SEARCH):
            self._answer(404, {"error": "not_found"})
            return
        body = self._body()
        if body is None:
            self._answer(400, {"error": "bad_json"})
            return
        try:
            self._command(path, body)
        except RefusedError as refusal:
            self._answer(409, {"error": refusal.word})

    def do_PUT(self) -> None:
        """Чужой метод: маршруты знают ровно GET и POST."""
        self._answer(405, {"error": "method_not_allowed"})

    def do_DELETE(self) -> None:
        """Чужой метод: удалять у моста нечего."""
        self.do_PUT()

    def do_PATCH(self) -> None:
        """Чужой метод: править у моста нечего."""
        self.do_PUT()

    def log_message(self, format: str, *args: Any) -> None:
        """Строка запроса уходит в журнал процесса, а не в stderr россыпью."""
        print(f"{self.address_string()} {format % args}", flush=True)

    # ------------------------------------------------------------------ внутреннее

    def _command(self, path: str, body: dict[str, JsonValue]) -> None:
        """Развести POST по мосту; отказ моста поднимается выше словом."""
        if path == SEARCH:
            query = body.get("query")
            if not isinstance(query, str) or not query.strip():
                self._answer(400, {"error": "no_query"})
                return
            self._answer(200, {"results": self.bridge.search(query.strip())})
            return
        if path == PLAY:
            query = body.get("query")
            if not isinstance(query, str) or not query.strip():
                self._answer(400, {"error": "no_query"})
                return
            pick = body.get("pick")
            if pick is not None and (
                not isinstance(pick, int) or isinstance(pick, bool) or pick < 1
            ):
                self._answer(400, {"error": "bad_pick"})
                return
            self._answer(202, {"key": self.bridge.play(query.strip(), pick)})
            return
        if path == NEXT:
            self.bridge.next()
            self._answer(204, None)
            return
        command, arg = body.get("cmd"), body.get("arg")
        if command not in COMMANDS or command is None:
            self._answer(400, {"error": "bad_cmd"})
            return
        if command in NEEDS_ARG and not isinstance(arg, int | float):
            self._answer(400, {"error": "no_arg"})
            return
        self.bridge.control(str(command), float(arg) if isinstance(arg, int | float) else 0.0)
        self._answer(204, None)

    def _picture(self, name: str) -> None:
        """Байты картинки, которую мост уже нашёл; чужое имя отвечает тем же 404.

        Тела тут не собираются из имени и не читаются с диска по нему: имя приезжает
        снаружи, а мост знает только те картинки, которые нашёл сам.
        """
        found = self.bridge.poster(name)
        if found is None:
            self._answer(404, {"error": "not_found"})
            return
        body, kind = found
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, JsonValue] | None:
        """Тело запроса объектом; пустое тело - это пустой объект, кривое - ``None``."""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > BODY_LIMIT:
            return None
        try:
            parsed = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def _answer(self, code: int, body: dict[str, JsonValue] | None) -> None:
        """Один ответ на запрос: 204 идёт без тела вовсе."""
        self.send_response(code)
        if body is None:
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def serve(bridge: Bridge, port: int = PORT, host: str = ANY_INTERFACE) -> ThreadingHTTPServer:
    """Поднять сервер моста; слушать он начинает в потоке вызывающего."""
    handler = type("_BoundHandler", (_Handler,), {"bridge": bridge})
    return ThreadingHTTPServer((host, port), handler)
