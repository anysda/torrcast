"""Как узнать про службы вокруг: ffmpeg, systemd, Prowlarr, TorrServer, ТВ и раздача.

Половина системной среды :mod:`torrcast.adapters.health.system_health_environment`.
"""

import socket
import subprocess
from typing import cast

import requests

from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.adapters.chromecast.scan.alive import CAST_PORT
from torrcast.adapters.chromecast.scan.by_mdns import by_mdns
from torrcast.adapters.chromecast.scan.receiver_link import receiver_link
from torrcast.adapters.http_server.hls_base import hls_base
from torrcast.adapters.http_server.our_address import our_address
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.health_config import HealthConfig

#: Сколько ждём версию ffmpeg: команда локальная и быстрая, а потолок тут стоит от
#: повисшего наглухо процесса, а не от медленного ответа.
_VERSION_TIMEOUT = 10


class ServiceProbe:
    """Факты о службах и сети: каждая проба отвечает значением, а не исключением."""

    @staticmethod
    def ffmpeg_version() -> str | None:
        """Первая строка ``ffmpeg -version``; ``None`` - он не сказал ничего."""
        version = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT,
            check=False,
        ).stdout.splitlines()
        return str(version[0]) if version else None

    @staticmethod
    def prowlarr_unit(timeout: float) -> str | None:
        """Окружение юнита Prowlarr; ``None`` - службой мы не управляем."""
        try:
            done = subprocess.run(
                ["systemctl", "show", "prowlarr.service", "-p", "Environment"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return str(done.stdout)

    @staticmethod
    def get_json(url: str, headers: dict[str, str], timeout: float) -> object | None:
        """JSON по адресу; ``None`` - не ответил или ответил не JSON."""
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            payload: object = response.json()
            return payload
        except (requests.RequestException, ValueError):
            return None

    @staticmethod
    def search_titles(
        url: str, apikey: str, indexer: int, query: str, timeout: float
    ) -> list[str] | None:
        """Заголовки одного настоящего поиска по одному индексеру; ``None`` - молчание.

        Строка на каждую строку ответа, даже безымянную: пустая выдача и выдача мимо
        запроса - разные диагнозы, и различает их правило домена, а не эта проба.
        """
        try:
            response = requests.get(
                f"{url}/api/v1/search",
                headers={"X-Api-Key": apikey},
                params={
                    "query": query,
                    "type": "search",
                    "indexerIds": str(indexer),
                    "limit": "1",
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            return None
        if not isinstance(payload, list):
            return None
        return [
            row["title"] if isinstance(row, dict) and isinstance(row.get("title"), str) else ""
            for row in payload
        ]

    @staticmethod
    def torrserver_echo(url: str, timeout: float) -> str | None:
        """Ответ службы раздачи на ``/echo``; ``None`` - она молчит."""
        try:
            response = requests.get(f"{url}/echo", timeout=timeout)
            response.raise_for_status()
        except requests.RequestException:
            return None
        return str(response.text)

    @staticmethod
    def torrserver_settings(url: str, timeout: float) -> object | None:
        """Настройки TorrServer. Спрашиваются POST-ом с телом - GET на этот адрес молчит."""
        try:
            response = requests.post(f"{url}/settings", json={"action": "get"}, timeout=timeout)
            response.raise_for_status()
            payload: object = response.json()
            return payload
        except (requests.RequestException, ValueError):
            return None

    @staticmethod
    def cast_port() -> int:
        """Порт приёмника: он открыт даже у спящего телевизора."""
        return CAST_PORT

    @staticmethod
    def our_address(tv: str) -> str:
        """Наш адрес с той стороны, с которой нас видит ТВ; пусто - маршрута нет."""
        return our_address(tv)

    @staticmethod
    def port_error(host: str, port: int, timeout: float) -> str:
        """Пусто, если порт открылся, иначе причина отказа человеческими словами."""
        sock = socket.socket()
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
        except OSError as exc:
            return str(exc.strerror or exc)
        finally:
            sock.close()
        return ""

    @staticmethod
    def heard_receivers() -> tuple[list[str], str, str]:
        """Имена приёмников из эфира, а также причина и пояснение, если их нет."""
        heard = by_mdns()
        return [device.title for device in heard.devices], heard.reason, heard.note

    @staticmethod
    def receiver_profile(config: HealthConfig) -> tuple[str, str, bool]:
        """Имя выбранного профиля приёмника, откуда он взялся и осторожный ли он."""
        chosen = detector.detect(config)
        return str(chosen.profile.title), str(chosen.how), bool(chosen.profile is CAUTIOUS)

    @staticmethod
    def receiver_link(host: str, timeout: float) -> tuple[float, bool | None]:
        """Аптайм приёмника и то, чем он подключён; молчание - ноль и «не сказал»."""
        return receiver_link(host, timeout)

    @staticmethod
    def hls_base(config: HealthConfig) -> tuple[str, str]:
        """База URL раздачи и, если она не собирается, причина этого."""
        try:
            return hls_base(cast(Config, config)), ""
        except TorrcastError as exc:
            return "", str(exc)
