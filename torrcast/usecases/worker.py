"""Показ внутри transient-юнита: своя раздача, свой приёмник и своя уборка на выходе.
Зовёт его ``ExecStart`` юнита ``torrcast-play`` через :func:`torrcast.commands.main`.
"""

# ruff: noqa: F821, F822

from __future__ import annotations

from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.journal import journal

__all__ = [
    "Supply",
    "TorrcastError",
    "TorrServer",
    "_cmd_worker",
    "_on_term",
    "_own_torrent",
    "_release_torrents",
    "_worker_loop",
    "contextlib",
    "detect_profile",
    "make_receiver",
    "signal",
    "tune_profile",
]

import contextlib
import signal

from torrcast.ports.module import module
from torrcast.usecases.stopped import _on_term
from torrcast.usecases.torrents import _own_torrent, _release_torrents
from torrcast.usecases.worker_loop import _worker_loop

for _module_name, _names in {
    "torrcast.cast": ("make_receiver",),
    "torrcast.state": ("load_config",),
    "torrcast.stream": (
        "PROBE_TIMEOUT",
        "Supply",
        "TorrServer",
    ),
}.items():
    _dependency = module(_module_name)
    globals().update({name: getattr(_dependency, name) for name in _names})
detect_profile = module("torrcast.profile").detect
tune_profile = module("torrcast.profile").tune


def _cmd_worker(key: str) -> int:
    """Показ внутри transient-юнита: своей раздачей, своей упаковкой и своим сторожем.

    Руками не зовётся — это ``ExecStart`` юнита ``torrcast-play``. Всё, что нужно знать о
    показе, лежит в записи состояния: magnet, файл, дорожка и позиция.

    Сериал юнит доигрывает сам: серия дошла до конца — сторож записал в
    состояние следующую, и цикл берёт её же раздачу и следующий файл, не спрашивая CLI.
    Серия была последней — состояние отмечает конец, цикл выходит, юнит гаснет чисто.

    ⚠️ **Приёмник один на весь юнит, а не на серию.** Соединение с ТВ живёт здесь и
    достаётся каждой серии готовым. Иначе получалось два сендера сразу: на стыке серий
    приложение приёмника намеренно не закрывается (:func:`_handover`), поэтому и сокет
    прошлой серии оставался жив, а следующая поднимала себе новый. Для приёмника оба —
    один и тот же ``sender-0`` (докстринг :class:`torrcast.cast.ChromecastReceiver`), и он
    отвечает новому пустым статусом. Замер на живом Q70D, стык s1e5→s1e6: два
    соединения в ``ss``, «LOAD не взяли (IDLE/ERROR)», «приёмник залип — закрываю
    приложение и соединение», экран пустой **15.3 с**.

    ⚠️ **Раздача уезжает вместе с показом.** Юнит - единственный её хозяин: он её поднял,
    он один из неё читает, и кроме него о ней не знает никто - в списке службы она, к
    слову, видна весь показ (проверено на TorrServer MatriX.142.2), но своей её там
    ничто не называет. Пока уборки тут не было, каждый сеанс оставлял по раздаче
    навсегда - до перезапуска TorrServer, - и они копились ровно в той службе, которая
    падает по таймеру тем вероятнее, чем их больше (:data:`torrcast.commands.MAX_LIVE`).
    Убирается своё и только своё, по хэшам, которые юнит завёл сам, и на любом выходе:
    штатный конец, ошибка и SIGTERM от ``cast stop`` (он приходит как
    :class:`torrcast.usecases.stopped._Stopped` и раскручивает ``finally`` наравне с
    прочими). Прогрев следующей серии тут не жертва: он идёт по этой же раздаче и
    кончается вместе с юнитом.
    """
    journal().mark("процесс показа")
    config = load_config()
    # Профиль приёмника юнит выбирает себе сам, а не получает от CLI: юнит переживает
    # смену серии и живёт своей жизнью, а опрос паспорта стоит одного HTTP к устройству.
    chosen = detect_profile(config)
    config = tune_profile(config, chosen.profile)
    print(f"профиль приёмника: {chosen.profile.title} - {chosen.how}", flush=True)
    # SIGTERM от `cast stop` обязан пройти через finally: иначе позиция не запишется.
    signal.signal(signal.SIGTERM, _on_term)
    torrserver = TorrServer(config.torrserver_url)
    receiver = make_receiver(
        config.receiver,
        config.tv or "",
        config.hls_cert if config.transport == "https" else "",
        profile=chosen.profile,
    )
    supply = Supply(TorrServer(config.torrserver_url, timeout=PROBE_TIMEOUT))
    #: Хэши, которые подняли МЫ, - по ним и только по ним пойдёт уборка на выходе.
    mine: list[str] = []
    try:
        return _worker_loop(config, key, torrserver, receiver, supply, mine, chosen.profile)
    finally:
        gone = _release_torrents(config, mine)
        # Раздачи больше нет - и записи о ней тоже: следующему запуску убирать нечего.
        # А вот если служба смолчала, раздача жива, и запись о ней - единственное, чем её
        # потом снести (:func:`_release_orphans`): такой хэш забывать нельзя.
        if not mine or mine[-1] in gone:
            with contextlib.suppress(TorrcastError):  # не вправе провалить сам выход
                _own_torrent(key, "")
