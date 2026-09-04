"""Мост между шестью маршрутами и продуктом: поиск, показ, продолжение, пульт, переход и снимок.

Своих правил тут нет. Показ поднимается той же :func:`torrcast.cli.main.main`, что и в
консоли, под тем же перехватом вывода бота (:func:`tgbot.command_result.command_result`)
- оттуда же берётся словесная причина отказа. Пульт пишет слово в тот же файл, что кнопки
бота. Переход называет следующую серию тем же :meth:`torrcast.domain.entry.Entry.advance`
и играет её тем же запросом «имя s1e4», каким её назвал бы человек. Поиск
(:meth:`Bridge.search`) отдаёт ровно то, что нашёл бы `search_circle` на том же приёмнике,
и запоминает показанный порядок (:mod:`hass.searching`); номер пункта в его ответе - тот
же ``--pick N``, которым CLI понимает выбор.

🔴 Команда показа идёт в ГЛАВНОМ потоке, как и у бота: поручения моста живут отдельно
(:mod:`hass.orders`), и там же названо, почему. Поиск в эту очередь не встаёт: он ничего
не показывает и не сигналит, и ждать главного потока ему незачем.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable

from hass.following import following
from hass.motion import Motion
from hass.orders import Command, Orders
from hass.payload import payload
from hass.posters import Posters
from hass.refused_error import RefusedError
from hass.say import SEEKBY, TOGGLE, say
from hass.searching import DETECT, REMEMBER, SEARCH, Detect, Remember, Search, searching
from hass.stopping import STOP, stopping
from hass.volume import Volume
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.health.machine_probe import MachineProbe
from torrcast.cli.main import main as run_cast
from torrcast.domain.config import Config
from torrcast.domain.json_value import JsonValue
from torrcast.domain.version import __version__
from torrcast.ports.playback_session import PlaybackSession
from torrcast.runtime.playback_session import playback_session

BUSY, NOTHING_PLAYING, NO_NEXT, NO_VOLUME = "busy", "nothing_playing", "no_next", "no_volume"
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
        """Тело ``GET /api/state``: снимок показа, громкость и место под сегменты."""
        config = self._settings()
        active = self._session.active()
        shown = self._session.snapshot(self._session.key() if active else "")
        return payload(
            # Место у карточки своё, пока перемотка моста приземляется (:meth:`Motion.aimed`).
            self._motion.aimed(shown),
            version=__version__,
            tv=config.tv or "",
            state=self._motion.phase(shown, active=active, starting=self._orders.underway()),
            volume=self._volume_of(config).level(),
            disk_free=MachineProbe.disk_free(config.hls_dir),
            last_error=self._orders.last_error,
            picture=self._posters.picture(shown if active else None, self._session.stream_address),
        )

    def poster(self, name: str) -> tuple[bytes, str] | None:
        """``GET /api/poster/<имя>``: байты картинки и её тип; чужое имя - ``None``."""
        return self._posters.read(name)

    # ------------------------------------------------------------------ команды

    def search(self, query: str) -> list[JsonValue]:
        """``POST /api/search``: список картин тем же поиском, что и показ, мимо очереди.

        Весь шаг - у :func:`hass.searching.searching`: профиль приёмника, круг поиска,
        память показанного порядка под ``--pick N`` и поле ``default`` у той записи,
        которую включил бы голый :meth:`play` без номера.
        """
        return searching(self._settings(), query, self._search, self._detect, self._remember)

    def play(self, query: str, pick: int | None = None) -> str:
        """``POST /api/play``: поднять показ; с ``pick`` - ровно картину под этим номером
        из :meth:`search`, флагом ``--pick N``, которым его знает CLI."""
        args = [query] if pick is None else [query, "--pick", str(pick)]
        return self._start(args)

    def resume(self) -> str:
        """``POST /api/resume``: поднять показ ровно так, как это делает пустой ``cast``.

        Картину и место выбирает ПРОДУКТ, а не мост: сюда уходит пустой argv, и дальше
        последнее смотренное называет тот же
        :func:`torrcast.usecases.cast_command._default_query._default_query`, а место
        поднимает та же закладка. Складывать это на стороне моста значило бы завести
        второй ответ на один вопрос. Отказ пустому ``query`` у :meth:`play` остаётся:
        показ ПО ЗАПРОСУ без запроса - по-прежнему брак, а это другая просьба.
        """
        return self._start([])

    def control(self, command: str, arg: float) -> None:
        """``POST /api/control``: пульт идущего показа, а остановка - дверь наружу.

        Остановка стоит ВЫШЕ отказов и ни про показ, ни про подъём не спрашивает
        (:func:`hass.stopping.stopping`). Остальному пульту без идущего показа делать
        нечего: громкость и ``toggle`` уезжают приёмнику, который ничего не играет.
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
        say(f"{SEEKBY} {arg:g}" if command == SEEKBY else TOGGLE)
        self._motion.commanded(command, arg)

    def next(self) -> None:
        """``POST /api/next``: следующая серия той же раздачи, названная запросом."""
        query = following(self._session)
        if query is None:
            raise RefusedError(NO_NEXT)
        self._start([query])

    # ------------------------------------------------------------------ внутреннее

    def _start(self, args: list[str]) -> str:
        """Отдать команду рабочему потоку; очереди нет, второй заход - это отказ."""
        if not self._orders.take(args):
            raise RefusedError(BUSY)
        return secrets.token_hex(4)

    def abandoned(self) -> bool:
        """Снят ли заказ на идущий подъём: спрашивает это сам подъём.

        Кладёт факт :func:`hass.stopping.stopping`, и там же названо, почему отдельным.
        """
        return self._orders.abandoned()

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
        """Громкость ТОГО приёмника, который назван настройкой прямо сейчас: адрес
        меняется живой командой ``cast --tv``, и старое соединение мост отпускает."""
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
