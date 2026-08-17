"""Слушание mDNS: единственный способ узнать человеческие имена приёмников.

Зовёт его поиск приёмников параллельно обходу подсетей, и щуп служб - в одиночку."""

from __future__ import annotations

import time
from contextlib import suppress
from typing import Final

from torrcast.adapters.chromecast.cast.hush_cosmetic_noise import hush_cosmetic_noise
from torrcast.adapters.chromecast.scan.device import Device
from torrcast.adapters.chromecast.scan.mdns import Mdns

#: Сколько слушаем mDNS. Приёмник отвечает на первый же запрос, дальше идёт тишина.
MDNS_TIMEOUT: Final = 4.0


def by_mdns(timeout: float = MDNS_TIMEOUT) -> Mdns:
    """Приёмники, которые сами объявили о себе по mDNS: тут и берутся человеческие имена.

    Слушаем строго IPv4: на хосте без внешнего IPv6 сокет уходит в SYN-SENT и висит
    там дольше всего нашего поиска.

    Любой сбой zeroconf (нет мультикаста, чужой namespace, занятый порт) - это не отказ
    поиска: остаётся обход подсетей, и он найдёт то же самое, только без имён. Но
    причину пустого ответа мы больше не глотаем: :class:`Mdns` разводит три случая -
    нет модуля, сеть не дала слушать, слушали и никого не услышали.
    """
    try:
        import zeroconf
        from pychromecast.discovery import CastBrowser, SimpleCastListener
    except ImportError:  # другой python без зависимостей: так рождалась ложная тревога
        return Mdns(
            reason="module",
            note=(
                "mDNS не слушаю: в этом python нет модуля zeroconf - "
                "имён приёмников не будет, адреса найдёт обход подсетей"
            ),
        )
    hush_cosmetic_noise()  # см. :func:`named`: жалоба на 8443 ничего не значит
    try:
        zconf = zeroconf.Zeroconf(ip_version=zeroconf.IPVersion.V4Only)
    except Exception as exc:  # нет мультикаста, чужой namespace, занятый порт 5353
        return Mdns(
            reason="network",
            note=(
                f"mDNS не слушаю: сеть не дала мультикаста ({exc}) - "
                "имён приёмников не будет, адреса найдёт обход подсетей"
            ),
        )
    browser = CastBrowser(SimpleCastListener(), zconf)
    found: list[Device] = []
    broken = ""
    try:
        browser.start_discovery()
        time.sleep(timeout)
        for info in list(browser.devices.values()):
            if info.host:
                found.append(
                    Device(
                        address=str(info.host),
                        name=str(info.friendly_name or ""),
                        model=str(info.model_name or ""),
                        how="mdns",
                        maker=str(getattr(info, "manufacturer", "") or ""),
                    )
                )
    except Exception as exc:  # слушание оборвалось: показываем, что успели услышать
        broken = str(exc) or type(exc).__name__
    finally:
        with suppress(Exception):
            browser.stop_discovery()
        with suppress(Exception):
            zconf.close()
    if found:
        return Mdns(devices=found)
    if broken:
        return Mdns(
            reason="network",
            note=(
                f"mDNS оборвался ({broken}) - "
                "имён приёмников не будет, адреса найдёт обход подсетей"
            ),
        )
    return Mdns(
        reason="silence",
        note=(
            f"mDNS слушал {timeout:g} сек - никто не отозвался: приёмник в другом "
            "сегменте (мультикаст через маршрутизатор не ходит) или молчит; "
            "адреса найдёт обход подсетей"
        ),
    )
