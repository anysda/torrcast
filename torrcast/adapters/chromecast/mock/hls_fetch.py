"""Чем сухой приёмник ходит за потоком: манифест, сессия и память о 404."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.why import why
from torrcast.ports.clock import Clock

#: Заголовок, без которого Chromecast молча не играет ответ.
CORS_HEADER: Final = "Access-Control-Allow-Origin"
#: Сколько ждём ответа раздачи, секунды.
HTTP_TIMEOUT: Final = 30.0


def _requests_session(ca: str) -> Any:
    """Настоящая сессия. Импорт отложен: показ поднимается быстрее, чем ``requests``."""
    import requests

    session = requests.Session()
    session.verify = ca or True
    return session


class HlsFetch:
    """Рот приёмника в сеть: та же строгость к TLS и CORS, что у ТВ.

    Адрес приходит готовым, и по нему же выбирается строгость: на https TLS проверяется
    по-настоящему, а не ``verify=False`` - чему доверять, решает якорь доверия
    (системное хранилище для настоящего серта, сам файл для self-signed; пустой ``ca`` =
    хранилище). На http проверять нечего.
    """

    def __init__(self, ca: str, clock: Clock, sulk: float = 0.0) -> None:
        self.ca = ca
        self.clock = clock
        #: Сколько приёмник не берёт LOAD вовсе, поймав 404
        #: (:attr:`torrcast.domain.profile.Profile.sulk`).
        self.sulk = sulk
        #: Докуда приёмник не берёт LOAD после пойманного 404.
        self.sulk_until = 0.0
        #: Чем открывается сессия; сверке сегментов нужна своя, а тесту - раздача на бумаге.
        self.session: Callable[[str], Any] = _requests_session

    def open(self) -> Any:
        """Сессия под свой якорь доверия: одна на того, кто её просит."""
        return self.session(self.ca)

    def manifest(self, url: str) -> str:
        """Первый ответ раздачи: TLS, доступность, CORS. Тело отдаётся зовущему."""
        import requests

        try:
            response = self.open().get(url, timeout=HTTP_TIMEOUT)
            self.caught(response)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise InfraError(
                phrase("chromecast_talk.manifest_not_fetched", reason=why(exc))
            ) from exc
        if response.headers.get(CORS_HEADER) != "*":
            raise InfraError(phrase("chromecast_talk.cors_header_missing", header=CORS_HEADER))
        return str(response.text)  # сессия нетипизирована - тело забираем строкой явно

    def caught(self, response: Any) -> None:
        """404 приёмник помнит :attr:`sulk` секунд.

        ⚠️ Наказание за 404 - повадка конкретного аппарата, а не общее правило: на
        замеренных приёмниках его нет вовсе, и там это ноль. Механизм стоит на месте
        затем, чтобы обидчивый приёмник описывался числом в своём профиле, а не правкой
        кода.
        """
        if getattr(response, "status_code", 0) == 404:
            self.sulk_until = self.clock.monotonic() + self.sulk
