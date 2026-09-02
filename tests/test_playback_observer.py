"""Пульт следует за снимком показа, а не за тем, кто запустил команду."""

from pathlib import Path
from typing import cast

import pytest

from tgbot.playback_observer import PlaybackObserver
from tgbot.telegram_api import TelegramApi
from tgbot.telegram_choice_environment import TelegramChoiceEnvironment
from tgbot.telegram_control import TelegramControl
from tgbot.transport import _TelegramResult


class _Api:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.edited: list[tuple[int, str, object]] = []
        self.deleted: list[int] = []

    def post(self, _chat: str, text: str, _buttons: object = None) -> _TelegramResult:
        message_id = 40 + len(self.sent)
        self.sent.append((message_id, text))
        return _TelegramResult(200, "", {"message_id": message_id})

    def edit(self, _chat: str, message_id: int, text: str, buttons: object = None) -> object:
        self.edited.append((message_id, text, buttons))
        return object()

    def delete(self, _chat: str, message_id: int) -> object:
        self.deleted.append(message_id)
        return object()


def test_observer_keeps_one_control_message_across_episode_and_stop(tmp_path: Path) -> None:
    api = _Api()
    titles = iter(["Домохозяйки (2004) s1e17", "Домохозяйки (2004) s1e18", ""])
    control = TelegramControl(cast(TelegramApi, api), "-100", tmp_path / "control")
    observer = PlaybackObserver(control, lambda: next(titles))

    observer.sync()
    observer.sync()
    observer.sync()

    assert api.sent == [(40, "Домохозяйки (2004) s1e17")]
    assert api.edited[0][:2] == (40, "Домохозяйки (2004) s1e18")
    assert api.edited[0][2] == control.buttons(), "кнопки пережили смену серии"
    assert api.deleted == [40]


def test_failed_deletion_disarms_the_old_control(tmp_path: Path) -> None:
    class Refused(_Api):
        def delete(self, _chat: str, message_id: int) -> object:
            self.deleted.append(message_id)
            raise RuntimeError("forbidden")

    api = Refused()
    titles = iter(["Мумия (1999)", ""])
    observer = PlaybackObserver(
        TelegramControl(cast(TelegramApi, api), "-100", tmp_path / "control"),
        lambda: next(titles),
    )

    observer.sync()
    observer.sync()

    assert api.edited == [(40, "Nothing is playing.", None)]


def test_restart_reuses_and_cleans_the_remembered_control(tmp_path: Path) -> None:
    api = _Api()
    path = tmp_path / "control"
    first = TelegramControl(cast(TelegramApi, api), "-100", path)
    first.show("Мумия (1999)")

    PlaybackObserver(TelegramControl(cast(TelegramApi, api), "-100", path), lambda: "").sync()

    assert api.sent == [(40, "Мумия (1999)")]
    assert api.deleted == [40]
    assert not path.with_suffix(".message").exists()


class _Refusing(_Api):
    """Отказывает пульту заданным исходом, пока его не «починили» снаружи."""

    def __init__(self, refusal: _TelegramResult) -> None:
        super().__init__()
        self.refusal = refusal

    def post(self, chat: str, text: str, buttons: object = None) -> _TelegramResult:
        if self.refusal.status != 200:
            return self.refusal
        return super().post(chat, text, buttons)

    def edit(self, chat: str, message_id: int, text: str, buttons: object = None) -> object:
        if self.refusal.status != 200:
            return self.refusal
        return super().edit(chat, message_id, text, buttons)


def test_telegram_refusal_is_named_once_per_state_change_not_per_tick(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Отказ повторяется на каждом тике, а строка в журнале - одна на смену состояния."""
    api = _Refusing(_TelegramResult(401, "Unauthorized"))
    title = ["Мумия (1999)"]
    observer = PlaybackObserver(
        TelegramControl(cast(TelegramApi, api), "-100", tmp_path / "control"),
        lambda: title[0],
    )

    # 🔴 Тиков шесть, а не три. Демпфер смены рода (:data:`_STEADY_TICKS`) сам держит
    # три тика молча, поэтому на окне в три тика сторож зелен и со снятым дедупом по
    # прежнему отказу: замер даёт 1/1/1/1 строку как есть и 1/2/3/4 без него.
    for _ in range(6):
        observer.sync()

    refused = capsys.readouterr().err.splitlines()
    assert len(refused) == 1, "шесть тиков отказа - одна строка, а не эхо каждые три"
    assert "401" in refused[0]

    api.refusal = _TelegramResult(200)
    observer.sync()

    recovered = capsys.readouterr().err.splitlines()
    assert len(recovered) == 1, "возврат работы - тоже одна строка"
    assert "401" not in recovered[0]

    api.refusal = _TelegramResult(401, "Unauthorized")
    # Пульт с неизменным текстом чат не трогает вовсе: отказ ловит тот тик,
    # которому есть что послать, - здесь сменившуюся серию.
    title[0] = "Мумия (1999) s1e2"
    for _ in range(6):
        observer.sync()

    assert [line for line in capsys.readouterr().err.splitlines() if "401" in line] == [refused[0]]


def test_network_trouble_and_a_dead_token_are_named_apart(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Беда сети пройдёт сама, 401 - нет: строки обязаны различаться.

    Смена рода называется, лишь устоявшись: одиночный тик чужого рода среди
    сплошных отказов прежнего - шум сети и строки не стоит.
    """
    api = _Refusing(_TelegramResult(0, "Timeout"))
    observer = PlaybackObserver(
        TelegramControl(cast(TelegramApi, api), "-100", tmp_path / "control"),
        lambda: "Мумия (1999)",
    )

    observer.sync()

    network = capsys.readouterr().err.strip()
    assert "Timeout" in network
    assert "401" not in network

    api.refusal = _TelegramResult(401, "Unauthorized")
    observer.sync()
    api.refusal = _TelegramResult(0, "Timeout")
    observer.sync()

    assert not capsys.readouterr().err, "одиночный чужой тик - шум, а не смена беды"

    api.refusal = _TelegramResult(401, "Unauthorized")
    observer.sync()
    observer.sync()
    observer.sync()

    dead_token = capsys.readouterr().err.strip()
    assert "401" in dead_token
    assert dead_token != network


def test_the_ended_show_takes_its_command_message_and_not_the_next_one(
    tmp_path: Path,
) -> None:
    """Конец показа убирает и пульт, и команду; команде занявшей чат - рано.

    Пока показ идёт, в чате живут оба сообщения. Номер команды запоминается на
    старте показа: при щели между показами снимается команда КОНЧИВШЕГОСЯ, а не та,
    что уже заняла чат следующим запросом.
    """
    api = _Api()
    choice = TelegramChoiceEnvironment(cast(TelegramApi, api), "-100")
    observer = PlaybackObserver(
        TelegramControl(cast(TelegramApi, api), "-100", tmp_path / "control"),
        lambda: "",
        choice,
    )

    choice.begin(7)
    observer.sync("Мумия (1999)")
    assert api.deleted == [], "пока идёт показ, в чате остаются и команда, и пульт"

    choice.begin(9)
    # 🔴 Тик при ЖИВОМ показе уже ПОСЛЕ прихода команды 9 - это и есть та гонка, ради
    # которой номер запоминается на старте. Без него сторож зелен и тогда, когда номер
    # перезапоминается каждым тиком, а конец показа 7 уносит чужую команду 9.
    observer.sync("Мумия (1999) s1e2")
    observer.sync("")

    assert api.deleted == [40, 7], "конец показа снял пульт и команду кончившегося"
    assert choice.command_id() == 9, "команда нового диалога пережила щель между показами"

    # Простой после конца показа: снятое не снимается вторично. Без этой проверки
    # сторож зелен и тогда, когда наблюдатель шлёт `deleteMessage` на давно мёртвый
    # номер каждые две секунды всё время, пока показа нет.
    observer.sync("")

    assert api.deleted == [40, 7], "простой не снимает уже снятое ещё раз"

    observer.sync("Блич (2004)")
    observer.sync("")

    assert api.deleted == [40, 7, 41, 9], "и её снимает конец уже своего показа"
