"""Лента показа: манифест на весь фильм, а в tmpfs - окно вокруг места просмотра.

Заводит её показ (:mod:`torrcast.usecases.playback`), а спрашивает раздача по http.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from torrcast.ports.pack_run.pack_run import PackRun
from torrcast.usecases.feed_pack.feed_front import _front, _weight
from torrcast.usecases.feed_pack.feed_restart import _restart
from torrcast.usecases.feed_pack.feed_seam import _seam
from torrcast.usecases.feed_pack.feed_segment import _have, _segment, _warm
from torrcast.usecases.feed_pack.feed_shrink import _shrink, _skip
from torrcast.usecases.feed_pack.feed_state import _State
from torrcast.usecases.feed_pack.feed_steer import _steer
from torrcast.usecases.feed_pack.feed_stop import _rest, _stop
from torrcast.usecases.feed_pack.feed_survive import _mute, _survive
from torrcast.usecases.feed_pack.feed_sweep import _prune, _sweep


@dataclass(slots=True)
class Feed(_State):
    """Упаковка по требованию: манифест обещает весь фильм, в tmpfs лежит окно.

    Это ответ на железное ограничение: приёмнику нужен манифест на всю длительность,
    иначе у показа нет ни таймлайна, ни перемотки, — а целый фильм ни в RAM, ни на диск
    не влезает. Развязка в том, что манифест и файлы живут порознь:

    * :meth:`Grid.manifest` перечисляет **все** сегменты фильма и не меняется никогда;
    * файлы под этими именами появляются только там, где приёмник смотрит прямо сейчас;
    * запрос сегмента, которого нет, — это и есть перемотка. Показ не отвечает 404
      (после него ресивер капризничает минутами), а перезапускает упаковку с нужного
      места и отдаёт кусок, как только он готов.

    Отсюда же берётся честная позиция: имя сегмента = его место в фильме, ``-copyts``
    держит исходные метки времени, и приёмник считает время от начала фильма, а не от
    начала куска. Никаких смещений показу пересчитывать не нужно.
    """

    @property
    def duration(self) -> float:
        return self.grid.duration

    def manifest(self) -> bytes:
        return self.grid.manifest().encode("utf-8")

    def segment(self, slot: int) -> Path | None:
        """Файл сегмента ``slot``; ``None`` — его не будет (:func:`_segment`)."""
        return _segment(self, slot, self._steer, self._seam)

    def _warm(self, slot: int) -> Path | None:
        """Прогретый на диске кусок этого места или ``None`` (:func:`_warm`)."""
        return _warm(self, slot)

    def _seam(self, slot: int) -> None:
        """Прогретое впереди на исходе - поднять упаковку за его концом (:func:`_seam`)."""
        _seam(self, slot, self.restart)

    def have(self, slot: int) -> bool:
        """Есть ли кусок этого места — в окне показа или в прогретом (:func:`_have`)."""
        return _have(self, slot)

    def _steer(self, slot: int) -> bool:
        """Что делать с упаковкой ради сегмента ``slot`` (:func:`_steer`)."""
        return _steer(self, slot, self.restart)

    def _mute(self) -> None:
        """Источник молчит дольше срока - это тоже обрыв (:func:`_mute`)."""
        _mute(self)

    def _survive(self, packer: PackRun) -> bool:
        """Упаковка оборвалась сама: пробуем ещё или сдаёмся (:func:`_survive`)."""
        return _survive(self, packer)

    def restart(self, slot: int) -> None:
        """Начать упаковку с сегмента ``slot`` (:func:`_restart`)."""
        _restart(self, slot, self._shrink)

    def _shrink(self, slot: int, size: int = 0) -> bool:
        """Ужать тяжёлый кусок на месте; ``False`` - пропуск (:func:`_shrink`)."""
        return _shrink(self, slot, size)

    def _skip(self, slot: int, size: int, reason: str) -> bool:
        """Честный пропуск места, которое нельзя отдать приёмнику (:func:`_skip`)."""
        return _skip(self, slot, size, reason)

    def sweep(self) -> None:
        """Сдать успевшее, поднять оборванное, придержать несданное (:func:`_sweep`)."""
        _sweep(self, self.restart)

    def prune(self, played: float) -> None:
        """Убрать из tmpfs то, чего показу уже не нужно (:func:`_prune`)."""
        _prune(self, played)

    def front(self, played: float = 0.0) -> float:
        """Докуда показ обеспечен подряд от позиции ``played`` (:func:`_front`)."""
        return _front(self, played)

    def drift(self) -> float:
        """Насколько нарезанное разошлось с манифестом, секунды (:meth:`Packer.drift`)."""
        packer = self.packer
        return 0.0 if packer is None else packer.drift(self.grid)

    def weight(self) -> int:
        """Сколько байт лежит в tmpfs прямо сейчас (:func:`_weight`)."""
        return _weight(self)

    def trouble(self) -> str:
        """Почему показ дальше не идёт, если не идёт; пусто — всё в порядке.

        Мёртвый ffmpeg сам по себе поводом остановить показ не является: дочитанный до
        конца вход (:meth:`Packer.finished`) - это конец фильма, остаток которого уже в
        tmpfs, а обрыв лечится следующей упаковкой. ⚠️ Одного кода 0 для этого мало:
        вход, умерший на середине, тоже выходит нулём, и здесь такой прогон числится
        обрывом, а не концом (:meth:`_steer`).
        Ошибкой это становится, только когда обрывы пошли подряд (:attr:`limit`).
        """
        return self.fatal

    def stall(self, why_source: str) -> None:
        """Упаковка сдалась, но виноват ИСТОЧНИК: показ не умирает, а ждёт его возврата.

        🔴 Три оборванных подряд прогона (:attr:`limit`) означают «показывать нечего»
        только тогда, когда источник в порядке. Служба раздач, которую перезапустили,
        рвёт вход ровно так же - и старая упаковка объявляла себя мёртвой насовсем через
        3.5-12 с, хотя ждать оставалось три секунды. Спрашивает источник сторож
        (:class:`Supply`), а здесь снимается приговор: обрывы забываются, показ переходит
        в «источника нет» и продолжает пробовать. Вернулся источник - прогон выложит
        кусок, и признак снимется сам (:meth:`_steer`).
        """
        self.fatal = ""
        self.crashes = 0
        self.offline = why_source

    def halted(self) -> bool:
        packer = self.packer
        return packer is not None and packer.halted

    def rest(self) -> bool:
        """Остаток фильма прогрет целиком — упаковку гасим (:func:`_rest`)."""
        return _rest(self)

    def halt(self) -> None:
        packer = self.packer
        if packer is not None:
            packer.halt()

    def stop(self) -> None:
        """Показ окончен: упаковка гаснет, каталог показа пустеет (:func:`_stop`)."""
        _stop(self)
