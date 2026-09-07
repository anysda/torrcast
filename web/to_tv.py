"""Переносит идущий показ на ТВ: ``POST /api/to-tv`` (ТЗ §7.5).

Поток, упаковка и перекод не трогаются: приёмнику ТВ достаётся тот же ``url``, что уже
лежит в ящике вкладки (:mod:`web.box`), и та же секунда, на которой стоит показ - нового
показа тут не поднимается.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.browser.read_web_position import read_web_position
from torrcast.adapters.browser.write_web_position import write_web_position
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.system_clock import CLOCK
from torrcast.domain.position import Position
from torrcast.usecases.playback.hls_root import hls_root
from web.answer import Answer
from web.refusal import refusal
from web.request import Request
from web.tv_session import SESSION


def to_tv(request: Request) -> Answer:
    """Позвать приёмник ``config.tv`` на уже идущий показ вкладки."""
    del request  # тело запросу не нужно - всё берётся из ящика вкладки и настроек
    config = load_config()
    address = config.tv or ""
    if not address:
        return refusal(409, "no_tv")
    out = hls_root(config.hls_dir)
    box = read_web_box(out)
    url = str(box.get("url", ""))
    if not url:
        return refusal(409, "nothing_playing")
    # Позиция от вкладки свежее позиции ящика, только пока она про ЭТОТ сеанс: чужой или
    # прошлый ключ был бы враньём о секунде показа (тем же основанием, что и `web.position`).
    record = read_web_position(out)
    at = float(box.get("at", 0.0))
    if record is not None and record.get("key") == box.get("key"):
        at = float(record.get("pos", at))
    key = str(box.get("key", ""))
    SESSION.start(address, str(box.get("title", "")), url, at, echo=_echo(out, key), key=key)
    return Answer(202, b"")


def _echo(out: Path, key: str) -> Callable[[Position], None]:
    """Класть место ТВ туда же, откуда продукт читает место вкладки (ТЗ §7.5.3).

    Источник секунды на время каста один, и это приёмник ТВ: вкладка свою плёнку не
    останавливает (она подстраивается под ТВ, §4.5), и оба писателя в один файл двигали
    бы закладку по очереди - то на секунду ТВ, то на секунду вкладки. Отсюда и запрет
    вкладке писать, пока каст жив (:func:`web.position.position`).

    Ключ берётся ящика, а не приёмника: файл места читается только вместе с ящиком, и
    чужой ключ в нём означал бы «места нет» (:mod:`torrcast.adapters.browser.
    browser_receiver`).
    """

    def heard(spot: Position) -> None:
        # Ящик уехал под другой показ - слушатель умолкает и отдаёт файл вкладке: иначе
        # он писал бы место ТВ под ключом, которого в ящике уже нет, а новая картина
        # осталась бы вовсе без места (:meth:`web.tv_session.TvSession.owns`).
        if not SESSION.owns(str(read_web_box(out).get("key", ""))):
            return
        write_web_position(
            out,
            key=key,
            pos=spot.pos,
            dur=spot.dur,
            phase="playing" if spot.playing else "paused",
            wall=CLOCK.wall(),
        )

    return heard
