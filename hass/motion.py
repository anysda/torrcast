"""Одно слово о показе для карточки плеера: замер, которым берётся пауза, и защёлка
собственной команды моста, которая того замера не ждёт."""

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

#: Сколько закладка может уехать от места, где мост сказал ``toggle``, пока приёмник
#: берёт команду, секунды. Сторож кладёт закладку на диск раз в
#: :data:`torrcast.usecases.watch.WATCH_SECONDS` (10 с), поэтому после команды туда
#: может лечь ещё одна запись ИДУЩЕГО показа: она не «поехала снова», а доехала.
#: Сдвиг дальше этого запаса - уже факт: приёмник команду не взял, показ идёт.
HELD_MARGIN = 15.0

#: Слова состояния, которыми мост отвечает карточке плеера.
IDLE, STARTING, PLAYING, PAUSED, TORN = "idle", "starting", "playing", "paused", "torn"


class Motion:
    """Сдвиг закладки между опросами и слово о показе, которое из него выходит.

    Меряется по опросам того, кто спрашивает: Home Assistant опрашивает мост раз в
    несколько секунд, и каждый опрос - это замер. Никто не спрашивал - замера нет, и
    паузы мост не называет.

    Собственную команду моста замер не ждёт: :meth:`toggle` переворачивает слово в ту
    же секунду и держит его защёлкой. Снимает защёлку факт, а не таймер: закладка
    поехала дальше :data:`HELD_MARGIN` - показ идёт, простояла :data:`STILL_SECONDS`
    после команды - стоит.
    """

    def __init__(self, still: float = STILL_SECONDS, clock: Callable[[], float] = time.monotonic):
        self._still = still
        self._clock = clock
        self._seen: tuple[str, float] = ("", -1.0)
        self._since = 0.0
        self._word = ""
        self._held = ""
        self._held_at: tuple[str, float] = ("", -1.0)

    def standing(self, key: str, position: float) -> bool:
        """Стоит ли закладка дольше порога; сдвинулась - счёт начинается заново."""
        now = self._clock()
        if self._seen != (key, position):
            self._seen, self._since = (key, position), now
            return False
        return now - self._since >= self._still

    def toggle(self) -> None:
        """Перевернуть слово по собственной команде моста, не дожидаясь замера.

        ``toggle`` - переключатель: «играю» становится «паузой», «пауза» - «играю».
        Защёлка ставится на тот показ и то место закладки, которые замер видит сейчас:
        другой показ её не наследует, а сдвиг дальше :data:`HELD_MARGIN` её снимает.
        Стояние считается заново от команды: старая пауза, которую команда как раз
        сняла, не должна снимать защёлку «играю» на первом же опросе.
        """
        self._held = PLAYING if self._word == PAUSED else PAUSED
        self._held_at = self._seen
        self._since = self._clock()

    def phase(self, shown: PlaybackSnapshot | None, *, active: bool, starting: bool) -> str:
        """Одно слово о показе для карточки плеера.

        Тёмный экран называется ``torn`` и при живом юните тоже: живой юнит картинки не
        доказывает, и продукт сам отказывается звать такой показ идущим
        (:class:`torrcast.usecases.status.Status`). Зритель перед чёрным экраном - это не
        «играю».

        🔴 Паузой закладка называется только у ИДУЩЕГО показа: тёмный экран отсекается
        выше, а показ, не давший ни кадра с момента своего поднятия, тоже не пауза -
        стоять там нечему. Признак - факт (:attr:`~torrcast.domain.playback_snapshot.
        PlaybackSnapshot.moved`), а не порог позиции: у продолжения запись уже несёт
        чужую, положительную позицию ПРОШЛОГО сеанса, и порог `position > 0` называл бы
        паузой показ, который в ЭТОМ запуске ещё не сдвинул её ни разу (TC-1002, живая
        приёмка 03-09-2026).
        """
        if active:
            if shown is not None and shown.dark_since:
                return TORN
            # Кадра этого запуска ещё не было - декодировать нечего, и паузой
            # зрителя это не назвать, каким бы ни было число позиции на диске.
            standing = (
                shown is not None and shown.moved and self.standing(shown.key, shown.position)
            )
            self._word = self._word_of(shown, standing)
            return self._word
        if starting:
            return STARTING
        if shown is not None and shown.dark_since:
            return TORN
        return IDLE

    def _word_of(self, shown: PlaybackSnapshot | None, standing: bool) -> str:
        """Слово с защёлкой собственной команды; защёлку снимает факт, а не таймер.

        «Пауза» держится, пока закладка ТОГО ЖЕ показа не уехала дальше
        :data:`HELD_MARGIN` от места команды; уехала - приёмник команду не взял.
        «Играю» держится, пока закладка не простояла :data:`STILL_SECONDS` после
        команды; простояла - показ так и стоит. Обоих случаев нет - слово замера.
        """
        if self._held == PAUSED:
            if shown is not None and (
                shown.key != self._held_at[0]
                or abs(shown.position - self._held_at[1]) > HELD_MARGIN
            ):
                self._held = ""
            else:
                return PAUSED
        if self._held == PLAYING:
            if standing:
                self._held = ""
            else:
                return PLAYING
        return PAUSED if standing else PLAYING
