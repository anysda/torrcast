"""Нелинейное меню настройки Telegram-бота."""

from __future__ import annotations

from collections.abc import Callable

from tgbot.config import Config
from tgbot.i18n import i18n
from tgbot.proxy import proxy as parse_proxy
from tgbot.transport import _TelegramResult, transport

_Reader = Callable[[str], str]
_Writer = Callable[[str], None]
_Checker = Callable[[str, str, str, str, float], _TelegramResult]
text = i18n


def _masked(token: str) -> str:
    """Оставить в отчёте только безопасный хвост токена."""
    return "…" + token[-4:] if token else "…"


def _diagnosis(result: _TelegramResult, language: str) -> str:
    """Разложить сетевой и протокольный отказ на пользовательские причины."""
    if result.status == 0:
        return text("network", language, detail=result.detail)
    if result.status in {400, 401, 403}:
        return text(f"http_{result.status}", language)
    return text("http_other", language, status=result.status, detail=result.detail)


def _offer_proxy(config: Config, language: str, read: _Reader, write: _Writer) -> bool:
    """Принять лечебный прокси и ответить, надо ли повторить живую проверку."""
    candidate = read(text("try_proxy", language))
    if not candidate:
        return False
    proxy, problem = parse_proxy(candidate)
    if problem:
        write(text(problem, language))
        return False
    config.proxy = proxy or ""
    write(text("proxy_set", language))
    return True


def wizard(
    language: str = "en",
    *,
    read: _Reader = input,
    write: _Writer = print,
    checker: _Checker = transport,
    timeout: float = 20.0,
) -> int:
    """Показывать меню до явного выхода; сохранять только после живой проверки."""
    config = Config.load()
    while True:
        write(text("menu", language))
        choice = read(text("choice", language)).strip()
        if choice == "0":
            return 0
        if choice == "1":
            config.token = read(text("token", language)).strip()
            write(text("token_set", language, token=_masked(config.token)))
        elif choice == "2":
            config.chat_id = read(text("chat", language)).strip()
            write(text("chat_set", language))
        elif choice == "3":
            candidate = read(text("proxy", language))
            if not candidate:
                continue
            proxy, problem = parse_proxy(candidate)
            if problem:
                write(text(problem, language))
            else:
                config.proxy = proxy or ""
                write(text("proxy_set", language))
        elif choice == "4":
            if not config.token or not config.chat_id:
                write(text("need_fields", language))
                continue
            write(text("testing", language))
            result = checker(
                config.token,
                config.chat_id,
                config.proxy,
                text("test_message", language),
                timeout,
            )
            while result.status != 200:
                write(_diagnosis(result, language))
                if not _offer_proxy(config, language, read, write):
                    break
                write(text("testing", language))
                result = checker(
                    config.token,
                    config.chat_id,
                    config.proxy,
                    text("test_message", language),
                    timeout,
                )
            if result.status == 200:
                config.save()
                write(text("success", language))
        elif choice == "5":
            removed = Config.remove()
            config = Config()
            write(text("removed" if removed else "nothing_removed", language))
        else:
            write(text("invalid_choice", language))
