"""Реальный приёмник: pychromecast по адресу из конфига, со своим сторожем подвиса.

Заводит его композиционный корень; занятия показа лежат в файлах рядом."""

from __future__ import annotations

from torrcast.adapters.chromecast.cast.drop_seek import _drop_seek
from torrcast.adapters.chromecast.cast.nudge import _nudge
from torrcast.adapters.chromecast.cast.past_deadly import _past_deadly
from torrcast.adapters.chromecast.cast.play import _play
from torrcast.adapters.chromecast.cast.position import _position
from torrcast.adapters.chromecast.cast.receiver_talk import _Talk
from torrcast.adapters.chromecast.cast.reload import _reload
from torrcast.adapters.chromecast.cast.replay import _replay
from torrcast.adapters.chromecast.cast.say_skip import _say_skip
from torrcast.adapters.chromecast.cast.stop import _stop
from torrcast.adapters.chromecast.cast.watch_seek import _watch_seek
from torrcast.domain.position import Position


class ChromecastReceiver(_Talk):
    """Реальный приёмник: pychromecast по адресу из конфига.

    Почему не catt: его ``cast <url>`` гонит любой URL через yt-dlp и не умеет передать
    подсказки формата HLS (:data:`HLS_HINTS`), без которых ресивер отвечает LOAD ERROR.
    ⚠️ Порт 8009 открыт даже в standby, любой коннект будит ТВ — поэтому соединение
    поднимается лениво, только когда кастить действительно собираются.

    ⚠️ **Сендер к приёмнику должен быть ровно один.** У всех соединений pychromecast
    ``source_id`` один и тот же — ``sender-0`` (socket_client.py), поэтому второй процесс,
    подключившийся к тому же ТВ, для приёмника неотличим от первого. Ломается это так:
    показ идёт (ТВ качает сегменты и рисует картинку), а владеющий сессией процесс
    получает на ``GET_STATUS`` пустой ``MEDIA_STATUS`` — то есть вечный ``IDLE`` при
    ``app_id=CC1AD845`` и живом ``status_text``. Дальше сторож честно решает, что LOAD не
    взяли, закрывает приложение и в итоге гасит показ. Замерено: три прогона
    подряд умерли ровно так, и каждый раз рядом был чужой сендер — пробоотборник,
    диагностический скрипт или их ``quit_app`` минутой раньше. Отсюда правило для
    диагностики: наблюдать за показом можно чем угодно, кроме второго pychromecast —
    позиция и так лежит в state.json, а забор сегментов виден в ``ss``.
    """

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        """Начать показ и дождаться картинки (:func:`_play`)."""
        _play(self, url, title, at)

    def stop(self, quit_app: bool = False) -> None:
        """Снять каст, а по просьбе - закрыть и приложение (:func:`_stop`)."""
        _stop(self, quit_app)

    def position(self, front: float = 0.0) -> Position:
        """Где показ и жив ли он; попутно вся работа сторожа (:func:`_position`)."""
        return _position(self, front)

    def replay(self, at: float, paused: bool = False) -> float:
        """Поднять свой погасший показ (:func:`_replay`).

        ``paused=True`` - вернуть сессию на закладку, НЕ начиная показ: паузу ставил
        зритель, и снимает её тоже он, с пульта.
        """
        return _replay(self, at, paused)

    def refusal(self) -> str:
        """Почему последний :meth:`replay` не дал картинки; пусто - он удался.

        Отвечает на вопрос лестницы воскрешения
        (:class:`torrcast.usecases.revive_playback._blame._Blaming`): «нельзя» и «упал» -
        разные исходы, и в ленте они обязаны стоять разными строками, иначе замер
        подъёмов приёмника не читается вовсе.
        """
        return self._refused

    def seek(self, pos: float) -> None:
        """Перемотка от владеющего сендера — ровно та же MEDIA-команда, что с пульта.

        Существует ради диагностики (:data:`torrcast.domain.debug_handles.CTL_ENV`): автотест кнопку
        нажать не может, а вторым pychromecast её не подать вовсе — приёмник считает второе
        соединение тем же сендером (докстринг класса). Состояние сторожа (``_peak``, счётчики
        подвиса) здесь намеренно не трогается: перемотка проверяется вместе со сторожем, и подчищать
        за собой его вход значило бы проверять не то.
        """
        self._device().media_controller.seek(pos)

    def pause(self) -> None:
        self._device().media_controller.pause()

    def resume(self) -> None:
        self._device().media_controller.play()

    def volume(self, step: float) -> None:
        """Сдвинуть громкость малым шагом кинокастового пульта."""
        device = self._device()
        current = float(getattr(device.status, "volume_level", 0.0) or 0.0)
        device.set_volume(max(0.0, min(1.0, current + step)))

    # ------------------------------------------------------------------ внутреннее

    def _say_skip(self, back: float) -> None:
        """Назвать зрителю перешагнутую плёнку (:func:`_say_skip`)."""
        _say_skip(self, back)

    def _past_deadly(self, at: float) -> float:
        """Откуда поднимать показ, если кусок его убивает (:func:`_past_deadly`)."""
        return _past_deadly(self, at)

    def _reload(self) -> bool:
        """Повтор LOAD посреди показа (:func:`_reload`)."""
        return _reload(self)

    def _nudge(self, pos: float, front: float = 0.0) -> None:
        """Расшевелить зависший приёмник (:func:`_nudge`)."""
        _nudge(self, pos, front)

    def _watch_seek(self, pos: float, state: str) -> None:
        """Заметить перемотку и померить ожидание картинки (:func:`_watch_seek`)."""
        _watch_seek(self, pos, state)

    def _drop_seek(self, why: str) -> None:
        """Закрыть перемотку, кончившуюся ничем (:func:`_drop_seek`)."""
        _drop_seek(self, why)
