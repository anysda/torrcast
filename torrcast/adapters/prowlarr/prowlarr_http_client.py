"""Исполняет HTTP-запросы Prowlarr с назначенным правилом таймаутом."""

import contextlib
from typing import Any

import requests

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.why import why

_HttpSession = requests.Session


def _close(response: Any) -> None:
    """Освободить ответ HTTP, если подставной транспорт его поддерживает."""
    close = getattr(response, "close", None)
    if callable(close):
        close()


class _IndexersUnavailableError(InfraError):
    """Prowlarr сообщает, что выбранные индексеры недоступны."""


class ProwlarrHttpClient:
    """Сетевая механика Prowlarr без политики выбора бюджета."""

    def new_session(self) -> _HttpSession:
        """Сессия поиска, которая не держит соединений между запросами.

        Сессия живёт весь поиск и дольше - её носят опоздавшие круга и превью, - а
        Prowlarr сам закрывает простаивающее соединение через пару минут. Пул
        keep-alive держал бы такой сокет полуоткрытым (CLOSE-WAIT), пока сессию не
        соберёт сборщик мусора: за десять минут работы полок их набиралась сотня.
        """
        session = requests.Session()
        session.headers["Connection"] = "close"
        return session

    def get_json(self, session: Any, url: str, timeout: float, base_url: str) -> Any:
        response: Any = None
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            body = str(getattr(exc.response, "text", "") or "").casefold()
            if "all selected indexers being unavailable" in body:
                raise _IndexersUnavailableError(
                    phrase("prowlarr.selected_indexers_unresponsive")
                ) from exc
            raise InfraError(
                phrase("prowlarr.unresponsive", base_url=base_url, reason=why(exc))
            ) from exc
        except ValueError as exc:
            raise InfraError(phrase("prowlarr.not_json")) from exc
        finally:
            _close(response)

    def post(self, session: Any, url: str, body: Any, timeout: float) -> None:
        _close(session.post(url, json=body, timeout=timeout))

    def probe(
        self,
        session: Any,
        indexer_url: str,
        test_url: str,
        list_timeout: float,
        test_timeout: float,
        base_url: str,
    ) -> None:
        """Проверить индексер, поглотив сетевой отказ фонового лечения."""
        with contextlib.suppress(requests.RequestException, InfraError, ValueError):
            body = self.get_json(session, indexer_url, list_timeout, base_url)
            self.post(session, test_url, body, test_timeout)
