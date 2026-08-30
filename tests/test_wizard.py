"""Проверки меню настройки Telegram."""

from pathlib import Path

from pytest import MonkeyPatch

from tgbot.config import CONFIG_ENV, Config
from tgbot.transport import _TelegramResult
from tgbot.wizard import wizard


def test_failure_stays_in_menu_accepts_proxy_and_rechecks(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    monkeypatch.setenv(CONFIG_ENV, str(path))
    answers = iter(["1", "bad…tail", "2", "-100", "4", "http://proxy:80", "0"])
    seen: list[tuple[str, str]] = []
    outcomes = iter([_TelegramResult(401), _TelegramResult(200)])

    def checker(
        token: str, _chat: str, proxy: str, _message: str, _timeout: float
    ) -> _TelegramResult:
        seen.append((token, proxy))
        return next(outcomes)

    output: list[str] = []
    assert wizard(read=lambda _prompt: next(answers), write=output.append, checker=checker) == 0
    assert seen == [("bad…tail", ""), ("bad…tail", "http://proxy:80")]
    assert "401" in "\n".join(output)
    assert Config.load().proxy == "http://proxy:80"


def test_mtproto_is_named_and_does_not_end_setup(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path / "config.json"))
    answers = iter(["3", "tg://proxy?server=x&port=1&secret=y", "0"])
    output: list[str] = []
    assert wizard(read=lambda _prompt: next(answers), write=output.append) == 0
    assert "MTProto" in "\n".join(output)
