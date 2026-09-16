"""Синхронный транспорт Telegram Bot API с честным сроком запроса."""

from __future__ import annotations

import signal
import threading
from dataclasses import dataclass
from types import FrameType

import requests


class _DeadlineError(BaseException):
    """Общий срок вызова истёк, даже если сокет менялся внутри requests."""


def _deadline(_signum: int, _frame: FrameType | None) -> None:
    """Прервать синхронный вызов по общему сроку."""
    raise _DeadlineError


@dataclass(frozen=True, slots=True)
class _TelegramResult:
    """Исход одного вызова Bot API; нулевой статус означает сетевой отказ."""

    status: int
    detail: str = ""
    value: object | None = None


class _TelegramClient:
    """Клиент двух методов, необходимых живой проверке настройки."""

    def __init__(self, token: str, proxy: str = "", timeout: float = 20.0) -> None:
        self._base = f"https://api.telegram.org/bot{token}/"
        self._timeout = timeout
        self._proxies = {"http": proxy, "https": proxy} if proxy else None

    def call(self, method: str, **params: object) -> _TelegramResult:
        """Вызвать Bot API, не раскрывая токен в диагностике исключения."""
        return self._sent(method, None, params)

    def upload(self, method: str, files: dict[str, bytes], /, **params: object) -> _TelegramResult:
        """Вызвать Bot API с байтами вложением: обложку пульта берут только телом.

        Полем ``data`` уехало бы текстовое подобие байтов, и Telegram ответил бы
        отказом про негодную картинку (:meth:`tgbot.telegram_api.TelegramApi.photo`).
        """
        return self._sent(method, files, params)

    def _sent(
        self,
        method: str,
        files: dict[str, bytes] | None,
        params: dict[str, object],
    ) -> _TelegramResult:
        """Одна посылка Bot API: общий срок, общий разбор ответа."""
        alarm = threading.current_thread() is threading.main_thread()
        previous = signal.getsignal(signal.SIGALRM)
        try:
            if alarm:
                signal.signal(signal.SIGALRM, _deadline)
                signal.setitimer(signal.ITIMER_REAL, self._timeout)
            response = requests.post(
                self._base + method,
                data=params,
                files=files,
                proxies=self._proxies,
                timeout=self._timeout,
            )
        except _DeadlineError:
            return _TelegramResult(0, "Timeout")
        except requests.RequestException as error:
            return _TelegramResult(0, type(error).__name__)
        finally:
            if alarm:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)
        detail = ""
        value: object | None = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = str(payload.get("description", ""))
                value = payload.get("result")
        except requests.JSONDecodeError:
            detail = response.reason
        return _TelegramResult(response.status_code, detail, value)


def transport(
    config_token: str,
    chat_id: str,
    proxy: str,
    message: str,
    timeout: float = 20.0,
) -> _TelegramResult:
    """Проверить токен через getMe, затем право писать живым sendMessage."""
    client = _TelegramClient(config_token, proxy, timeout)
    identified = client.call("getMe")
    if identified.status != 200:
        return identified
    return client.call("sendMessage", chat_id=chat_id, text=message)
