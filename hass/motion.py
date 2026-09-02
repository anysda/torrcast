"""Одно слово о показе для карточки плеера и замер, которым берётся пауза."""

from __future__ import annotations

import time
from collections.abc import Callable

from torrcast.domain.playback_snapshot import PlaybackSnapshot

#: Сколько закладка должна простоять на месте, чтобы это была пауза зрителя, секунды.
#:
#: 🔴 Числа паузы в состоянии нет вовсе: приёмник называет ``PAUSED`` только владеющему
#: сендеру, а вторым pychromecast MEDIA-статуса не получить
#: (:data:`torrcast.domain.debug_handles.CTL_ENV`). Снаружи пауза видна ровно одним
#: способом - закладка стоит. Сторож показа кладёт её на диск раз в
#: :data:`torrcast.usecases.watch.WATCH_SECONDS` (10 с), поэтому идущий показ выглядит
#: стоящим до десяти секунд законно; порог взят с запасом в две пропущенные записи.
STILL_SECONDS = 25.0

#: Слова состояния, которыми мост отвечает карточке плеера.
IDLE, STARTING, PLAYING, PAUSED, TORN = "idle", "starting", "playing", "paused", "torn"


class Motion:
    """Сдвиг закладки между опросами и слово о показе, которое из него выходит.

    Меряется по опросам того, кто спрашивает: Home Assistant опрашивает мост раз в
    несколько секунд, и каждый опрос - это замер. Никто не спрашивал - замера нет, и
    паузы мост не называет.
    """

    def __init__(self, still: float = STILL_SECONDS, clock: Callable[[], float] = time.monotonic):
        self._still = still
        self._clock = clock
        self._seen: tuple[str, float] = ("", -1.0)
        self._since = 0.0

    def standing(self, key: str, position: float) -> bool:
        """Стоит ли закладка дольше порога; сдвинулась - счёт начинается заново."""
        now = self._clock()
        if self._seen != (key, position):
            self._seen, self._since = (key, position), now
            return False
        return now - self._since >= self._still

    def phase(self, shown: PlaybackSnapshot | None, *, active: bool, starting: bool) -> str:
        """Одно слово о показе для карточки плеера.

        Тёмный экран называется ``torn`` и при живом юните тоже: живой юнит картинки не
        доказывает, и продукт сам отказывается звать такой показ идущим
        (:class:`torrcast.usecases.status.Status`). Зритель перед чёрным экраном - это не
        «играю».
        """
        if active:
            if shown is not None and shown.dark_since:
                return TORN
            standing = shown is not None and self.standing(shown.key, shown.position)
            return PAUSED if standing else PLAYING
        if starting:
            return STARTING
        if shown is not None and shown.dark_since:
            return TORN
        return IDLE
