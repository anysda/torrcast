"""Мост между четырьмя маршрутами и продуктом: показ, пульт, переход и снимок.

Своих правил тут нет. Показ поднимается той же :func:`torrcast.cli.main.main`, что и в
консоли, под тем же перехватом вывода, каким его зовёт бот
(:func:`tgbot.command_result.command_result`) - оттуда же берётся и словесная причина
отказа. Пульт пишет слово в тот же файл, что кнопки бота. Переход называет следующую
серию тем же :meth:`torrcast.domain.entry.Entry.advance`, которым её называет сторож
показа, и играет её тем же запросом «имя s1e4», каким её назвал бы человек.

🔴 Команда исполняется в ГЛАВНОМ потоке, как и у бота (:meth:`tgbot.bot.Bot.run_one`), и
это не стиль: ``cast`` ставит на время команды свой обработчик SIGTERM
(:func:`torrcast.cli.answered.answered`), а из чужого потока это не делается вовсе -
``signal only works in main thread``. Показ, отпущенный в рабочий поток, умирал бы этой
строкой на каждом запросе, ничего не сыграв. Поэтому HTTP живёт в потоке, а очередь
команд - в главном.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Callable, Sequence
from queue import Queue

from hass.motion import Motion
from hass.payload import payload
from hass.refused_error import RefusedError
from hass.say import SEEKBY, TOGGLE, say
from hass.volume import Volume
from tgbot.command_result import command_result
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.health.machine_probe import MachineProbe
from torrcast.cli.main import main as run_cast
from torrcast.domain.config import Config
from torrcast.domain.json_value import JsonValue
from torrcast.domain.slugify import slugify
from torrcast.domain.version import __version__
from torrcast.domain.why import why
from torrcast.ports.playback_session import PlaybackSession
from torrcast.ports.state_store.slot import store
from torrcast.runtime.playback_session import playback_session

BUSY, NOTHING_PLAYING, NO_NEXT, NO_VOLUME = "busy", "nothing_playing", "no_next", "no_volume"
STOP, VOLUME = "stop", "volume"
#: Слова, которые принимает ``POST /api/control``.
COMMANDS = (TOGGLE, SEEKBY, VOLUME, STOP)

_Command = Callable[[Sequence[str] | None], int]


class Bridge:
    """Всё, что мост умеет, за одним объектом; HTTP над ним - только разбор запроса."""

    def __init__(
        self,
        *,
        session: PlaybackSession | None = None,
        command: _Command = run_cast,
        settings: Callable[[], Config] = load_config,
        volume: Volume | None = None,
        motion: Motion | None = None,
    ) -> None:
        self._session = playback_session() if session is None else session
        self._command = command
        self._settings = settings
        self._volume = volume
        self._motion = motion or Motion()
        self._lock = threading.Lock()
        self._queue: Queue[list[str] | None] = Queue()
        self._starting = False
        self._last_error = ""

    # ------------------------------------------------------------------ снимок

    def state(self) -> dict[str, JsonValue]:
        """Тело ``GET /api/state``: снимок показа, громкость и место под сегменты."""
        config = self._settings()
        active = self._session.active()
        shown = self._session.snapshot(self._session.key() if active else "")
        return payload(
            shown,
            version=__version__,
            tv=config.tv or "",
            state=self._motion.phase(shown, active=active, starting=self._starting),
            volume=self._volume_of(config).level(),
            disk_free=MachineProbe.disk_free(config.hls_dir),
            last_error=self._last_error,
        )

    # ------------------------------------------------------------------ команды

    def play(self, query: str) -> str:
        """``POST /api/play``: поднять показ штатным путём, ничего не спрашивая."""
        return self._start([query])

    def control(self, command: str, arg: float) -> None:
        """``POST /api/control``: пульт идущего показа."""
        if not self._session.active():
            raise RefusedError(NOTHING_PLAYING)
        if command == VOLUME:
            if not self._volume_of(self._settings()).set(arg):
                raise RefusedError(NO_VOLUME)
            return
        if command == STOP:
            self._start([STOP])
            return
        say(f"{SEEKBY} {arg:g}" if command == SEEKBY else TOGGLE)

    def next(self) -> None:
        """``POST /api/next``: следующая серия той же раздачи, названная запросом."""
        following = self._following()
        if following is None:
            raise RefusedError(NO_NEXT)
        self._start([following])

    # ------------------------------------------------------------------ внутреннее

    def _following(self) -> str | None:
        """Запрос на следующую серию; ``None`` - фильм, последняя серия или тишина."""
        if not self._session.active():
            return None
        entry = store().load().get(self._session.key())
        if entry is None:
            return None
        after = entry.advance()
        if after.done or not after.label:
            return None
        # Запрос собирается из записи ровно так же, как его собирает поиск следующего
        # сезона (:func:`torrcast.usecases.next_season._next_season`), а серия встаёт в
        # него так же, как её называет человек: `cast киберпанк s2e5` (TC-807).
        words = (entry.query or slugify(entry.title)).replace("-", " ")
        return f"{words} {after.label}"

    def _start(self, args: list[str]) -> str:
        """Отдать команду рабочему потоку; очереди нет, второй заход - это отказ."""
        with self._lock:
            if self._starting:
                raise RefusedError(BUSY)
            self._starting = True
            self._last_error = ""  # прошлый отказ живёт до начала следующего показа
        self._queue.put(args)
        return secrets.token_hex(4)

    def run(self) -> None:
        """Исполнять команды, пока не попросят уйти. Зовётся из ГЛАВНОГО потока."""
        while self.run_one():
            pass

    def run_one(self) -> bool:
        """Исполнить одну команду; ``False`` - в очередь положили просьбу уйти."""
        args = self._queue.get()
        try:
            if args is None:
                return False
            self._run(args)
            return True
        finally:
            self._queue.task_done()

    def stop(self) -> None:
        """Вывести цикл команд из ожидания: мост уходит."""
        self._queue.put(None)

    def _run(self, args: list[str]) -> None:
        """Исполнить команду и запомнить её словесный отказ тем же словом, что консоль."""
        try:
            result = command_result(self._command, args)
            if result.code:
                self._last_error = result.detail
        except Exception as error:
            self._last_error = why(error)
        finally:
            with self._lock:
                self._starting = False

    def _volume_of(self, config: Config) -> Volume:
        """Громкость ТОГО приёмника, который назван настройкой прямо сейчас.

        Адрес меняется живой командой ``cast --tv``, и мост её переживает: сменился
        адрес - прежнее соединение отпускается, иначе громкость уезжала бы на телевизор,
        который в этом доме уже не показывает.
        """
        address = config.tv or ""
        if self._volume is not None and self._volume.address != address:
            self._volume.close()
            self._volume = None
        if self._volume is None:
            self._volume = Volume(address)
        return self._volume

    def close(self) -> None:
        """Отпустить приёмник: мост уходит, соединение за собой не оставляем."""
        if self._volume is not None:
            self._volume.close()
