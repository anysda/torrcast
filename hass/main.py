"""Точка входа ``torrcast-ha``: собрать продукт, объявиться в сети и слушать порт.

🔴 Среды выбора мост НЕ подставляет, и это проверено, а не предположено. Без ``--menu``
:func:`torrcast.usecases.choice.enter_take.enter_take` ни на одной ветке не возвращает
``asks``, а список с вопросом (:func:`torrcast.usecases.choice._pick_plan._pick_plan`)
поднимается только под ним - то есть штатный ``cast <запрос>`` выбирает картину сам и
терминала не спрашивает. Флага ``--menu`` в запросе моста нет ни на одной ручке.

А вот ``--pick N`` мост шлёт: им играется картина, выбранная в карточке Home Assistant
из выдачи ``POST /api/search`` (:meth:`hass.bridge.Bridge.play`). Ветка номера в
:func:`_pick_plan` терминала тоже не спрашивает - она сверяет номер с запомненным
порядком и говорит взятую картину вслух. Порядок под этот номер кладёт сам мост, тем
же механизмом, что и меню консоли (:mod:`hass.searching`).
"""

from __future__ import annotations

import os
import signal
import threading
from types import FrameType

from hass.announce import Announce
from hass.bridge import Bridge
from hass.serve import PORT, serve
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.version import __version__
from torrcast.ports.abandon.slot import install as install_abandon
from torrcast.runtime.wire import wire

#: ``TORRCAST_HA_PORT=<порт>`` - слушать не 8479. Того же рода переопределение, что и
#: ``TORRCAST_STATE``: щуп на занятой машине не имеет права занять боевой порт.
PORT_ENV = "TORRCAST_HA_PORT"


def _port() -> int:
    """Порт моста: настроенный или боевой."""
    try:
        return int(os.environ.get(PORT_ENV) or PORT)
    except ValueError:
        return PORT


def main() -> int:
    """Служить, пока не попросят уйти; уходя, снять запись из mDNS.

    🔴 Главный поток остаётся за командами, а не за сервером, и это единственная
    рабочая раскладка: ``cast`` ставит на время команды свой обработчик сигнала, а из
    рабочего потока это не делается вовсе (:mod:`hass.bridge`). Запросы карточки при
    этом не ждут показа - их разбирает сервер в своём потоке.
    """
    wire()
    bridge = Bridge()
    # Про отказ человека знает только мост: у консоли отказываться некому. Назначается
    # это здесь, в композиционном корне, а не самим мостом.
    install_abandon(bridge.abandoned)
    chosen = _port()
    server = serve(bridge, chosen)
    announce = Announce(chosen, version=__version__, tv=load_config().tv or "")
    announce.open()

    def leave(number: int, frame: FrameType | None) -> None:
        del number, frame
        bridge.stop()
        # Сервер останавливается из отдельного потока: просить цикл остановиться из
        # его же обработчика - это тупик.
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, leave)
    signal.signal(signal.SIGINT, leave)
    threading.Thread(target=server.serve_forever, name="torrcast-ha-http", daemon=True).start()
    try:
        bridge.run()
    finally:
        announce.close()
        server.shutdown()
        server.server_close()
        bridge.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - запуск руками, а не юнитом
    raise SystemExit(main())
