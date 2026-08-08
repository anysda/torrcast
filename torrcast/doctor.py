"""``cast doctor`` — самопроверка окружения одной командой.

Проверяется ровно то, обо что уже спотыкались: терминал и локаль (кириллица в
вопросах), Prowlarr и TorrServer (есть чем искать и что раздавать), адрес ТВ и его порт
8009 (есть кому играть), путь до ТВ и адрес раздачи, ffmpeg с ``-readrate_initial_burst``
и серт, если кто-то включил https. Вердикт по-русски, без трейсбеков и без ``⚠``.

Каждая проверка возвращает пару ``(строка, всё ли хорошо)``: ``cast doctor`` печатает
строки и завершается кодом 2, если хоть где-то «плохо».
"""

from __future__ import annotations

import locale
import os
import socket
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from torrcast.console import iutf8 as _iutf8
from torrcast.console import stdin_is_tty
from torrcast.state import Config

__all__ = ["checkup"]

Line = tuple[str, bool]
#: Порт управления Chromecast: открыт даже в standby, коннект будит ТВ.
CAST_PORT = 8009
_TIMEOUT = 5.0


def checkup(config: Config) -> Iterator[Line]:
    """Все проверки по порядку: сначала консоль, потом инфраструктура, потом ТВ."""
    yield _terminal()
    yield _locale()
    yield _tools()
    yield _prowlarr(config)
    yield _torrserver(config)
    yield from _tv(config)
    yield _hls(config)


def _ok(text: str) -> Line:
    return f"ок      {text}", True


def _warn(text: str) -> Line:
    return f"внимание {text}", True


def _bad(text: str) -> Line:
    return f"плохо   {text}", False


def _terminal() -> Line:
    """Терминал и режим ``IUTF8``: без него ssh ломает забой на кириллице."""
    if not stdin_is_tty():
        return _warn("терминала нет (запуск не интерактивный) - вопросы возьмут дефолты")
    import termios

    try:
        mode = termios.tcgetattr(sys.stdin.fileno())
    except (termios.error, ValueError, OSError):
        return _warn("терминал есть, но режим ввода не читается - кириллица не проверена")
    was = bool(int(mode[0]) & _iutf8())
    how = "уже включён" if was else "выключен, включаем сами на время команды"
    return _ok(f"терминал: pty есть, IUTF8 {how} - кириллица в вопросах работает")


def _locale() -> Line:
    """Кодировка: русские названия и ключи состояния должны переживать запись в файл."""
    encoding = (locale.getpreferredencoding(False) or "").lower()
    names = ("LANG", "LC_ALL", "LC_CTYPE")
    env = " ".join(f"{n}={os.environ[n]}" for n in names if n in os.environ)
    if "utf" in encoding or "utf" in env.lower():
        return _ok(f"локаль: {encoding or 'utf-8'} {('(' + env + ')') if env else ''}".strip())
    return _bad(f"локаль {encoding or '?'} не UTF-8 - русские названия побьются ({env or 'пусто'})")


def _tools() -> Line:
    """ffmpeg/ffprobe и поддержка ``-readrate_initial_burst`` (нужен ffmpeg ≥ 6.1)."""
    try:
        done = subprocess.run(
            ["ffmpeg", "-hide_banner", "-h", "full"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return _bad("ffmpeg не запускается - упаковывать поток нечем")
    version = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10, check=False
    ).stdout.splitlines()
    head = version[0][:60] if version else "ffmpeg"
    if "readrate_initial_burst" not in done.stdout:
        return _bad(f"{head}: нет -readrate_initial_burst - старт будет медленным")
    return _ok(f"{head}, -readrate_initial_burst есть")


def _prowlarr(config: Config) -> Line:
    if not config.prowlarr_apikey:
        return _bad("Prowlarr: apikey пуст - искать нечем, перезапусти ./install.sh")
    payload = _json(f"{config.prowlarr_url}/api/v1/health", {"X-Api-Key": config.prowlarr_apikey})
    if payload is None:
        return _bad(f"Prowlarr не отвечает ({config.prowlarr_url}) - поиска не будет")
    indexers = _json(f"{config.prowlarr_url}/api/v1/indexer", {"X-Api-Key": config.prowlarr_apikey})
    count = len(indexers) if isinstance(indexers, list) else 0
    if not count:
        return _bad(f"Prowlarr отвечает, но индексеров ноль ({config.prowlarr_url})")
    return _ok(f"Prowlarr отвечает, индексеров {count} ({config.prowlarr_url})")


def _torrserver(config: Config) -> Line:
    import requests

    try:
        response = requests.get(f"{config.torrserver_url}/echo", timeout=_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        return _bad(f"TorrServer не отвечает ({config.torrserver_url}) - раздачи не будет")
    return _ok(f"TorrServer {response.text.strip()[:20]} ({config.torrserver_url})")


def _tv(config: Config) -> Iterator[Line]:
    """Адрес ТВ, маршрут до него и порт 8009 — он открыт даже у спящего Q70D."""
    from torrcast.stream import our_address

    if not config.tv:
        yield _bad("адрес ТВ не задан: cast --tv <ip>")
        return
    if config.receiver == "mock":
        yield _warn(f"приёмник mock ({config.tv}) - каста наружу нет, это режим проверки")
        return
    ours = our_address(config.tv)
    if not ours:
        yield _bad(f"до ТВ {config.tv} нет маршрута - каст не уйдёт")
        return
    yield _ok(f"ТВ {config.tv} виден с нашей ноги {ours}")
    sock = socket.socket()
    sock.settimeout(_TIMEOUT)
    try:
        sock.connect((config.tv, CAST_PORT))
        yield _ok(f"порт {CAST_PORT} на ТВ открыт - приёмник примет показ")
    except OSError as exc:
        yield _bad(f"порт {CAST_PORT} на ТВ не открылся ({exc.strerror or exc}) - ТВ обесточен?")
    finally:
        sock.close()


def _hls(config: Config) -> Line:
    """Адрес раздачи и, если кто-то включил https, свежесть серта."""
    from torrcast import TorrcastError
    from torrcast.stream import hls_base

    try:
        base = hls_base(config)
    except TorrcastError as exc:
        return _bad(f"адрес раздачи не собирается: {exc}")
    if config.transport != "https":
        return _ok(f"раздача {base} - ни серта, ни DNS в пути показа")
    left = _cert_days(config.hls_cert)
    if left is None:
        return _bad(f"раздача {base}, но серт {config.hls_cert} не читается")
    if left < 7:
        return _bad(f"раздача {base}, серту осталось {left} дн - показ вот-вот отвалится")
    return _ok(f"раздача {base}, серту осталось {left} дн")


def _cert_days(path: str) -> int | None:
    """Сколько дней осталось серту; ``None`` — файла нет или он не разбирается."""
    import ssl
    from typing import Any

    decode: Any = getattr(ssl, "_ssl", None)  # штатного API «прочитать серт с диска» нет
    if decode is None:
        return None
    try:
        until = str(decode._test_decode_cert(str(Path(path)))["notAfter"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    stamp = datetime.strptime(until, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    return (stamp - datetime.now(UTC)).days


def _json(url: str, headers: dict[str, str]) -> object | None:
    import requests

    try:
        response = requests.get(url, headers=headers, timeout=_TIMEOUT)
        response.raise_for_status()
        payload: object = response.json()
        return payload
    except (requests.RequestException, ValueError):
        return None
