"""Счастливый путь: фильм и озвучка, больше ничего.

Проверяется дословное требование к продукту: «не хочу видеть какие там файлы, хочу
выбрать фильм и озвучку». Значит на обязательном пути нет ни таблицы релизов, ни списка
файлов, ни строк про серии у фильма, а вопросов ровно два — и оба пропускаются, когда
выбор единственный.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest

from tests.fakes import composition, terminal
from tests.fakes.show_unit import FakeShowUnit
from tgbot.bot import Bot
from tgbot.config import Config as BotConfig
from tgbot.i18n import i18n
from tgbot.language import language as chosen_language
from tgbot.telegram_api import TelegramApi
from tgbot.telegram_choice_environment import TelegramChoiceEnvironment
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.adapters.filesystem.state.state import State
from torrcast.cli.main import main
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_OK
from torrcast.domain.media import Media
from torrcast.domain.raw_result import RawResult
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.choice.configure import configure as configure_choice
from torrcast.usecases.playback._launch import _await_playing

#: Настоящее ожидание картинки: фикстура окружения подменяет его заглушкой, а один тест
#: проверяет именно его.
AWAIT_PLAYING = _await_playing

GB = 1024**3
#: Выдача «моаны», сведённая к сути: две картины франшизы, у каждой по два релиза.
FOUND = [
    RawResult("Moana 2016 1080p DSNP WEB-DL DDP5 1 Atmos H 264-BLOOM", "a" * 40, 5 * GB, 22),
    RawResult("Moana 2016 1080p BluRay x264 Atmos TrueHD7 1-WiKi", "b" * 40, 17 * GB, 5),
    RawResult("Моана 2 / Moana 2 (2024) WEB-DL 1080p | D, P", "c" * 40, 3 * GB, 140),
    RawResult("Moana 2 (2024) 1080p BRRip 5.1 x264 -YTS", "d" * 40, 2 * GB, 121),
]
TRACKS = (
    AudioTrack(0, "rus", "Дубляж", "ac3", 6),
    AudioTrack(1, "eng", "Original", "ac3", 6),
)


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Окружение без Prowlarr, без TorrServer, без systemd — но с полным путём выбора."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))
    save_config(Config(tv="10.0.0.50", prowlarr_apikey="ключ", hls_dir=str(tmp_path / "hls")))
    composition.use_indexers(monkeypatch, _FakeProwlarr)
    composition.use_engines(monkeypatch, _FakeTorrServer)
    composition.use_prober(
        monkeypatch, lambda url, timeout=90.0, alive=None: Media(5978.0, TRACKS, "h264", 1080)
    )
    composition.use_start_unit(monkeypatch, lambda key: None)
    composition.use_await_playing(
        monkeypatch, lambda config, progress, timeout=120.0, start=0.0: None
    )


class _FakeProwlarr:
    def __init__(self, url: str, apikey: str) -> None:
        self.url = url
        #: Счёт выпавших и опоздавших - часть договора клиента
        #: (:class:`~torrcast.ports.torrent_catalogue.indexer_client.IndexerClient`):
        #: круг говорит человеку и о том, чего в выдаче нет. Тут не выпал никто.
        self.silent: tuple[str, ...] = ()
        self.banned: tuple[str, ...] = ()
        self.reported_silent: set[str] = set()

    def search(self, query: str) -> list[RawResult]:
        return list(FOUND)

    def late(self) -> list[RawResult]:
        """Опоздавших нет: круг тут отвечает разом (TC-118)."""
        return []

    def waiting(self) -> tuple[str, ...]:
        """В пути никого: круг тут отвечает разом (TC-703)."""
        return ()

    def spare(self) -> float:
        """Остаток цели: тут поиск мгновенный, поэтому цела вся (TC-228)."""
        from torrcast.domain.goal_spare import GOAL

        return GOAL


class _FakeTorrServer:
    """Раздача в объёме подготовки релиза: hash, файлы, URL потока."""

    def __init__(self, url: str) -> None:
        self.url = url

    def add(self, magnet: str) -> str:
        return f"hash-{magnet[:30]}"

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
    ) -> list[TorrFile]:
        return [
            TorrFile(0, "Moana/Moana.2016.1080p.mkv", 5 * GB),
            TorrFile(1, "Moana/Moana.sample.mkv", 30 * 1024**2),
            TorrFile(2, "Moana/cover.jpg", 1024),
        ]

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"http://ts/{torrent_hash}/{index}"

    def drop(self, torrent_hash: str) -> bool:
        pass

        return True


def _answers(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
    """Подставные ответы человека; заодно собираем сами вопросы."""
    asked: list[str] = []
    queue = iter(replies)

    def ask(prompt: str = "") -> str:
        asked.append(prompt)
        return next(queue, "")

    monkeypatch.setattr("builtins.input", ask)
    return asked


def test_the_happy_path_asks_nothing_at_all(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """На счастливом пути вопросов нет ни одного: назвали кино - оно и включилось.

    Картин подошло две, и это ещё не повод спрашивать: «моана» - просьба про «Moana»
    2016 с её 22 сидами, даже когда у «Моаны 2» их 140, и другой картины, которую тут
    можно было иметь в виду, нет. Решение при этом названо вслух одной строкой, и в ней
    есть ход к любой другой картине.

    Меню озвучки из счастливого пути убрано: дорожка выбирается сама, а её подпись
    печатается в строке запуска — молчаливой подмены тут нет, есть названный выбор.
    """
    asked = _answers(monkeypatch)

    assert main(["моана"]) == 0

    printed = capsys.readouterr().out
    assert asked == [], "спрашивать было не о чем"
    assert "Озвучка:" not in printed, "меню озвучки на счастливом пути больше нет"
    assert "беру «Moana (2016)» - подошло картин 2; другая: cast releases моана и --pick N" in (
        printed
    )
    assert "играю «Moana» (2016) · 1080p · rus · Дубляж - на ТВ" in printed
    # Ни таблицы релизов, ни файлов, ни серий - именно этого пользователь видеть не хочет.
    for forbidden in ("Релизы:", "Качество", "Файл:", "Серии:", ".mkv", "Какой берём?"):
        assert forbidden not in printed, forbidden
    # И ни одного значка из запрещённого набора: вывод остаётся текстом, а не пиктограммами.
    assert not set(printed) & set("→⚠▶≥")


def test_silent_indexer_is_named_once_during_search(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Урезанная выдача не выглядит полной: промолчавший источник назван на экране."""

    class _SilentProwlarr(_FakeProwlarr):
        def __init__(self, url: str, apikey: str) -> None:
            super().__init__(url, apikey)
            self.silent = ("Knaben",)

    composition.use_indexers(monkeypatch, _SilentProwlarr)
    _answers(monkeypatch, "2", "")

    assert main(["моана"]) == 0
    printed = capsys.readouterr().out
    line = "индексер Knaben не ответил - выдача может быть хуже"
    assert printed.count(line) == 1


def test_banned_indexer_is_named_too(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-510. Выпасть из каталога можно двумя способами, и оба видны человеку: молчун
    не ответил нам, а заблокированного мы и не спрашивали (TC-259). Строка при этом одна
    и на весь поиск одна - разводить их по кругам поиска незачем."""

    class _BannedProwlarr(_FakeProwlarr):
        def __init__(self, url: str, apikey: str) -> None:
            super().__init__(url, apikey)
            self.banned = ("Knaben",)

    composition.use_indexers(monkeypatch, _BannedProwlarr)
    _answers(monkeypatch, "2", "")

    assert main(["моана"]) == 0
    printed = capsys.readouterr().out
    assert printed.count("индексер Knaben недоступен - выдача может быть хуже") == 1


def test_the_question_says_out_loud_what_enter_will_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-204. Дефолт в длинной франшизе уезжает за экран: терминал после вывода
    показывает хвост. Поэтому прямо перед вопросом сказано, что случится по Enter, -
    названием и годом, а не одной цифрой в скобках.

    Строка стоит ПОСЛЕ списка: шапка уехала бы вверх вместе со списком. Сам список
    остаётся хронологическим - меняется показ дефолта, а не порядок. Список тут
    поднят явным ``--menu``: на обычном пути у этой выдачи вопроса нет, а мерить
    строку надо там, где вопрос точно стоит.
    """
    _answers(monkeypatch, "", "")  # Enter на вопросе - то самое, о чём строка и говорит

    assert main(["моана", "--menu"]) == 0

    printed = capsys.readouterr().out
    enter = "Enter - «Moana (2016)», пункт 1 из 2"
    assert enter in printed
    assert (
        printed.index("  1. Moana (2016)")
        < printed.index("  2. Моана 2 (2024)")
        < printed.index(enter)
    ), "список хронологический, а строка про дефолт - в хвосте, у самого вопроса"
    assert "играю «Moana» (2016)" in printed, "и Enter запустил ровно то, что было названо"


def test_a_single_choice_is_not_a_question(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Меню франшизы пропускается, когда картина одна; озвучки нет вовсе."""
    composition.use_prober(
        monkeypatch, lambda url, timeout=90.0, alive=None: Media(5978.0, TRACKS[:1], "h264")
    )
    asked = _answers(monkeypatch)

    assert main(["моана", "2"]) == 0

    assert asked == [], "выбирать не из чего - спрашивать не о чем"
    assert "Озвучка:" not in capsys.readouterr().out


def test_the_liveliest_namesake_is_taken_without_a_question(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-812. Под одним именем - две разные картины разных лет: берётся самая живая.

    Живость роя - показатель того, что картина популярна, а варианты стоят за ``--menu``.
    Решение не молчит: строка называет взятую картину годом, число сидов её лучшей
    раздачи, сколько картин под этим именем есть ещё, и ключ, которым их поднять.
    Дефолт франшизы это не тронуло - у частей своё правило, и тут обе картины - не части.
    """

    class _Twins(_FakeProwlarr):
        def search(self, query: str) -> list[RawResult]:
            return list(TWINS)

    composition.use_indexers(monkeypatch, _Twins)
    asked = _answers(monkeypatch, "", "")

    assert main(["мумия"]) == 0
    printed = capsys.readouterr().out
    assert asked == [], "тёзки по году больше не спрашивают - берётся самая живая"
    assert (
        "беру «Мумия (2026)» - самая живая из одноимённых, у лучшей её раздачи сидов 604; "
        "других картин под этим именем: 1, их список: cast мумия --menu" in printed
    ), printed
    assert "играю «Мумия» (2026)" in printed


#: Выдача «мумии»: две картины под одним именем - самая тихая из подмен (🔴 TC-198).
TWINS = [
    RawResult("Мумия / The Mummy (1999) BDRip 1080p | D", "e" * 40, 5 * GB, 47),
    RawResult("Мумия / The Mummy (2026) WEB-DL 1080p | D", "f" * 40, 4 * GB, 604),
]


@pytest.mark.machine
def test_bot_drives_a_real_choice_through_inline_buttons(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Команда бота проходит настоящий поиск, вопрос и запуск, не подменяя CLI."""

    class Api:
        def __init__(self) -> None:
            self.sent: list[tuple[int, str, Any]] = []
            self.edited: list[str] = []
            self.deleted: list[int] = []
            self.replies: dict[int, int | None] = {}
            self.pick_ready = threading.Event()

        def send(
            self,
            _chat_id: str,
            text: str,
            buttons: Any = None,
            reply_to_message_id: int | None = None,
        ) -> int:
            message_id = len(self.sent) + 1
            self.sent.append((message_id, text, buttons))
            self.replies[message_id] = reply_to_message_id
            if buttons and str(buttons[0][0].get("callback_data", "")).startswith("pick:"):
                self.pick_ready.set()
            return message_id

        def answer(self, _callback_id: str, _text: str = "") -> object:
            return object()

        def edit(self, _chat_id: str, _message_id: int, text: str, _buttons: Any = None) -> object:
            self.edited.append(text)
            return object()

        def delete(self, _chat_id: str, message_id: int) -> object:
            self.deleted.append(message_id)
            return object()

    class Twins(_FakeProwlarr):
        def search(self, query: str) -> list[RawResult]:
            return list(TWINS)

    composition.use_indexers(monkeypatch, Twins)
    api = Api()
    previous = _environment_port()
    bot = Bot(
        BotConfig("token", "-100"),
        api=cast(TelegramApi, api),
        assemble=lambda: None,
    )
    try:
        bot.dispatch(
            {
                "message": {
                    "chat": {"id": -100},
                    "from": {"language_code": "ru"},
                    "message_id": 69,
                    "text": "cast мумия",
                }
            }
        )
        bot.run_one()
        search_id, _search_text, search_buttons = next(
            item for item in api.sent if "самая живая из одноимённых" in item[1]
        )
        assert search_buttons is None
        assert api.replies[search_id] == 69
        assert search_id in api.deleted

        bot.dispatch(
            {
                "message": {
                    "chat": {"id": -100},
                    "from": {"language_code": "ru"},
                    "message_id": 70,
                    "text": "cast мумия --menu",
                }
            }
        )

        def choose_first() -> None:
            assert api.pick_ready.wait(timeout=2)
            message_id, _text, buttons = next(
                item
                for item in api.sent
                if item[2] and item[2][0][0]["callback_data"].startswith("pick:")
            )
            bot.dispatch(
                {
                    "callback_query": {
                        "id": "pick",
                        "data": buttons[0][0]["callback_data"],
                        "from": {"language_code": "ru"},
                        "message": {"message_id": message_id, "chat": {"id": -100}},
                    }
                }
            )

        callback = threading.Thread(target=choose_first)
        callback.start()
        bot.run_one()
        callback.join(timeout=2)
        assert not callback.is_alive()
    finally:
        configure_choice(previous)

    assert any("1. Мумия (1999)" in text for _message_id, text, _buttons in api.sent)
    assert any("1. Мумия (1999)" in text for text in api.edited)
    controls = [
        text
        for _message_id, text, buttons in api.sent
        if buttons and buttons[0][0]["callback_data"].startswith("control:")
    ]
    assert controls == ["Мумия (2026)", "Мумия (1999)"]
    assert "играю «Мумия» (1999)" in capsys.readouterr().out


@pytest.mark.machine
def test_menu_card_is_removed_once_the_cast_actually_starts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """TC-926: карточка меню пропадает вместе со строками поиска, а не только по stop."""

    class Api:
        def __init__(self) -> None:
            self.sent: list[tuple[int, str, Any]] = []
            self.edited: list[str] = []
            self.deleted: list[int] = []
            self.pick_ready = threading.Event()

        def send(
            self,
            _chat_id: str,
            text: str,
            buttons: Any = None,
            reply_to_message_id: int | None = None,
        ) -> int:
            message_id = len(self.sent) + 1
            self.sent.append((message_id, text, buttons))
            if buttons and str(buttons[0][0].get("callback_data", "")).startswith("pick:"):
                self.pick_ready.set()
            return message_id

        def answer(self, _callback_id: str, _text: str = "") -> object:
            return object()

        def edit(self, _chat_id: str, _message_id: int, text: str, _buttons: Any = None) -> object:
            self.edited.append(text)
            return object()

        def delete(self, _chat_id: str, message_id: int) -> object:
            self.deleted.append(message_id)
            return object()

    class Twins(_FakeProwlarr):
        def search(self, query: str) -> list[RawResult]:
            return list(TWINS)

    composition.use_indexers(monkeypatch, Twins)
    api = Api()
    previous = _environment_port()
    bot = Bot(
        BotConfig("token", "-100"),
        api=cast(TelegramApi, api),
        assemble=lambda: None,
    )
    try:
        #: Прогреть импорт и заглушки настоящим прогоном без --menu (как в тесте образце) -
        #: иначе первый в процессе поиск конкурирует с 2-секундным ожиданием карточки.
        bot.dispatch(
            {
                "message": {
                    "chat": {"id": -100},
                    "from": {"language_code": "ru"},
                    "message_id": 69,
                    "text": "cast мумия",
                }
            }
        )
        bot.run_one()

        bot.dispatch(
            {
                "message": {
                    "chat": {"id": -100},
                    "from": {"language_code": "ru"},
                    "message_id": 70,
                    "text": "cast мумия --menu",
                }
            }
        )

        def choose_first() -> None:
            assert api.pick_ready.wait(timeout=2)
            message_id, _text, buttons = next(
                item
                for item in api.sent
                if item[2] and item[2][0][0]["callback_data"].startswith("pick:")
            )
            bot.dispatch(
                {
                    "callback_query": {
                        "id": "pick",
                        "data": buttons[0][0]["callback_data"],
                        "from": {"language_code": "ru"},
                        "message": {"message_id": message_id, "chat": {"id": -100}},
                    }
                }
            )

        callback = threading.Thread(target=choose_first)
        callback.start()
        bot.run_one()
        callback.join(timeout=2)
        assert not callback.is_alive()

        card_id, _card_text, card_buttons = next(
            item
            for item in api.sent
            if item[2] and item[2][0][0]["callback_data"].startswith("pick:")
        )
        card_callback = card_buttons[0][0]["callback_data"]

        #: Карточка со списком одноимённых должна уйти вместе со строками поиска.
        assert card_id in api.deleted

        #: Кнопка удалённой карточки больше не работает - callback от неё не засчитывается.
        environment = cast(TelegramChoiceEnvironment, _environment_port())
        assert environment.accept(card_callback, card_id) is False

        #: После уборки очередная строка стража уходит новым сообщением, а не правкой трупа.
        edited_before = len(api.edited)
        sent_before = len(api.sent)
        environment.write("проверочная строка после уборки карточки")
        assert len(api.sent) == sent_before + 1
        assert api.sent[-1][2] is None
        assert len(api.edited) == edited_before
    finally:
        configure_choice(previous)


@pytest.mark.machine
def test_the_cancel_button_takes_the_whole_dialog_away_without_a_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-926. Человек передумал: показ не пошёл, диалог убран, отказа в чате нет.

    Планка та же, что у соседних зеркал: подделан один ``Api``, а команда - настоящая
    ``cast мумия --menu`` через :func:`torrcast.cli.main.main`, карточка настоящая, и
    нажимается настоящая кнопка отмены из этой карточки, а не выдуманный callback.

    Проверяются три вещи разом, потому что каждая по отдельности покупается дёшево:
    показ не начался, карточка и сама команда человека удалены, а строки «Каст не
    начался» в чате НЕТ. Вместо неё - всплывающая подсказка, которая мусора не оставляет.
    """

    class Api:
        def __init__(self) -> None:
            self.sent: list[tuple[int, str, Any]] = []
            self.edited: list[str] = []
            self.deleted: list[int] = []
            self.answers: list[str] = []
            self.pick_ready = threading.Event()

        def send(
            self,
            _chat_id: str,
            text: str,
            buttons: Any = None,
            reply_to_message_id: int | None = None,
        ) -> int:
            message_id = len(self.sent) + 1
            self.sent.append((message_id, text, buttons))
            if buttons and str(buttons[0][0].get("callback_data", "")).startswith("pick:"):
                self.pick_ready.set()
            return message_id

        def answer(self, _callback_id: str, text: str = "") -> object:
            self.answers.append(text)
            return object()

        def edit(self, _chat_id: str, _message_id: int, text: str, _buttons: Any = None) -> object:
            self.edited.append(text)
            return object()

        def delete(self, _chat_id: str, message_id: int) -> object:
            self.deleted.append(message_id)
            return object()

    class Twins(_FakeProwlarr):
        def search(self, query: str) -> list[RawResult]:
            return list(TWINS)

    composition.use_indexers(monkeypatch, Twins)
    api = Api()
    previous = _environment_port()
    bot = Bot(
        BotConfig("token", "-100"),
        api=cast(TelegramApi, api),
        assemble=lambda: None,
    )
    try:
        #: Прогреть импорт и заглушки настоящим прогоном без --menu (как в тесте образце) -
        #: иначе первый в процессе поиск конкурирует с 2-секундным ожиданием карточки.
        bot.dispatch(
            {
                "message": {
                    "chat": {"id": -100},
                    "from": {"language_code": "ru"},
                    "message_id": 69,
                    "text": "cast мумия",
                }
            }
        )
        bot.run_one()
        capsys.readouterr()  # прогрев показ ЗАПУСТИЛ - его строки в счёт не идут
        started = len(api.deleted)

        bot.dispatch(
            {
                "message": {
                    "chat": {"id": -100},
                    "from": {"language_code": "ru"},
                    "message_id": 72,
                    "text": "cast мумия --menu",
                }
            }
        )

        #: Что именно нажато - спрашивается СНАРУЖИ потока: провались утверждение здесь,
        #: вопрос остался бы без ответа и повис на пять минут вместо честного красного.
        pressed: list[str] = []

        def press_cancel() -> None:
            assert api.pick_ready.wait(timeout=2)
            message_id, _text, buttons = next(
                item
                for item in api.sent
                if item[2] and item[2][0][0]["callback_data"].startswith("pick:")
            )
            #: Нажимается последняя кнопка ТОЙ ЖЕ карточки, а не выдуманный callback.
            pressed.append(buttons[-1][0]["callback_data"])
            bot.dispatch(
                {
                    "callback_query": {
                        "id": "drop",
                        "data": pressed[-1],
                        "from": {"language_code": "ru"},
                        "message": {"message_id": message_id, "chat": {"id": -100}},
                    }
                }
            )

        callback = threading.Thread(target=press_cancel)
        callback.start()
        bot.run_one()
        callback.join(timeout=2)
        assert not callback.is_alive()
    finally:
        configure_choice(previous)

    card_id, _card_text, _card_buttons = next(
        item for item in api.sent if item[2] and item[2][0][0]["callback_data"].startswith("pick:")
    )
    printed = capsys.readouterr().out

    #: Нажата была именно кнопка отмены - последняя строка карточки со списком.
    assert [data.split(":")[0] for data in pressed] == ["drop"], pressed
    #: Показ не пошёл: ни строки запуска, ни нового пульта под неё.
    assert "играю «Мумия»" not in printed, printed
    assert not any(
        buttons and str(buttons[0][0].get("callback_data", "")).startswith("control:")
        for _message_id, _text, buttons in api.sent[card_id:]
    )
    #: Диалог убран целиком: карточка меню и сама команда человека.
    assert card_id in api.deleted[started:]
    assert 72 in api.deleted[started:]
    #: Отказа в чате нет - есть всплывающая подсказка, которая мусора не оставляет.
    #: Строка отказа берётся у самого каталога и на языке настройки продукта: впиши её
    #: сюда руками по-русски - и сторож промолчал бы на английский ответ бота.
    failure = i18n("failed", chosen_language(), detail="").rstrip()
    assert failure and not any(failure in text for _message_id, text, _buttons in api.sent), (
        api.sent
    )
    assert api.answers == [i18n("cancelled", chosen_language())]
    #: И подсказки про Enter в карточке тоже нет: клавиатуры в чате не существует.
    assert not any("Enter" in text for _message_id, text, _buttons in api.sent)
    assert not any("Enter" in text for text in api.edited)


def test_the_console_question_keeps_its_enter_hint_and_its_ctrl_c(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-926. Кнопка отмены - дело чата: консольный путь остался прежним.

    Две вещи разом, потому что правка задела общий код: подсказка про Enter в терминале
    печатается (там она единственный способ узнать, что даст пустой ввод), а отмена в
    терминале - это по-прежнему Ctrl+C, и она по-прежнему отказ кодом 2 с той же строкой.
    Новый код возврата отмены консоли не достаётся: поднять его тут нечем.
    """
    _answers(monkeypatch, "", "")

    assert main(["моана", "--menu"]) == EXIT_OK
    assert "Enter - «Moana (2016)», пункт 1 из 2" in capsys.readouterr().out

    def interrupted(_prompt: str = "") -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupted)

    assert main(["моана", "--menu"]) == EXIT_INFRA
    assert "команда прервана с клавиатуры" in capsys.readouterr().err


@pytest.mark.machine
def test_bot_understands_the_menu_flag_after_telegram_autocorrects_the_dash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """TC-926: телеграм подменяет `--menu` на `—menu` - карточка выбора обязана прийти."""

    class Api:
        def __init__(self) -> None:
            self.sent: list[tuple[int, str, Any]] = []
            self.edited: list[str] = []
            self.deleted: list[int] = []
            self.pick_ready = threading.Event()

        def send(
            self,
            _chat_id: str,
            text: str,
            buttons: Any = None,
            reply_to_message_id: int | None = None,
        ) -> int:
            message_id = len(self.sent) + 1
            self.sent.append((message_id, text, buttons))
            if buttons and str(buttons[0][0].get("callback_data", "")).startswith("pick:"):
                self.pick_ready.set()
            return message_id

        def answer(self, _callback_id: str, _text: str = "") -> object:
            return object()

        def edit(self, _chat_id: str, _message_id: int, text: str, _buttons: Any = None) -> object:
            self.edited.append(text)
            return object()

        def delete(self, _chat_id: str, message_id: int) -> object:
            self.deleted.append(message_id)
            return object()

    class Twins(_FakeProwlarr):
        def search(self, query: str) -> list[RawResult]:
            return list(TWINS)

    composition.use_indexers(monkeypatch, Twins)
    api = Api()
    previous = _environment_port()
    bot = Bot(
        BotConfig("token", "-100"),
        api=cast(TelegramApi, api),
        assemble=lambda: None,
    )
    try:
        #: Прогреть импорт и заглушки настоящим прогоном без флага (как в тесте образце) -
        #: иначе первый в процессе поиск конкурирует с 2-секундным ожиданием карточки.
        bot.dispatch(
            {
                "message": {
                    "chat": {"id": -100},
                    "from": {"language_code": "ru"},
                    "message_id": 69,
                    "text": "cast мумия",
                }
            }
        )
        bot.run_one()

        bot.dispatch(
            {
                "message": {
                    "chat": {"id": -100},
                    "from": {"language_code": "ru"},
                    "message_id": 71,
                    "text": "cast мумия —menu",
                }
            }
        )

        def choose_first() -> None:
            assert api.pick_ready.wait(timeout=2)
            message_id, _text, buttons = next(
                item
                for item in api.sent
                if item[2] and item[2][0][0]["callback_data"].startswith("pick:")
            )
            bot.dispatch(
                {
                    "callback_query": {
                        "id": "pick",
                        "data": buttons[0][0]["callback_data"],
                        "from": {"language_code": "ru"},
                        "message": {"message_id": message_id, "chat": {"id": -100}},
                    }
                }
            )

        callback = threading.Thread(target=choose_first)
        callback.start()
        bot.run_one()
        callback.join(timeout=2)
        assert not callback.is_alive()
    finally:
        configure_choice(previous)

    #: Карточка со списком пришла - значит флаг `--menu` доехал до argparse настоящим.
    assert any("1. Мумия (1999)" in text for _message_id, text, _buttons in api.sent)
    assert "играю «Мумия» (1999)" in capsys.readouterr().out


def test_the_namesake_line_is_said_before_the_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-198/TC-812: взяли самую живую тёзку - и человек слышит об этом ПЕРЕД стартом.

    Место у строки одно и выбрано не для порядка: фазы поиска к этой секунде уехали
    вверх экрана и читаются как ход работы, а решение про картину человек уносит с
    собой. Раньше на «мумию» не печаталось ничего вовсе - тихо игралась та «Мумия»,
    у которой рой пожирнее.
    """

    class _Twins(_FakeProwlarr):
        def search(self, query: str) -> list[RawResult]:
            return list(TWINS)

    composition.use_indexers(monkeypatch, _Twins)
    _answers(monkeypatch, "", "")

    assert main(["мумия"]) == 0

    printed = capsys.readouterr().out
    take = printed.index("беру «Мумия (2026)» - самая живая из одноимённых")
    start = printed.index("играю «Мумия» (2026)")
    assert take < start, "решение названо вслух до старта показа, а не после"


def test_the_film_with_a_number_in_the_title_is_a_film(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Номер в названии не делает картину сериалом: «Моана 2» — фильм, строк про серии нет."""
    _answers(monkeypatch, "")

    assert main(["моана", "--pick", "2"]) == 0

    printed = capsys.readouterr().out
    assert "сериал" not in printed and "s1e1" not in printed
    key, entry = next(iter(State.load()))
    assert (key, entry.kind, entry.episodes) == ("movie:моана-2:2024", "movie", [])


def test_a_pick_names_the_film_without_a_question(monkeypatch: pytest.MonkeyPatch) -> None:
    """Картину можно назвать флагом - тогда вопроса «Что смотрим?» нет вовсе.

    Номер - ровно тот, что стоит у пункта меню на экране, и называет его человек:
    молчаливой подмены тут нет, есть названный выбор, как у ``--release`` и ``--voice``.
    """
    asked = _answers(monkeypatch)

    assert main(["моана", "--pick", "2"]) == 0

    assert asked == [], "номер назван флагом - спрашивать нечего"
    key, _entry = next(iter(State.load()))
    assert key == "movie:моана-2:2024"


def test_a_pick_works_where_a_menu_cannot_be_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без терминала меню упирается в честный отказ - а с флагом картина названа и там.

    Это и есть назначение флага: любой неинтерактивный сценарий (ssh без pty, скрипт)
    называет номер заранее и не упирается в вопрос, на который некому ответить.
    """
    terminal.use_tty(monkeypatch, tty=False)
    _answers(monkeypatch)

    assert main(["моана", "--pick", "1"]) == 0

    key, _entry = next(iter(State.load()))
    assert key == "movie:moana:2016"


def test_a_pick_outside_the_menu_is_an_honest_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Номер, которого нет в меню, - ошибка вслух, а не молчаливый первый пункт."""
    composition.use_start_unit(monkeypatch, lambda key: pytest.fail("не кастим"))
    _answers(monkeypatch)

    assert main(["моана", "--pick", "7"]) == 1
    assert "номера 7 нет" in capsys.readouterr().err


def test_release_and_file_are_debug_handles_and_show_the_insides(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--release N` и `--file N` — отладочные ручки: внутренности показываем только им."""
    _answers(monkeypatch, "1", "")

    assert main(["моана", "2", "--release", "2", "--file", "1"]) == 0

    printed = capsys.readouterr().out
    assert "файл: Moana.2016.1080p.mkv" in printed
    assert State.load().entries["movie:моана-2:2024"].file_idx == 0


def test_a_hand_picked_number_does_not_trip_the_neighbours_prewarm(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Названный номер относится к выбранной картине, а греются под меню все.

    Прогрев поднимает голову очереди у первых картин списка
    (:data:`~torrcast.domain.prewarm_settings.PREWARM`), и номер, названный руками, у соседки может
    не существовать вовсе: у «Моаны» 2016 года раздачи две, а спрошена третья у «Моаны 2». Соседка
    на этом молчит - спрос идёт с той картины, которую человек выбрал.
    """
    extra = RawResult("Моана 2 / Moana 2 (2024) BDRip 1080p x264", "e" * 40, 4 * GB, 90)

    class _WithSpare(_FakeProwlarr):
        def search(self, query: str) -> list[RawResult]:
            return [*FOUND, extra]

    composition.use_indexers(monkeypatch, _WithSpare)
    _answers(monkeypatch, "")

    assert main(["моана", "--pick", "2", "--release", "3"]) == 0

    assert "релизов 2" not in capsys.readouterr().out, "счёт соседки к выбору не относится"


def test_releases_prints_the_old_table_and_exits(capsys: pytest.CaptureFixture[str]) -> None:
    """`cast releases <запрос>` — та самая таблица, но только по явной просьбе."""
    assert main(["releases", "моана"]) == 0

    printed = capsys.readouterr().out
    assert "Релизы:" in printed and "Качество" in printed
    assert "Moana (2016)" in printed and "Моана 2 (2024)" in printed
    assert "играю" not in printed, "releases ничего не запускает"


def test_releases_ties_each_number_to_its_picture(capsys: pytest.CaptureFixture[str]) -> None:
    """🔴 TC-446. Номер релиза относится к картине своей таблицы - и таблица это говорит.

    Картин в выдаче несколько, нумерация релизов у каждой своя, и одним ``--release N``
    картину не назвать: заголовки нумеруются тем же номером, что пункты меню `cast`
    (и флаг ``--pick``), а строка-подсказка зовёт оба флага.
    """
    assert main(["releases", "моана"]) == 0

    printed = capsys.readouterr().out
    assert "1. Moana (2016) - раздач" in printed, printed
    assert "2. Моана 2 (2024) - раздач" in printed, printed
    assert "--pick M --release N" in printed, printed


def test_the_start_time_means_a_picture_on_the_screen(
    show_unit: FakeShowUnit, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """«Старт NN с» обязан означать картинку, а не «упаковка пошла».

    Доказательство картинки одно: показ увидел ``PLAYING`` и положил флажок. Пока
    флажка нет, CLI честно стоит в фазе «жду телевизор».
    """
    from torrcast.adapters.console.console.progress import Progress
    from torrcast.adapters.stream_pack.forget_playing import forget_playing
    from torrcast.adapters.stream_pack.mark_playing import mark_playing
    from torrcast.adapters.stream_pack.playing_flag import playing_flag

    out = tmp_path / "hls"
    out.mkdir(parents=True, exist_ok=True)
    forget_playing(out)
    show_unit.alive = True  # юнит жив: ждать нам мешает только отсутствие картинки
    config = Config(hls_dir=str(out))

    with pytest.raises(Exception, match="показ не начался"), Progress() as progress:
        AWAIT_PLAYING(config, progress, timeout=0.6)

    mark_playing(out)
    assert playing_flag(out).exists()
    with Progress() as progress:  # флажок на месте - ждать больше нечего
        AWAIT_PLAYING(config, progress, timeout=0.6)


def test_resume_is_silent_and_only_reports_position_in_the_show_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Продолжение не спрашивает; место называет обычная строка показа."""
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query="моана-2"),
    )
    state.save()
    asked = _answers(monkeypatch, "")

    assert main(["моана", "2"]) == 0

    printed = capsys.readouterr().out
    assert asked == []
    assert "с 0:41:07" in printed and "ищу" not in printed


def test_new_plays_the_saved_choice_from_zero_without_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Флаг обнуляет только позицию сохранённого выбора."""
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(
            title="Моана 2",
            magnet="magnet:?xt=1",
            file_idx=7,
            audio=2,
            pos=2467.0,
            dur=5978.0,
            query="моана-2",
        ),
    )
    state.save()
    asked = _answers(monkeypatch, "")

    assert main(["моана", "2", "--new"]) == 0

    saved = State.load().entries["movie:моана-2:2024"]
    assert asked == []
    assert (saved.pos, saved.file_idx, saved.audio, saved.magnet) == (0.0, 7, 2, "magnet:?xt=1")


def test_new_without_a_bookmark_uses_the_normal_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Новая картина с нуля - обычный поиск, а не ошибка про отсутствующую запись."""
    asked = _answers(monkeypatch)

    assert main(["моана", "2", "--new"]) == 0

    saved = State.load().entries["movie:моана-2:2024"]
    assert asked == []
    assert saved.magnet.startswith("magnet:?xt=urn:btih:") and saved.pos == 0.0


def test_new_restarts_the_saved_choice_of_the_picture_picked_in_the_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """После выбора картины закладка ищется по её ключу и не переискивает релиз."""
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(
            title="Моана 2",
            magnet="magnet:?xt=saved-picked",
            file_idx=7,
            audio=1,
            pos=2467.0,
            dur=5978.0,
            query="моана",
        ),
    )
    state.save()
    asked = _answers(monkeypatch)

    assert main(["моана", "--pick", "2", "--new"]) == 0

    saved = State.load().entries["movie:моана-2:2024"]
    assert asked == [], "картину назвали флагом - спрашивать нечего"
    assert (saved.magnet, saved.file_idx, saved.audio, saved.pos) == (
        "magnet:?xt=saved-picked",
        7,
        1,
        0.0,
    )


def test_a_bookmark_of_a_sequel_does_not_answer_which_picture_was_asked(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Имя франшизы без номера зовёт первую часть, а не ту, на которой стоит закладка.

    Запись под запросом «моана» осталась от «Моаны 2»: её когда-то выбрали в меню, а в
    записи лежит текст запроса, а не имя картины. Продолжение по такой записи включало
    другое кино той же франшизы молча.
    """
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query="моана"),
    )
    state.save()
    asked = _answers(monkeypatch)

    assert main(["моана"]) == 0

    printed = capsys.readouterr().out
    assert asked == [], "имя франшизы зовёт первую часть, и спрашивать не о чем"
    assert "беру «Moana (2016)»" in printed
    assert "играю «Moana» (2016)" in printed, printed
    assert State.load().entries["movie:моана-2:2024"].pos == 2467.0, "закладка цела"


def test_the_bookmark_is_resumed_inside_the_picture_that_was_chosen(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Закладка не выброшена: её предлагают той картине, которую человек выбрал.

    Картина названа флагом; после выбора сохранённое место поднимается молча.
    """
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query="моана"),
    )
    state.save()
    asked = _answers(monkeypatch, "")  # вторая картина меню, продолжить с места

    assert main(["моана", "--pick", "2"]) == 0

    printed = capsys.readouterr().out
    assert asked == [], "картину назвали флагом, а место поднимается молча"
    assert "играю «Моана 2»" in printed and "с 0:41:07" in printed, printed
    assert State.load().entries["movie:моана-2:2024"].pos == 2467.0, "продолжаем с места"


def test_a_legacy_record_of_a_film_written_as_a_series_behaves_as_a_film(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Старая ошибка разбора живёт в сохранённом состоянии: «Moana 2» записана ``tv`` с s1e1.

    Парсер починен, но запись живёт и позиция в ней настоящая — терять её нельзя.
    Одна серия в списке сериалом не считается: продолжение молчит и не говорит про серии.
    """
    state = State()
    state.put(
        "tv:moana-2:2024",
        Entry(
            title="Moana 2",
            magnet="magnet:?xt=1",
            kind="tv",
            pos=2566.0,
            dur=5982.0,
            query="моана-2",
            season=1,
            episode=1,
            episodes=[[1, 1, 1]],
        ),
    )
    state.save()
    asked = _answers(monkeypatch, "")

    assert main(["моана", "2"]) == 0

    printed = capsys.readouterr().out
    assert asked == []
    assert "s1e1" not in printed and "Серии" not in printed
    assert State.load().entries["tv:moana-2:2024"].pos == 2566.0, "позиция пользователя цела"


def test_prewarmed_torrents_are_dropped_when_the_show_never_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Обрыв до показа не оставляет прогретые раздачи в TorrServer.

    Прогрев под меню поднимает до :data:`~torrcast.domain.prewarm_settings.PREWARM` раздач ещё до
    первого вопроса. Любой выход мимо ``keep_only`` — Ctrl-C на «Что смотрим?», запуск без
    терминала, «годного релиза нет» — оставлял их жить в TorrServer: наш процесс умирает, а раздачи
    качаются в чужой RAM до перезапуска сервера.
    """
    dropped: list[str] = []
    added: list[str] = []

    class _Counting(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            added.append(magnet)
            return f"hash-{magnet[:30]}"

        def drop(self, torrent_hash: str) -> bool:
            dropped.append(torrent_hash)
            return True

    composition.use_engines(monkeypatch, _Counting)
    monkeypatch.setattr(
        "builtins.input", lambda prompt="": (_ for _ in ()).throw(KeyboardInterrupt)
    )

    assert main(["моана", "--menu"]) != 0, "Ctrl-C на вопросе - не показ"

    assert added, "прогрев под меню раздачи поднимает"
    assert len(dropped) == len(set(added)), "и все они убраны, раз показа не будет"


#: Раздачи «Moana» 2016 - первой живой части, в которую попадает Enter, - в порядке отбора.
SPARE_PICTURE = ("a" * 40, "b" * 40)


def _btih(magnet: str) -> str:
    """infoHash из magnet: по нему видно, какую именно раздачу подняли."""
    return magnet.partition("btih:")[2][:40]


def test_the_spare_release_warms_under_the_menu_not_after_the_first_one_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Под меню греется не только верх выбранной картины, но и её запасной релиз.

    Пока запасной поднимался только в отборе, брак верха стоил человеку полного подъёма
    второй раздачи - метаданные по DHT плюс ffprobe, - и всё это уже после вопроса, то
    есть на глазах. Пауза, пока меню читают, при этом простаивала.
    """
    added: list[str] = []

    class _Counting(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            added.append(magnet)
            return f"hash-{magnet[:30]}"

    composition.use_engines(monkeypatch, _Counting)
    under_question: list[set[str]] = []

    def ask(prompt: str = "") -> str:
        if "Что смотрим?" in prompt:  # вопрос на экране, ответа ещё нет
            deadline = time.monotonic() + 5.0
            while len(added) < 3 and time.monotonic() < deadline:
                time.sleep(0.02)
            under_question.append({_btih(m) for m in added})
        return ""

    monkeypatch.setattr("builtins.input", ask)

    assert main(["моана", "--menu"]) == 0

    assert under_question, "меню про франшизу спросили"
    assert set(SPARE_PICTURE) <= under_question[0], "обе раздачи выбранной картины уже греются"


def test_the_unused_spare_leaves_torrserver_by_its_own_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Верх годен - запасной прибирается до старта показа, и прибирается ПО ХЭШУ.

    Своё убирается поимённо, а не «снести всё, что видно в TorrServer»: раздачи прогрева
    в списке сервера смешаны с чужими, и чистка списком снесла бы чужое.
    """
    added: list[str] = []
    dropped: list[str] = []

    class _Counting(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            added.append(magnet)
            return f"hash-{magnet[:30]}"

        def drop(self, torrent_hash: str) -> bool:
            dropped.append(torrent_hash)
            return True

    composition.use_engines(monkeypatch, _Counting)
    _answers(monkeypatch, "", "")

    assert main(["моана"]) == 0

    raised = {f"hash-{magnet[:30]}" for magnet in added}
    played = f"hash-magnet:?xt=urn:btih:{SPARE_PICTURE[0][:10]}"
    spare = f"hash-magnet:?xt=urn:btih:{SPARE_PICTURE[1][:10]}"
    assert spare in raised, "запасной релиз грелся"
    assert set(dropped) == raised - {played}, "лишнее убрано, и убрано по хэшам"
    assert played not in dropped, "играем то, что осталось"


def _started_film(monkeypatch: pytest.MonkeyPatch, pos: float = 2467.0) -> None:
    """Начатый фильм в состоянии - единственный вход на путь resume."""
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=pos, dur=5978.0, query="моана-2"),
    )
    state.save()
    composition.use_warm_file(monkeypatch, lambda *a, **k: None)


def test_silent_resume_does_not_start_a_competing_position_warmer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """После удаления вопроса рой принадлежит только владельцу показа.

    Читателей у раздачи по-прежнему ровно один - юнит показа: грелки тут нет вовсе, и
    подделка её появление роняет. Подъём раздачи (``add``) читателем не является и с
    ffmpeg за рой не спорит: TC-571 спрашивает им ровно метаданные - жива ли записанная
    раздача, - и спрашивает ОДИН раз, той же строкой, которой раздачу через секунду
    поднимет сам юнит (``add`` идемпотентен, второй раз она уже поднята).
    """
    _started_film(monkeypatch)
    added: list[str] = []

    class _Counting(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            added.append(magnet)
            return f"hash-{magnet[:30]}"

    composition.use_engines(monkeypatch, _Counting)
    composition.use_warm_file(monkeypatch, lambda *a, **k: pytest.fail("грелки быть не должно"))

    assert main(["моана", "2"]) == 0
    assert added == ["magnet:?xt=1"], "CLI спрашивает записанную раздачу один раз и не читает её"


def test_a_dry_run_takes_even_the_chosen_torrent_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--dry`` с поиском убирает ВСЁ поднятое - и раздачу, которую «сыграли бы», тоже.

    Лишнее из прогрева убиралось всегда (:meth:`Bench.keep_only`), а выбранная раздача
    оставалась жить в TorrServer. Сухой прогон заведён ровно затем, чтобы
    следов не оставалось, - и сносить он обязан ровно своё, по явным хэшам.
    """
    added: list[str] = []
    dropped: list[str] = []

    class _Counting(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            torrent_hash = super().add(magnet)
            added.append(torrent_hash)
            return torrent_hash

        def drop(self, torrent_hash: str) -> bool:
            dropped.append(torrent_hash)
            return True

    composition.use_engines(monkeypatch, _Counting)
    _answers(monkeypatch, "")

    assert main(["моана", "--dry"]) == 0

    # Чужие прогревы догорают в своих потоках и доносят свои сносы оттуда - дожидаемся,
    # но не дольше пяти секунд: на сломанном коде выбранная раздача не уходит никогда.
    deadline = time.monotonic() + 5.0
    while set(added) - set(dropped) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert added, "прогрев под меню раздачи поднимал"
    assert set(dropped) <= set(added), "снесено только своё, чужих хэшей тут нет"
    assert not set(added) - set(dropped), "убрано всё поднятое, выбранная - тоже"


def test_a_dry_run_names_the_chosen_file_not_the_request_echo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-302. Сухой прогон печатал ЭХО ЗАПРОСА (``series.want``), и дефект «сыграла
    серию „- 84" вместо s1e1» (сквозная нумерация против сезонной) им не виден ВООБЩЕ:
    числа по сериям, снятые всухую, были враньём. Теперь ``--dry`` называет, ЧТО он
    выбрал бы, - имя файла внутри раздачи.
    """

    class _SeriesProwlarr(_FakeProwlarr):
        def search(self, query: str) -> list[RawResult]:
            return [
                RawResult(
                    "Киберпанк: Бегущие по краю / Cyberpunk: Edgerunners (2022) "
                    "S01 WEB-DL 1080p x264 | D",
                    "e" * 40,
                    9 * GB,
                    55,
                )
            ]

    class _SeriesTorrServer(_FakeTorrServer):
        def wait_files(
            self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
        ) -> list[TorrFile]:
            return [TorrFile(i, f"Cyberpunk.S01E0{i + 1}.mkv", 2 * GB) for i in range(3)]

    composition.use_indexers(monkeypatch, _SeriesProwlarr)
    composition.use_engines(monkeypatch, _SeriesTorrServer)
    _answers(monkeypatch, "")

    assert main(["киберпанк", "s1e3", "--dry"]) == 0

    said = capsys.readouterr().out
    assert "Cyberpunk.S01E03.mkv" in said, "сухой прогон называет ВЫБРАННЫЙ файл"
    assert "каста нет" in said


def test_an_instant_answer_is_no_worse_than_before(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enter нажали мгновенно — путь остаётся прежним: раздача та же, позиция цела.

    Подъём в этот момент ещё в пути, и ответ его не ждёт: показ поднимет ту же раздачу
    сам. Ускорение, которого не случилось, — это просто прежняя скорость.
    """
    _started_film(monkeypatch)
    started: list[str] = []

    class _Slow(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            time.sleep(0.3)  # человек успевает ответить раньше, чем раздача поднимется
            return f"hash-{magnet[:30]}"

    composition.use_engines(monkeypatch, _Slow)
    composition.use_start_unit(monkeypatch, lambda key: started.append(key))
    _answers(monkeypatch, "")

    assert main(["моана", "2"]) == 0
    assert started == ["movie:моана-2:2024"]
    kept = State.load().get("movie:моана-2:2024")
    assert kept is not None and kept.pos == 2467.0, "продолжаем с сохранённого места"


def test_two_pictures_under_one_name_reach_the_last_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-371. Строку про двусмысленность человек читает там же, где решение о картине.

    Развести пару одноимённых картин одного года отбору нечем: имя и год у них совпадают,
    и каталог сводит их в одну кучку. Значит слово остаётся за справкой, а место строки -
    последнее перед стартом, рядом с гейтом года: решение о КАРТИНЕ человек уносит с собой.
    """
    from torrcast.domain.facts.origin import Origin

    composition.use_passport(
        monkeypatch,
        lambda *a, **k: Origin(title="Moana", year=2016, namesake="Моана (фильм, 2026)"),
    )
    _answers(monkeypatch, "1", "")

    assert main(["моана"]) == 0

    printed = capsys.readouterr().out
    assert "под этим именем и годом картин две" in printed
    assert "«Моана (фильм, 2026)»" in printed


def _live_show(show_unit: FakeShowUnit) -> None:
    """Состояние живого показа: юнит поднят и держит другую картину."""
    state = State.load()
    state.put(
        "movie:матрица:1999",
        Entry(
            title="Матрица",
            magnet="magnet:?xt=urn:btih:" + "a" * 40,
            pos=128.0,
            torrent="a" * 40,
        ),
    )
    state.save()
    show_unit.alive = True


def test_a_second_cast_says_the_tv_is_busy_with_our_show(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-482. Один телевизор - один показ, и вторая команда говорит это словами зрителя.

    Прежде вторая ``cast`` на занятый телевизор вела себя как первая: ни строки о том, что
    на экране уже идёт фильм, ни слова о том, что выбор его оборвёт. Зритель узнавал об
    этом по погасшей картинке.
    """
    _live_show(show_unit)
    _answers(monkeypatch, "2", "")

    assert main(["моана"]) == 0

    printed = capsys.readouterr().out
    assert "на телевизоре сейчас идёт «Матрица»" in printed, printed
    assert "0:02:08" in printed, "видно и то, докуда досмотрели"
    assert "этот показ прервётся" in printed, printed


def test_the_menu_prewarm_stands_aside_while_our_show_is_on_air(
    show_unit: FakeShowUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-482. Пока идёт показ, прогрев под меню не поднимает ни одной раздачи.

    Замер 10-08: рядом с живым показом шла вторая ``cast``, и её прогрев тянул из роя
    чужие раздачи, писал их на тот же диск и читал ту же сеть - про показ он не знал
    ничего и не притормаживал. Показ первичен: раздумья зрителя оплачивает скорость
    нашего меню, а не его картинка.
    """
    added: list[str] = []

    class _Counting(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            added.append(magnet)
            return f"hash-{magnet[:30]}"

    composition.use_engines(monkeypatch, _Counting)
    _live_show(show_unit)

    under_question: list[int] = []

    def ask(prompt: str = "") -> str:
        if "Что смотрим?" in prompt:  # вопрос на экране, ответа ещё нет
            time.sleep(0.5)  # прогрев успел бы поднять три раздачи вдесятеро быстрее
            under_question.append(len(added))
        return ""

    monkeypatch.setattr("builtins.input", ask)

    assert main(["моана", "--menu"]) == 0

    assert under_question == [0], "под меню живого показа не поднято ни одной раздачи"


def test_a_hand_named_release_weighs_the_same_on_both_early_exits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Один и тот же ``--release N`` не может зависеть от того, совпал ли текст запроса.

    Ранних выхода по закладке два: один находит запись по тексту запроса, другой
    предлагает её внутри выбранной картины. Названный руками релиз на второй не заходит -
    раздачу там выбирает человек, - и на первый теперь тоже: иначе `cast моана 2` с
    флагом играл записанную раздачу, выбросив флаг молча, а `cast моана` с тем же флагом
    его уважал.
    """
    played = []
    for saved_query in ("моана-2", "моана"):  # текст запроса совпал с записью - и нет
        state = State()
        state.put(
            "movie:моана-2:2024",
            Entry(
                title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query=saved_query
            ),
        )
        state.save()
        _answers(monkeypatch, "2", "")  # вторая картина меню, если о ней спросят

        assert main(["моана", "2", "--release", "2"]) == 0

        capsys.readouterr()
        played.append(State.load().entries["movie:моана-2:2024"].magnet[:24])

    assert played[0] == played[1], "флаг решает исход одинаково на обоих путях"
    assert played[0] == "magnet:?xt=urn:btih:dddd", played  # названный релиз, не записанный


def test_a_hand_named_release_says_out_loud_that_it_drops_the_bookmark(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Названный релиз играется с начала - и сохранённое место теряется НЕ молча.

    Стартовая запись показа ложится под тот же ключ картины, то есть 41:07 после такого
    запуска не восстановить ниоткуда. `--release N` человек набирает про раздачу, а не
    про закладку, и узнать о её пропаже он обязан строкой до старта.
    """
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query="моана-2"),
    )
    state.save()
    _answers(monkeypatch, "2", "")

    assert main(["моана", "2", "--release", "2"]) == 0

    said = capsys.readouterr().out
    assert (
        "«Моана 2» - релиз назван руками, играю с начала; "
        "сохранённое место 0:41:07 не поднимаю" in said
    ), said
    assert State.load().entries["movie:моана-2:2024"].pos == 0.0, "играли с начала"


@pytest.mark.parametrize(
    ("flag", "number", "named", "torrent"),
    [("--release", "2", "релиз", "d"), ("--file", "1", "файл", "c")],
)
def test_a_hand_named_choice_beats_new_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flag: str,
    number: str,
    named: str,
    torrent: str,
) -> None:
    """Явный релиз или файл выбирается заново; ``--new`` не глотает его молча."""
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=saved", pos=2467.0, query="моана-2"),
    )
    state.save()
    _answers(monkeypatch)

    assert main(["моана", "2", "--new", flag, number]) == 0

    played = State.load().entries["movie:моана-2:2024"]
    said = capsys.readouterr().out
    assert played.magnet.startswith(f"magnet:?xt=urn:btih:{torrent * 4}")
    assert (
        f"«Моана 2» - {named} назван руками, играю выбранное с начала; "
        "сохранённый выбор не поднимаю" in said
    ), said


def test_continuing_without_a_flag_keeps_the_bookmark_and_stays_silent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Обычный `cast моана 2` по-прежнему продолжает начатое, и лишней строки нет.

    Условие раннего выхода выросло на ``not args.pinned``, и цена ошибки тут - потерянное
    место просмотра у того, кто никаких флагов не набирал.
    """
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query="моана-2"),
    )
    state.save()
    asked = _answers(monkeypatch, "")

    assert main(["моана", "2"]) == 0

    said = capsys.readouterr().out
    assert asked == []
    assert "не поднимаю" not in said, said
    kept = State.load().entries["movie:моана-2:2024"]
    assert kept.pos == 2467.0, "место осталось на 41:07"
    assert kept.magnet == "magnet:?xt=1", "играли записанную раздачу, а не выбранную заново"


#: Выдача «Кухни 6», сведённая к сути: все раздачи подписаны ОДНИМ сезоном, и число
#: стоит в самом имени картины - ровно та форма, на которой показ отказывал (TC-564).
KITCHEN = [
    RawResult(
        "Кухня 6 / Kuhnya 6 (2017) WEB-DL 1080p | 6 сезон, 1-20 из 20", "e" * 40, 20 * GB, 44
    ),
    RawResult("Кухня 6 / Kuhnya 6 (2017) SATRip | 6 сезон [1-20 из 20]", "f" * 40, 6 * GB, 11),
]


class _KitchenProwlarr(_FakeProwlarr):
    def search(self, query: str) -> list[RawResult]:
        return list(KITCHEN)


class _KitchenTorrServer(_FakeTorrServer):
    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
    ) -> list[TorrFile]:
        return [TorrFile(n - 1, f"Кухня 6/Kuhnya.s06e{n:02d}.mkv", 1 * GB) for n in range(1, 21)]


def test_a_series_named_by_its_only_season_still_plays(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-564. «Кухня 6», когда ВСЕ раздачи подписаны «6 сезон», включается.

    Форма выдачи дословная и самая частая у сериала, снятого целым сезоном: число стоит
    и в имени картины, и в подписи сезона. Каталог заводил такую картину с ``part=6``,
    номер запроса читался номером ЧАСТИ, план просил `s1e1` - и накрыть его не могла ни
    одна раздача. Человек получал `rc=1` и «раздач 2, но сезона 1 среди них нет - названы
    6» при живой картине: показа не было вовсе.

    Тест берёт именно эту форму. Возьми он раздачу, молчащую о сезоне, или «Кухня (6
    сезон)» - прошёл бы мимо дефекта: обе эти формы играли и до починки.
    """
    composition.use_indexers(monkeypatch, _KitchenProwlarr)
    composition.use_engines(monkeypatch, _KitchenTorrServer)
    _answers(monkeypatch, "", "")

    assert main(["кухня", "6"]) == 0, "картина живая, раздачи живые - это показ"

    printed = capsys.readouterr().out
    assert "играю «Кухня 6»" in printed, printed
    # Молчаливого прочтения не бывает: номер человек написал сам и вправе знать, чем
    # мы его сочли.
    assert "номер 6 читаю сезоном, а не частью" in printed, printed
    assert "сезона 1 среди них нет" not in printed, "отказа больше нет"


def test_the_bot_answers_in_the_language_the_previous_cast_command_remembered() -> None:
    """🔴 TC-929: `cast --ru` из чата меняет язык СЛЕДУЮЩЕГО ответа без рестарта юнита.

    Планка тут та же, что у соседних проб бота: подделан только ``Api``, а команда идёт
    настоящая - через :func:`torrcast.cli.main.main`. Прочитай бот язык один раз при
    старте, флаг подействовал бы лишь после перезапуска, и владелец сказал бы «не
    работает». Бот тут заводится ДО переключения нарочно.
    """

    class Api:
        def __init__(self) -> None:
            self.sent: list[str] = []

        def send(
            self,
            _chat_id: str,
            text: str,
            _buttons: Any = None,
            reply_to_message_id: int | None = None,
        ) -> int:
            del reply_to_message_id
            self.sent.append(text)
            return len(self.sent)

        def answer(self, _callback_id: str, _text: str = "") -> object:
            return object()

        def edit(self, _chat_id: str, _message_id: int, _text: str, _buttons: Any = None) -> object:
            return object()

        def delete(self, _chat_id: str, _message_id: int) -> object:
            return object()

    def ask(text: str, message_id: int) -> None:
        """Одно сообщение в чат от клиента, у которого язык интерфейса английский."""
        bot.dispatch(
            {
                "message": {
                    "chat": {"id": -100},
                    "from": {"language_code": "en"},
                    "message_id": message_id,
                    "text": text,
                }
            }
        )

    api = Api()
    previous = _environment_port()
    bot = Bot(BotConfig("token", "-100"), api=cast(TelegramApi, api), assemble=lambda: None)
    try:
        ask("cast", 1)
        assert api.sent == [i18n("help", "en")], "до переключения бот отвечает по-английски"

        ask("cast --ru", 2)
        bot.run_one()

        ask("cast", 3)
    finally:
        configure_choice(previous)

    assert load_config().language == "ru", "флаг из чата обязан лечь в настройку продукта"
    assert api.sent[-1] == i18n("help", "ru")
    assert api.sent[-1] != i18n("help", "en"), "русский и английский ответы обязаны различаться"
