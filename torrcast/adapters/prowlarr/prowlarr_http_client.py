"""Исполняет HTTP-запросы Prowlarr с назначенным правилом таймаутом."""

import contextlib
from typing import Any

import requests

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.why import why

_HttpSession = requests.Session


class _IndexersUnavailableError(InfraError):
    """Prowlarr сообщает, что выбранные индексеры недоступны."""


class ProwlarrHttpClient:
    """Сетевая механика Prowlarr без политики выбора бюджета."""

    def new_session(self) -> _HttpSession:
        return requests.Session()

    def get_json(self, session: Any, url: str, timeout: float, base_url: str) -> Any:
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

    def post(self, session: Any, url: str, body: Any, timeout: float) -> None:
        session.post(url, json=body, timeout=timeout)

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
            session.post(test_url, json=body, timeout=test_timeout)
