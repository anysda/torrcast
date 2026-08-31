"""Язык жалобы бота на настройку, которую нельзя разобрать без потери."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from tgbot.bot import Bot
from tgbot.config import CONFIG_ENV
from tgbot.config import Config as BotConfig
from tgbot.telegram_api import TelegramApi
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.config import Config
from torrcast.domain.invalid_config_object_error import InvalidConfigObjectError
from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.choice.configure import configure as configure_choice

_CYRILLIC = re.compile(r"[\u0400-\u04ff]")


@pytest.fixture(autouse=True)
def _choice_restored() -> Iterator[None]:
    """``Bot()`` тут ставит окружение выбора глобально и не снимает его.

    В бою это законно - бот один на процесс. В наборе это течь: следующий тест того
    же воркера xdist наследует чужое окружение и уезжает в телеграм-путь. Дисциплина
    та же, что уже держат пробы в ``tests/test_ux.py`` и ``tests/test_bot.py``
    (``previous = _environment_port()`` до создания бота, ``configure_choice(previous)``
    после), но здесь заведена фикстурой, чтобы не держаться на памяти каждого теста.
    """
    previous = _environment_port()
    yield
    configure_choice(previous)


class _Api:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, _chat_id: str, text: str, *_args: object, **_kwargs: object) -> int:
        self.sent.append(text)
        return len(self.sent)


def _broken_reply(path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Ответ бота на команду, упавшую о неразобранную настройку.

    🔴 Язык такого ответа - всегда английский: язык лежит в настройке, а настройка
    и есть та, что не читается
    (:func:`torrcast.adapters.filesystem.state.chosen_language.chosen_language`).
    Единый держатель второго источника языка не знает, поэтому и рамка ответа, и
    слово беды внутри неё вырождаются в английский при любой прошлой настройке.
    """
    path.write_text("[]\n", encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))
    api = _Api()

    def command(_args: object) -> int:
        load_config()
        return 0

    bot = Bot(
        BotConfig("token", "-100"),
        api=cast(TelegramApi, api),
        command=command,
        assemble=lambda: None,
    )
    bot.dispatch({"message": {"chat": {"id": -100}, "message_id": 1, "text": "cast film"}})
    bot.run_one()

    assert len(api.sent) == 1
    return api.sent[0]


def test_a_broken_configuration_reply_is_entirely_english(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Неразобранная настройка не читается - и кириллица не уезжает ни в рамке
    ответа, ни внутри неё, каким бы ни был язык до поломки."""
    reply = _broken_reply(tmp_path / "config.json", monkeypatch)

    assert not _CYRILLIC.search(reply), reply
    assert "expected a JSON object" in reply, reply


def test_the_broken_file_is_named_to_the_viewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Путь до битого файла - половина пользы жалобы, и он переживает перевод."""
    path = tmp_path / "config.json"

    assert str(path) in _broken_reply(path, monkeypatch)


def test_saving_over_a_broken_configuration_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Запись поверх неразобранного файла по-прежнему падает и файла не трогает."""
    path = tmp_path / "config.json"
    path.write_text("[]\n", encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))

    with pytest.raises(InvalidConfigObjectError) as caught:
        save_config(Config(tv="10.0.0.50"))

    assert caught.value.path == path
    assert path.read_text(encoding="utf-8") == "[]\n"


def test_saving_telegram_fields_over_a_broken_configuration_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Тот же договор у трёх ключей бота: чужой файл не переписывается молча."""
    path = tmp_path / "telegram.json"
    path.write_text("[]\n", encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(path))

    with pytest.raises(InvalidConfigObjectError) as caught:
        BotConfig("token", "-100").save()

    assert caught.value.path == path
    assert path.read_text(encoding="utf-8") == "[]\n"
