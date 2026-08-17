"""Поиск приёмников Chromecast-протокола в сети - чтобы адрес ТВ не пришлось знать.

Настройка после установки звучала так: «узнай где-то IP телевизора и передай его
``cast --tv <ip>``». Узнать его негде: в меню ТВ адрес спрятан через три экрана, а в
роутер пускают не всех. Поэтому ``cast --tv`` без адреса ищет приёмники сам, и человек
выбирает свой телевизор номером из списка.

Ищем **двумя** способами сразу, потому что поодиночке каждый слеп:

* штатный discovery pychromecast (mDNS/zeroconf) - он единственный знает человеческие
  имена («Samsung Q70D»), но mDNS это мультикаст, и через маршрутизатор он не идёт: у
  хоста бывает отдельная нога в сегмент телевизора, где имя услышать некому;
* обход адресов своих подсетей с проверкой порта 8009 - он ходит везде, куда идёт
  маршрут, но сам по себе имени не знает.

Найденное сливается по адресу: имя от mDNS выигрывает, адрес остаётся один.

⚠️ **Открытый порт - ещё не приёмник.** Проверять коннектом мало: транзитный VPN на
исходящем канале отвечает SYN-ACK на любой порт любого адреса, и тогда «нашлось 254
телевизора». Поэтому признаком служит не коннект, а **состоявшееся TLS-рукопожатие** на
8009 (:func:`alive`): молчащая заглушка ServerHello не пришлёт. Дальше запрашивается имя
(:func:`named`) - обычным HTTP-опросом устройства, без единой команды показа: обнаружение
не имеет права ничего запускать на чужом экране.

⚠️ Соседи внутри пакета зовут друг друга ЧЕРЕЗ него (``scan.by_mdns()``), а не связанной
функцией: подмену слушания и обхода на стенде ставят именно на пакет, и связывание при
импорте её бы потеряло.
"""

from torrcast.adapters.chromecast.scan.alive import CAST_PORT, alive
from torrcast.adapters.chromecast.scan.by_mdns import by_mdns
from torrcast.adapters.chromecast.scan.by_scan import by_scan
from torrcast.adapters.chromecast.scan.device import Device
from torrcast.adapters.chromecast.scan.find import find
from torrcast.adapters.chromecast.scan.found import Found
from torrcast.adapters.chromecast.scan.hosts import hosts
from torrcast.adapters.chromecast.scan.interfaces import interfaces
from torrcast.adapters.chromecast.scan.mdns import Mdns
from torrcast.adapters.chromecast.scan.named import named
from torrcast.adapters.chromecast.scan.net import Net
from torrcast.adapters.chromecast.scan.skipped import skipped
from torrcast.adapters.chromecast.scan.subnets import subnets

__all__ = [
    "CAST_PORT",
    "Device",
    "Found",
    "Mdns",
    "Net",
    "alive",
    "by_mdns",
    "by_scan",
    "find",
    "hosts",
    "interfaces",
    "named",
    "skipped",
    "subnets",
]
