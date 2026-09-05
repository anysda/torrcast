"""Источник показа: служба раздач и НАША раздача в ней.

Спрашивают его на краю показа: сторож упаковки и погасший экран приёмника."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.probe_settings import META_GRACE
from torrcast.domain.swarm_kept_up import swarm_kept_up
from torrcast.domain.swarm_supply import ENOUGH, swarm_supply
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    TorrServer = Any


@dataclass
class Supply:
    """Источник показа: служба раздач и НАША раздача в ней. Спрашивают его на краю показа.

    🔴 Обрыв входа показ и раньше переживал, но объяснить его не мог: упаковка умирает
    одинаково и когда просел рой, и когда службы раздач не стало вовсе. Разница между
    этими двумя случаями - вся разница для человека: в первом ждать бессмысленно, во
    втором показ поднимется сам. Замерено на перезапуске службы под показом: показ гас за
    3.5-12 с, человек 14 с не видел ни строки, а потом получал «приёмник не досмотрел
    поток» - обвинение приёмника, который ни в чём не виноват. Спросить источник стоит
    двух запросов и делается это ровно там, где показ уже кончается.

    ⚠️ В горячем пути этих вопросов быть не должно: раздача сегментов не ждёт ни журнал,
    ни лишний запрос. Поэтому :meth:`trouble` зовут только два места, и оба - край показа:
    упаковка объявила себя мёртвой и приёмник погасил экран.

    Второе назначение - :meth:`restore`. Раздачу после аварии возвращает МАГНИТ, потому
    что в URL потока едет только хэш (:meth:`TorrServer.stream_url`), а служба, заведя
    раздачу по голому хэшу, остаётся без трекеров: замерено - 25 с и ноль байт.
    """

    #: Клиент службы. Свой, а не общий с показом: вопросы задаются из сторожа, а коротким
    #: сроком (:data:`PROBE_TIMEOUT`) мёртвая служба отличается от живой сразу.
    server: TorrServer
    #: Хэш НАШЕЙ раздачи. Всё, что делает :class:`Supply`, делается по нему и только по
    #: нему: чужие раздачи в службе не наше дело - ни считать, ни убирать.
    torrent_hash: str = ""
    #: Магнит той же раздачи - из записи картины. Трекеры живут здесь и больше нигде.
    magnet: str = ""
    #: Последняя замеченная авария источника; пусто - аварии не было или её уже разгребли.
    #: По нему же :meth:`check` знает, что раздачу надо вернуть магнитом, даже если она
    #: уже числится в списке: заведённая по голому хэшу, она числится там точно так же.
    lost: str = ""
    #: Правда ли последняя проверка вернула раздачу магнитом. Об этом говорят вслух - и
    #: человеку, и следу, - потому что это и есть возврат трекеров.
    restored: bool = False
    #: Монотонный момент последнего возврата: от него отсчитывается :data:`META_GRACE`.
    restored_at: float = 0.0
    #: Выбранный файл и его паспортная длительность задают расход исходника на 1.0x.
    file_index: int = 0
    duration: float = 0.0
    #: Окно наблюдений сеанса: доли реального времени, по одной на каждый замер снабжения.
    #: Ровно то же, что уходит в след полем ``ratio``, - второго прибора тут нет.
    seen: list[float] = field(default_factory=list)
    #: Чей это сеанс: раздача и номер файла. Сменились - окно начинается заново, иначе
    #: серия отвечала бы за снабжение предыдущей.
    seen_for: tuple[str, int] = ("", -1)
    #: Правда ли рой хоть раз за сеанс вёз достаточно (:func:`swarm_kept_up`). По нему
    #: конец показа отличает «подача была здорова, а картинки не было» от вины источника.
    kept_up: bool = False
    #: Правда ли ПОСЛЕДНИЙ ответ был жалобой на просевший рой. Из всех бед источника
    #: только эта меряется нашим же спросом, и только её конец показа вправе снимать
    #: окном сеанса: служба, легшая насмерть, лежит одинаково и на живом, и на мёртвом.
    thin: bool = False

    def check(self) -> str:
        """Что не так с ИСТОЧНИКОМ прямо сейчас; пусто - источник в порядке.

        Три вопроса по нарастающей, и каждый отвечает за свой вид аварии: служба не
        отвечает вовсе; служба жива, но нашей раздачи в ней нет; раздача есть, а
        метаданных у неё нет - это она и есть, заведённая по голому хэшу из нашего же URL
        потока, без трекеров.

        Заметив, что служба вернулась, метод тут же возвращает ей раздачу МАГНИТОМ
        (:meth:`_restore`) - и только после этого говорит, что источник в порядке. Иначе
        «в порядке» было бы враньём: раздача без трекеров ищет пиров одним DHT и за 25 с
        не приносит ни байта (замерено).

        🔴 Отвечает метод про СЕЙЧАС, и просевший рой называет просевшим: на живом показе
        это не строка человеку, а действие - упаковка переходит в ожидание источника
        (:func:`torrcast.usecases.revive_playback._endure._endure`), а не умирает. Судить
        просадку виной источника или посмертным показанием - дело того, кто ХОРОНИТ показ
        (:func:`torrcast.usecases.playback._show_end._blame_the_end`), и для этого метод
        оставляет два факта: :attr:`thin` и :attr:`kept_up`.
        """
        self.restored = self.thin = False
        if not self.torrent_hash:
            return ""
        whose = (self.torrent_hash, self.file_index)
        if whose != self.seen_for:  # новая серия - окно наблюдений начинается заново
            self.seen, self.seen_for, self.kept_up = [], whose, False
        try:
            if not self.server.alive():
                return self._blame(phrase("stream_probe.service_down"))
            if not self.server.listed(self.torrent_hash):
                self._blame(phrase("stream_probe.torrent_lost"))
            else:
                status = self.server.status(self.torrent_hash)
                files = status.get("file_stats")
                if not isinstance(files, list) or not files:
                    if time.monotonic() - self.restored_at < META_GRACE:
                        return ""  # раздачу только что вернули магнитом - метаданные ещё едут
                    self._blame(phrase("stream_probe.no_trackers"))
                elif self.lost:
                    pass
                else:
                    measured = swarm_supply(status, self.file_index, self.duration)
                    if measured is None:
                        return ""
                    ratio, got, need = measured
                    enough = ratio >= ENOUGH
                    journal().supply(ratio, got, need, enough)
                    self.seen.append(ratio)
                    self.kept_up = swarm_kept_up(self.seen)
                    if enough:
                        return ""
                    self.thin = True
                    return phrase(
                        "stream_probe.thin_swarm",
                        got=f"{got:.2f}",
                        need=f"{need:.2f}",
                        ratio=f"{ratio:.2f}",
                    )
        except InfraError as exc:
            return self._blame(str(exc))
        return self._restore()

    def _restore(self) -> str:
        """Вернуть раздачу магнитом; пусто - вернули (или возвращать было нечего).

        Идемпотентно и у нас, и у службы: infohash тот же, значит и раздача та же - дубля
        не заводится, а трекеры из магнита к ней возвращаются. Чужих раздач это не
        касается никак: всё, что делает :class:`Supply`, делается по нашему хэшу.

        ⚠️ Магнит берётся из записи картины и ниоткуда больше: ходить за ним в индексеры
        посреди аварии было бы вторым способом не показать кино.
        """
        why_source = self.lost
        if not self.magnet:
            return why_source  # магнита нет - вернуть раздачу нечем, врать не о чем
        try:
            self.server.add(self.magnet)
        except InfraError:
            # служба ещё не поднялась
            return why_source or phrase("stream_probe.service_down")
        self.lost, self.restored, self.restored_at = "", True, time.monotonic()
        return ""

    def _blame(self, why_source: str) -> str:
        self.lost = why_source
        return why_source
