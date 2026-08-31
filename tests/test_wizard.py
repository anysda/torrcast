"""Проверки меню настройки Telegram."""

from pathlib import Path

from pytest import MonkeyPatch

from tgbot.config import CONFIG_ENV, Config
from tgbot.i18n import i18n
from tgbot.transport import _TelegramResult
from tgbot.wizard import wizard
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.config import Config as ProductConfig
from torrcast.domain.infra_error import InfraError
from torrcast.runtime.wire import wire


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
    assert (
        wizard(
            read=lambda _prompt: next(answers),
            write=output.append,
            checker=checker,
            service=lambda: None,
        )
        == 0
    )
    assert seen == [("bad…tail", ""), ("bad…tail", "http://proxy:80")]
    assert "401" in "\n".join(output)
    assert Config.load().proxy == "http://proxy:80"


def test_mtproto_is_named_and_does_not_end_setup(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path / "config.json"))
    answers = iter(["3", "tg://proxy?server=x&port=1&secret=y", "0"])
    output: list[str] = []
    assert wizard(read=lambda _prompt: next(answers), write=output.append) == 0
    assert "MTProto" in "\n".join(output)


def test_without_a_flag_the_menu_speaks_the_language_of_the_product_setting(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """`cast -tg` после `cast --ru` обязан поднять меню по-русски, а не по-английски."""
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path / "config.json"))
    save_config(ProductConfig(tv="10.0.0.50", language="ru"))
    wire()
    output: list[str] = []

    assert wizard(read=lambda _prompt: "0", write=output.append) == 0

    assert output == [i18n("menu")]


def _pass(_token: str, _chat: str, _proxy: str, _message: str, _timeout: float) -> _TelegramResult:
    return _TelegramResult(200)


def test_a_saved_setup_leaves_the_bot_service_running(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """🔴 Мастер кончается поднятой службой, а не одним лишь сохранением.

    31-08-2026 живьём: мастер сказал «сохранено», проверочная надпись пришла в чат (её
    шлёт сам мастер), человек написал `cast тачки` - и ничего. Опрашивать Telegram было
    некому: службы бота на машине не существовало, и ни установщик, ни мастер её не
    заводили. Проверка держит именно этот шаг - службу зовут ровно один раз и после
    сохранения.
    """
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path / "config.json"))
    answers = iter(["1", "12345:AA", "2", "-100", "4", "0"])
    raised: list[str] = []
    output: list[str] = []

    assert (
        wizard(
            read=lambda _prompt: next(answers),
            write=output.append,
            checker=_pass,
            service=lambda: raised.append("up"),
        )
        == 0
    )

    assert raised == ["up"], "настроенный бот обязан остаться поднятым"
    assert output.index(i18n("success")) < output.index(i18n("service_up")), (
        "служба поднимается после сохранения, а не вместо него"
    )


def test_a_service_that_did_not_come_up_is_named_and_the_setup_is_kept(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Отказ службы назван человеку, а проверенная настройка остаётся на диске.

    Молчание тут неотличимо от успеха: человек ушёл бы из мастера уверенным, что бот
    работает. Ронять мастер тоже нечем - настройка живой проверкой уже подтверждена.
    """
    path = tmp_path / "config.json"
    monkeypatch.setenv(CONFIG_ENV, str(path))
    answers = iter(["1", "12345:AA", "2", "-100", "4", "0"])
    output: list[str] = []

    def угасшая() -> None:
        raise InfraError("unit torrcast-bot.service did not start: Unit not found.")

    assert (
        wizard(
            read=lambda _prompt: next(answers),
            write=output.append,
            checker=_pass,
            service=угасшая,
        )
        == 0
    )

    assert Config.load().token == "12345:AA", "проверенная настройка обязана уцелеть"
    said = "\n".join(output)
    assert "Unit not found." in said and "systemctl enable --now torrcast-bot" in said
