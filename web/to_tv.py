"""Переносит идущий показ на ТВ: ``POST /api/to-tv`` (ТЗ §7.5).

Поток, упаковка и перекод не трогаются: приёмнику ТВ достаётся тот же ``url``, что уже
лежит в ящике вкладки (:mod:`web.box`), и та же секунда, на которой стоит показ - нового
показа тут не поднимается. Профиль приёмника и контейнер кусков - тоже из ящика: ТВ
зовётся тем же LOAD, что и прямой показ на него.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.browser.read_web_position import read_web_position
from torrcast.adapters.browser.write_web_position import write_web_position
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.system_clock import CLOCK
from torrcast.domain.by_key import by_key
from torrcast.domain.position import Position
from torrcast.domain.segment_container import FMP4, MPEGTS, SegmentContainer
from torrcast.usecases.playback.hls_root import hls_root
from web.answer import Answer
from web.refusal import refusal
from web.request import Request
from web.tv_session import SESSION

#: Контейнеры, которые ящик может назвать; чужое слово - «не известен», а не mpegts.
_CONTAINERS: Final[dict[str, SegmentContainer]] = {FMP4: FMP4, MPEGTS: MPEGTS}


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
    # Каст живёт, пока ящик держит ЭТОТ показ: стоп чистит ящик, и ТВ закрывается сам.
    alive = lambda: str(read_web_box(out).get("key", "")) == key  # noqa: E731
    title = str(box.get("title", ""))
    # 🔴 Профиль и контейнер - те, которыми показ упакован: с осторожными умолчаниями LOAD
    # «На ТВ» расходился с прямым показом на ТВ (подсказки mpegts на куски fmp4).
    profile = by_key(str(box.get("profile", "")))
    container = _CONTAINERS.get(str(box.get("container", "")))
    echo = _echo(out, key)
    SESSION.start(address, title, url, at, echo, key, alive, profile=profile, container=container)
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
