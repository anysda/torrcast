"""Раздача самой страницы (``GET /``) и её файлов (``GET /static/*``)."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from web.answer import Answer
from web.refusal import refusal
from web.request import Request

#: Каталог файлов страницы. Он лежит внутри пакета и уезжает вместе с ним в колесо.
STATIC: Final = Path(__file__).resolve().parent / "static"
#: Начало пути, за которым идёт имя файла.
PREFIX: Final = "/static/"
#: Чем подписан файл. Браузер разбирает страницу по этому заголовку, а не по имени:
#: с ``application/octet-stream`` он предложит скачать таблицу стилей вместо показа.
KINDS: Final = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}
#: Чем подписано всё остальное: молчаливая догадка о чужом типе хуже честной байты.
FALLBACK: Final = "application/octet-stream"


def serve_static(request: Request) -> Answer:
    """Отдать файл страницы; чужое имя и выход из :data:`STATIC` отвечают тем же 404."""
    name = "index.html" if request.path == "/" else request.path[len(PREFIX) :]
    found = _inside(name)
    if found is None:
        return refusal(404, "not_found")
    return Answer(200, found.read_bytes(), KINDS.get(found.suffix, FALLBACK))


def _inside(name: str) -> Path | None:
    """Файл внутри :data:`STATIC` или ``None``: наружу ``../`` не выпускается.

    Сравниваются РАЗРЕШЁННЫЕ пути, а не строки. Строку чистит каждый по-своему, и
    вычеркнутая по буквам ``../`` возвращается кодировкой (``%2e%2e``) или второй парой;
    разрешённый же путь у обхода один и тот же, и лежит он вне каталога страницы.
    Ссылка наружу считается тем же выходом: разбирает её тот же ``resolve``.
    """
    if not name:
        return None
    full = (STATIC / name).resolve()
    if full != STATIC and STATIC not in full.parents:
        return None
    return full if full.is_file() else None
