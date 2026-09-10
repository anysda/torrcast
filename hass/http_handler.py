"""Семь маршрутов моста поверх стандартной библиотеки. Новой зависимости тут нет.

Авторизации нет намеренно: продукт живёт в домашней сети и наружу не смотрит - ровно
как раздача HLS, которую забирает телевизор. Всё, что мост умеет, лежит в
:class:`hass.bridge.Bridge`; здесь только разбор запроса и коды ответа.

Восьмой маршрут сюда не дописывается: страница в браузере объявляет свои маршруты
таблицей (:func:`web.routes.routes`), и спрашивают её ПОСЛЕ этих семи, которые не
меняются. Ответ ``None`` от :func:`web.answer_for.answer_for` значит «путь не её», и
чужой путь получает тот же 404, что и до появления страницы.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Any

from hass.bridge import Bridge
from hass.http_routes import (
    BODY_LIMIT,
    COMMANDS,
    CONTROL,
    NEEDS_ARG,
    NEXT,
    PLAY,
    POSTER,
    RESUME,
    SEARCH,
    STATE,
)
from hass.play_extras import play_extras
from hass.refused_error import RefusedError
from torrcast.domain.json_value import JsonValue
from web.answer_for import answer_for


class _Handler(BaseHTTPRequestHandler):
    """Разбор запроса и коды ответа; мост кладёт сюда сервер (:func:`hass.serve.serve`)."""

    bridge: Bridge
    server_version = "torrcast-ha"
    sys_version = ""

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path.startswith(POSTER):
            self._picture(path[len(POSTER) :])
            return
        if path == STATE:
            self._answer(200, self.bridge.state())
            return
        self._offer({})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        body = self._body()
        if body is None:
            self._answer(400, {"error": "bad_json"})
            return
        if path not in (PLAY, CONTROL, NEXT, SEARCH, RESUME):
            self._offer(body)
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
            if body.get("progressive") is True:
                # Опт-ин (TC-1126): страница читает ``X-Torrcast-Partial``, HA - нет.
                results, partial = self.bridge.search_progress(query.strip())
                headers = {"X-Torrcast-Partial": "1" if partial else "0"}
                self._answer(200, {"results": results}, headers=headers)
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
            extras = play_extras(body)
            if isinstance(extras, str):
                self._answer(400, {"error": extras})
                return
            self._answer(202, {"key": self.bridge.play(query.strip(), pick, **extras)})
            return
        if path == RESUME:
            self._answer(202, {"key": self.bridge.resume()})
            return
        if path == NEXT:
            self.bridge.next(body)
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

    def _offer(self, body: dict[str, JsonValue]) -> None:
        """Спросить таблицу страницы последней; не её путь остаётся прежним 404."""
        found = answer_for(self.command, self.path, body)
        if found is None:
            self._answer(404, {"error": "not_found"})
            return
        self.send_response(found.code)
        for name, value in found.headers():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(found.body)

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

    def _answer(
        self, code: int, body: dict[str, JsonValue] | None, *, headers: dict[str, str] | None = None
    ) -> None:
        """Один ответ на запрос: 204 идёт без тела вовсе; ``headers`` - для превью (TC-1126)."""
        self.send_response(code)
        if body is None:
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)
