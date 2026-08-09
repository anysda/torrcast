"""``cast doctor`` — самопроверка окружения одной командой.

Проверяется ровно то, обо что уже спотыкались: терминал и локаль (кириллица в
вопросах), Prowlarr и TorrServer (есть чем искать и что раздавать), метапоиск, на
котором держится западный и аниме-хвост каталога, адрес ТВ и его порт 8009 (есть кому
играть), путь до ТВ и адрес раздачи, mDNS-путь поиска приёмников (будут ли имена),
ffmpeg с ``-readrate_initial_burst`` и серт, если кто-то включил https. Вердикт
по-русски, без трейсбеков и без ``⚠``.

Каждая проверка возвращает пару ``(строка, всё ли хорошо)``: ``cast doctor`` печатает
строки и завершается кодом 2, если хоть где-то «плохо».
"""

from __future__ import annotations

import locale
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from torrcast.console import iutf8 as _iutf8
from torrcast.console import stdin_is_tty
from torrcast.scan import CAST_PORT
from torrcast.state import Config

__all__ = ["CAST_PORT", "checkup"]

Line = tuple[str, bool]
#: Метапоиск, на котором держится примерно половина каталога - весь западный хвост и
#: аниме: прямые трекеры из установки его не перекрывают. Без него поиск продолжает
#: работать, поэтому это «внимание», а не «плохо», - но молчать о нём нельзя, иначе
#: урезанная выдача выглядит как пустой поиск без причины.
KEY_INDEXER = "Knaben"
_TIMEOUT = 5.0
#: Во сколько раз память службы раздачи больше кэша, который она держит. Замер: кэш лежит
#: в куче Go, и рядом с каждым куском живёт его копия в работе плюс мусор, который
#: сборщик забирает уже потом. Тот же множитель считает размер кэша в ``install.sh``
#: (``TS_MEM_OVERHEAD``) - если правишь тут, правь и там.
CACHE_OVERHEAD = 2
#: Байты, которые кэшу не отдают: система, python показа, два ffmpeg, сегменты в
#: /dev/shm (``install.sh``: ``TS_MEM_RESERVE``).
CACHE_RESERVE = 1792 * 1024 * 1024


def checkup(config: Config) -> Iterator[Line]:
    """Все проверки по порядку: сначала консоль, потом инфраструктура, потом ТВ."""
    yield _terminal()
    yield _locale()
    yield _tools()
    yield from _prowlarr(config)
    yield _torrserver(config)
    yield _cache(config)
    yield from _tv(config)
    yield _mdns()
    yield _profile(config)
    yield _hls(config)
    yield _shelves()
    yield _trace()


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


def _prowlarr(config: Config) -> Iterator[Line]:
    """Prowlarr: отвечает ли, сколько индексеров и жив ли тот, что весит за половину."""
    if not config.prowlarr_apikey:
        yield _bad("Prowlarr: apikey пуст - искать нечем, перезапусти ./install.sh")
        return
    headers = {"X-Api-Key": config.prowlarr_apikey}
    payload = _json(f"{config.prowlarr_url}/api/v1/health", headers)
    if payload is None:
        yield _bad(f"Prowlarr не отвечает ({config.prowlarr_url}) - поиска не будет")
        return
    indexers = _json(f"{config.prowlarr_url}/api/v1/indexer", headers)
    count = len(indexers) if isinstance(indexers, list) else 0
    if not count:
        yield _bad(f"Prowlarr отвечает, но индексеров ноль ({config.prowlarr_url})")
        return
    yield _ok(f"Prowlarr отвечает, индексеров {count} ({config.prowlarr_url})")
    yield _key_indexer(indexers)


def _enabled_names(payload: object) -> list[str]:
    """Имена включённых индексеров из ответа Prowlarr; выключенный не ищет."""
    if not isinstance(payload, list):
        return []
    names: list[str] = []
    for entry in payload:
        if not isinstance(entry, dict) or not entry.get("enable", True):
            continue
        name = entry.get("name")
        if isinstance(name, str):
            names.append(name)
    return names


def _key_indexer(payload: object) -> Line:
    """Метапоиск с половиной каталога: есть и включён - или выдача будет неполной."""
    needle = KEY_INDEXER.lower()
    if any(needle in name.lower() for name in _enabled_names(payload)):
        return _ok(f"{KEY_INDEXER} на месте - западные релизы и аниме в каталоге есть")
    return _warn(
        f"{KEY_INDEXER} не заведён или выключен - искать можно, но западных релизов и "
        "аниме в выдаче будет заметно меньше; вернуть - ./install.sh"
    )


def _torrserver(config: Config) -> Line:
    import requests

    try:
        response = requests.get(f"{config.torrserver_url}/echo", timeout=_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        return _bad(f"TorrServer не отвечает ({config.torrserver_url}) - раздачи не будет")
    return _ok(f"TorrServer {response.text.strip()[:20]} ({config.torrserver_url})")


def _cache(config: Config) -> Line:
    """Кэш раздачи: сколько его, во что он обойдётся памяти и влезает ли это в машину.

    Строка тут потому, что искать это число однажды пришлось с гипервизора: кэш в 4 ГиБ
    на 8-гигабайтной машине вырастал в 7.45 ГБ RSS, и она вставала колом на четвёртой
    минуте показа - без ssh, без журнала. Размер кэша теперь считается от фактической
    памяти (:func:`machine_memory`), и его видно отсюда.
    """
    sets = _settings(config.torrserver_url)
    if not isinstance(sets, dict):
        return _warn("настройки TorrServer не читаются - размер кэша неизвестен")
    size = int(sets.get("CacheSize") or 0)
    total = machine_memory()
    where = "на диске" if sets.get("UseDisk") else "в RAM"
    weight = size if sets.get("UseDisk") else size * CACHE_OVERHEAD
    text = (
        f"кэш раздачи {_gib(size)} {where}, под показом это ~{_gib(weight)} памяти "
        f"из {_gib(total)} машины"
    )
    if weight + CACHE_RESERVE > total:
        return _bad(f"{text} - не влезает: показ уронит машину, переставь install.sh")
    return _ok(text)


def machine_memory() -> int:
    """Память, которая есть у ЭТОЙ машины, байты - с оглядкой на cgroup.

    В контейнере ``/proc/meminfo`` показывает не то, что дадут: потолок стоит на cgroup,
    и упирается показ именно в него. Берём меньшее из двух.
    """
    total = 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return 0
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            limit = int(Path(path).read_text().strip())
        except (OSError, ValueError):
            continue
        if 0 < limit < total:
            total = limit
    return total


def _gib(size: int) -> str:
    return f"{size / 1024**3:.1f} ГиБ"


def _tv(config: Config) -> Iterator[Line]:
    """Адрес ТВ, маршрут до него и порт 8009 — он открыт даже у спящего Q70D."""
    from torrcast.stream import our_address

    if not config.tv:
        yield _bad("адрес ТВ не задан: cast --tv (найдёт приёмники сам) или cast --tv <ip>")
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


def _mdns() -> Line:
    """Путь поиска приёмников по mDNS: жив ли он, и что именно не так, если имен нет.

    Строка тут из-за старой ложной тревоги: поиск молча возвращал пустой список, и
    «в сети нет мультикаста» было не отличить от «запустили системным python без
    zeroconf». Теперь причину различает :func:`torrcast.scan.by_mdns`, а doctor её
    показывает. Тишина в эфире и отказ сети - «внимание», а не «плохо»: адреса найдёт
    обход подсетей, mDNS даёт только имена. Отсутствующий модуль - уже «плохо»: это
    сломанная установка, а не свойство сети.
    """
    from torrcast.scan import by_mdns

    heard = by_mdns()
    if heard.devices:
        names = ", ".join(device.title for device in heard.devices[:3])
        count = len(heard.devices)
        return _ok(f"mDNS: услышал приёмников {count} ({names}) - имена в поиске будут")
    if heard.reason == "module":
        return _bad(heard.note)
    return _warn(heard.note)


def _profile(config: Config) -> Line:
    """Профиль приёмника: по какому набору порогов будет играть показ и откуда он взялся.

    Строка тут ровно потому, что искать это однажды пришлось бы с гипервизора: пороги
    веса куска, терпения и битрейта у двух приёмников разные, и «почему на этом
    телевизоре перекодируется всё подряд» без этой строки не отвечается ничем.

    Осторожный профиль на незнакомом приёмнике - не беда, а замысел: он играет медленнее,
    но играет. Поэтому «внимание» здесь только тогда, когда осторожный набор достался
    приёмнику, которого мы не смогли спросить, - это единственный случай, где строка
    подсказывает человеку, что можно сделать лучше.
    """
    from torrcast.profile import CAUTIOUS, detect

    chosen = detect(config)
    text = f"профиль приёмника: {chosen.profile.title} - {chosen.how}"
    if chosen.profile is CAUTIOUS and chosen.how.endswith("беру осторожный"):
        return _warn(f"{text}; назвать руками - ключ receiver_profile в конфиге")
    return _ok(text)


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


def _shelves() -> Line:
    """Кэши карт опорных кадров и паспортов: сколько записей и сколько это весит.

    Строка одна и всегда «ок»: это не проверка, а цифра. Расти без предела полки больше
    не могут (:func:`torrcast.stream._trim`), но потолок молчаливый, а инструмент живёт
    годами - и место на диске лучше видеть числом, чем узнавать о нём от файловой
    системы. Потолки печатаются рядом, чтобы «много» и «мало» читались без документации.
    """
    from torrcast.state import state_path
    from torrcast.stream import KEYS_KEPT, PROBE_KEPT, shelf_weight

    shelf = state_path().parent
    keys, keys_weight = shelf_weight(shelf / "keys")
    probe, probe_weight = shelf_weight(shelf / "probe")
    return _ok(
        f"кэши в {shelf}: карт {keys}/{KEYS_KEPT} ({keys_weight / 1e6:.1f} МБ), "
        f"паспортов {probe}/{PROBE_KEPT} ({probe_weight / 1e6:.1f} МБ)"
    )


def _trace() -> Line:
    """Недельный след: пишется ли он вообще, свежий ли и сколько занимает.

    Проверка не про показ, а про диагностику: пустая или протухшая лента означает, что
    разбирать прошлый сеанс будет нечем, и узнать об этом лучше заранее, а не тогда,
    когда что-то уже сломалось. Сама по себе лента показу не нужна - поэтому «внимание».
    """
    from torrcast import trace

    found, newest, total = trace.health()
    if not found:
        return _warn(f"следа нет в {trace.log_dir()} - `cast log` покажет пустоту")
    days = (time.time() - newest) / 86400
    size = f"{total / 1e6:.1f} МБ"
    if days > trace.RETAIN_DAYS:
        return _warn(f"след есть ({size}), но последняя запись {days:.0f} дн назад")
    return _ok(f"след {size}, последняя запись {_ago(time.time() - newest)} назад")


def _ago(seconds: float) -> str:
    if seconds < 3600:
        return f"{seconds / 60:.0f} мин"
    if seconds < 86400:
        return f"{seconds / 3600:.0f} ч"
    return f"{seconds / 86400:.0f} дн"


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


def _settings(url: str) -> object | None:
    """Настройки TorrServer. Спрашиваются POST-ом с телом - GET на этот адрес молчит."""
    import requests

    try:
        response = requests.post(f"{url}/settings", json={"action": "get"}, timeout=_TIMEOUT)
        response.raise_for_status()
        payload: object = response.json()
        return payload
    except (requests.RequestException, ValueError):
        return None


def _json(url: str, headers: dict[str, str]) -> object | None:
    import requests

    try:
        response = requests.get(url, headers=headers, timeout=_TIMEOUT)
        response.raise_for_status()
        payload: object = response.json()
        return payload
    except (requests.RequestException, ValueError):
        return None
