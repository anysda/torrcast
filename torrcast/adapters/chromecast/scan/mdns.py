"""Итог слушания mDNS: приёмники и РАЗЛИЧИМАЯ причина, если услышать не вышло.

Собирает его :func:`by_mdns`, читают поиск приёмников и щуп служб."""

from __future__ import annotations

from dataclasses import dataclass, field

from torrcast.adapters.chromecast.scan.device import Device


@dataclass(frozen=True, slots=True)
class Mdns:
    """Итог слушания mDNS: приёмники и различимая причина, если услышать не вышло.

    Пустой список без причины однажды уже родил ложную тревогу: поиск молчал, и «в
    сети нет мультикаста» было не отличить от «в этом python нет zeroconf». Поэтому
    причина - поле результата, а не подавленное исключение: ``reason`` читает машина
    (doctor), ``note`` - человек (строка перед меню поиска).
    """

    devices: list[Device] = field(default_factory=list)
    #: Почему слушание не дало приёмников: ``module`` (в этом python нет zeroconf),
    #: ``network`` (сеть не дала мультикаста или слушание оборвалось) или ``silence``
    #: (слушали честно, но никто не отозвался). Пусто - приёмники услышаны.
    reason: str = ""
    #: Та же причина словами для человека; печатается как есть, без перевода.
    note: str = ""
