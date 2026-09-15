"""Мост между шестью маршрутами и продуктом: поиск, показ, продолжение, пульт, переход и снимок.

Своих правил тут нет. Показ поднимается той же :func:`torrcast.cli.main.main`, что и в
консоли, под тем же перехватом вывода бота (:func:`tgbot.command_result.command_result`)
- оттуда же берётся словесная причина отказа. Пульт пишет слово в тот же файл, что кнопки
бота. Переход называет следующую серию :meth:`torrcast.domain.entry.Entry.advance` и играет
её запросом «имя s1e4», каким её назвал бы человек. Поиск (:meth:`Bridge.search`) отдаёт
то, что нашёл бы `search_circle` на том же приёмнике, и запоминает показанный порядок
(:mod:`hass.searching`); номер пункта в ответе - тот же ``--pick N``, что понимает CLI.

🔴 Команда показа идёт в ГЛАВНОМ потоке, как и у бота: поручения моста живут отдельно
(:mod:`hass.orders`), и там же названо, почему. Поиск в эту очередь не встаёт: он ничего
не показывает и не сигналит, и ждать главного потока ему незачем.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Unpack

from hass.following import following
from hass.hit_posters import hits
from hass.motion import Motion
from hass.next_show import next_show
from hass.orders import Command, Orders
from hass.payload import payload
from hass.play_argv import play_argv
from hass.play_extras import _PlayExtras
from hass.posters import Posters
from hass.posters_left import posters_left
from hass.refused_error import BUSY, NO_REMOTE, NO_VOLUME, NOTHING_PLAYING, RefusedError
from hass.remote_refused import remote_refused
from hass.resuming import _resume
from hass.say import SEEKBY, TOGGLE, say
from hass.search_progress import search_progress
from hass.searching import DETECT, REMEMBER, SEARCH, Detect, Remember, Search, searching
from hass.starting import starting
from hass.stopping import STOP, _abandoned, stopping
from hass.tab_cast import tab_cast
from hass.volume import Volume
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.health.machine_probe import MachineProbe
from torrcast.cli.main import main as run_cast
from torrcast.domain.config import Config
from torrcast.domain.json_value import JsonValue
from torrcast.domain.version import __version__
from torrcast.ports.playback_session import PlaybackSession
from torrcast.ports.refusal_record import refusal_record
from torrcast.runtime.playback_session import playback_session
from torrcast.usecases.start_progress import START
from torrcast.usecases.warm.warm_root import warm_root
from web.warm_wiring import CATALOG, WARM

VOLUME = "volume"


class Bridge:
    """Всё, что мост умеет, за одним объектом; HTTP над ним - только разбор запроса."""

    def __init__(
        self,
        *,
        session: PlaybackSession | None = None,
        command: Command = run_cast,
        search: Search = SEARCH,
        detect: Detect = DETECT,
        remember: Remember = REMEMBER,
        settings: Callable[[], Config] = load_config,
        volume: Volume | None = None,
        motion: Motion | None = None,
        posters: Posters | None = None,
    ) -> None:
        self._session = playback_session() if session is None else session
        self._orders = Orders(command)
        self._search = search
        self._detect = detect
        self._remember = remember
        self._settings = settings
        self._volume = volume
        self._motion = motion or Motion()
        self._posters = posters or Posters()

    # ------------------------------------------------------------------ снимок

    def state(self) -> dict[str, JsonValue]:
        """Тело ``GET /api/state``: снимок показа, громкость и место под прогрев."""
        config = self._settings()
        active = self._session.active()
        shown = self._session.snapshot(self._session.key() if active else "")
        word = self._motion.phase(shown, active=active, starting=self._orders.underway())
        return payload(
            self._motion.aimed(shown),
            version=__version__,
            build=MachineProbe.build_id(),
            tv=config.tv or "",
            state=word,
            volume=self._volume_of(config).level(),
            disk_free=MachineProbe.disk_free(str(warm_root(config.warm_dir))),
            last_error=self._orders.last_error,
            refusal=refusal_record().read(),
            picture=self._posters.picture(shown if active else None, self._session.stream_address),
            has_next=following(self._session) is not None,
            start=START.seen(),
        )

    def poster(self, name: str) -> tuple[bytes, str] | None:
        """``GET /api/poster/<имя>``: байты картинки и её тип; чужое имя - ``None``."""
        return self._posters.read(name)

    # ------------------------------------------------------------------ команды

    def search(self, query: str) -> list[JsonValue]:
        """``POST /api/search``: список картин тем же поиском, что и показ, мимо очереди.

        Весь шаг - у :func:`hass.searching.searching`: профиль приёмника, круг поиска, память
        порядка под ``--pick N`` и ``default`` у записи, которую включил бы голый :meth:`play`."""
        said = self._settings(), query, self._search, self._detect, self._remember
        return searching(*said, warm=WARM)

    def search_progress(self, query: str) -> tuple[list[JsonValue], bool, float]:
        """``POST /api/search`` с ``progressive: true``: каталог первым, круг (:data:`WARM`).

        Третье поле - сколько секунд ещё дозапрашивать обложки готового списка; 0 - не в пути."""
        said = self._settings(), query, self._detect, self._remember
        results, partial = search_progress(*said, warm=WARM, catalog=CATALOG, covers=hits)
        coming = not partial and hits.pending(results)
        return results, partial, posters_left(query) if coming else 0.0

    def play(self, query: str, pick: int | None = None, **extras: Unpack[_PlayExtras]) -> str:
        """``POST /api/play``: argv собирает :func:`play_argv`, доводы проверены заранее."""
        return self._start(play_argv(query, pick, **extras))

    def resume(self) -> str:
        return _resume(self._start)

    def control(self, command: str, arg: float) -> None:
        """``POST /api/control``: пульт идущего показа, а остановка - дверь наружу.

        Остановка ВЫШЕ отказов (:func:`hass.stopping.stopping`), без показа пульту нечего делать.
        🔴 Вкладка пульта не берёт (TC-1210), а её каст «На ТВ» берёт (:mod:`hass.tab_cast`).
        """
        if command == STOP:
            stopping(self._orders, self._session)
            return
        if not self._session.active():
            raise RefusedError(NOTHING_PLAYING)
        if command == VOLUME:
            if not self._volume_of(self._settings()).set(arg):
                raise RefusedError(NO_VOLUME)
            return
        if not tab_cast(self._settings(), command, arg):
            if remote_refused(self._settings(), command):
                raise RefusedError(NO_REMOTE)
            say(f"{SEEKBY} {arg:g}" if command == SEEKBY else TOGGLE)
        self._motion.commanded(command, arg)

    def next(self, body: dict[str, JsonValue] | None = None) -> None:
        """``POST /api/next``: следующая серия той же раздачи, названная запросом."""
        if args := next_show(self._session, body or {}):
            self._start(args)

    # ------------------------------------------------------------------ внутреннее

    def _start(self, args: list[str]) -> str:
        """Отдать команду рабочему потоку; идущий показ новый СНИМАЕТ (ТЗ §7.4)."""
        if not starting(self._orders, self._session, args):
            raise RefusedError(BUSY)
        return secrets.token_hex(4)

    def abandoned(self) -> bool:
        return _abandoned(self._orders)

    def run(self) -> None:
        """Исполнять команды, пока не попросят уйти. Зовётся из ГЛАВНОГО потока."""
        self._orders.run()

    def run_one(self) -> bool:
        """Исполнить одну команду; ``False`` - в очередь положили просьбу уйти."""
        return self._orders.run_one()

    def stop(self) -> None:
        """Вывести цикл команд из ожидания: мост уходит."""
        self._orders.leave()

    def _volume_of(self, config: Config) -> Volume:
        """Громкость приёмника из настройки прямо сейчас: ``cast --tv`` меняет его на лету."""
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
