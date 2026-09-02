"""Точка входа ``torrcast-ha``: собрать продукт, объявиться в сети и слушать порт.

🔴 Среды выбора мост НЕ подставляет, и это проверено, а не предположено. Без ``--menu``
:func:`torrcast.usecases.choice.enter_take.enter_take` ни на одной ветке не возвращает
``asks``, а вопрос номера (:func:`torrcast.usecases.choice._pick_plan._pick_plan`)
задаётся только под ним - то есть штатный ``cast <запрос>`` выбирает картину сам и
терминала не спрашивает. Флаг в запрос не попадает: мост зовёт ``run_cast([query])``
одним позиционным словом.
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
