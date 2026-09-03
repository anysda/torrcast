"""Одно слово о показе для карточки плеера: правда о паузе из записи показа, а для
записи без неё - прежний замер стоящей закладки; плюс защёлка собственной команды
моста, которая ни того ни другого не ждёт."""

from __future__ import annotations

import time
from collections.abc import Callable

from torrcast.domain.playback_snapshot import PlaybackSnapshot

#: Сколько закладка должна простоять на месте, чтобы это была пауза зрителя, секунды.
#:
#: Замер - ЗАПАСНОЙ путь. Основной - факт: слово ``PAUSED`` приёмник называет только
#: владеющему сендеру, и показ кладёт его в запись на переходе, с немедленным сбросом
#: на диск (:attr:`torrcast.domain._playing._Playing.paused`). Замер остаётся для записи,
#: в которой правды нет, - её писал юнит прежней версии. Сторож кладёт закладку на диск
#: раз в :data:`torrcast.usecases.watch.WATCH_SECONDS` (10 с), поэтому идущий показ
#: выглядит стоящим до десяти секунд законно; порог взят с запасом в две пропущенные
#: записи.
STILL_SECONDS = 25.0

#: Сколько закладка может уехать от места, где мост сказал ``toggle``, пока приёмник
#: берёт команду, секунды. Действует там же, где замер: в записи без слова о паузе.
#: Сторож кладёт закладку на диск раз в :data:`torrcast.usecases.watch.WATCH_SECONDS`
#: (10 с), поэтому после команды туда может лечь ещё одна запись ИДУЩЕГО показа: она не
#: «поехала снова», а доехала. Сдвиг дальше этого запаса - уже факт: приёмник команду
#: не взял, показ идёт.
HELD_MARGIN = 15.0

#: Сколько защёлка собственной команды моста держится против факта записи, секунды.
#: Команда уходит показу через файл, и запись узнаёт решение приёмника на следующем
#: круге его опроса: до той записи факт ещё СТАРЫЙ, и поверить ему сразу значило бы
#: вернуть карточке слово, которое команда как раз отменила.
TOOK_SECONDS = 6.0

#: Слова состояния, которыми мост отвечает карточке плеера.
IDLE, STARTING, PLAYING, PAUSED, TORN = "idle", "starting", "playing", "paused", "torn"


class Motion:
    """Слово о показе из факта записи, а без факта - из сдвига закладки между опросами.

    Меряется по опросам того, кто спрашивает: Home Assistant опрашивает мост раз в
    несколько секунд, и каждый опрос - это замер. Никто не спрашивал - замера нет, и
    паузы мост не называет.

    Собственную команду моста ни факт, ни замер не ждут: :meth:`toggle` переворачивает
    слово в ту же секунду и держит его защёлкой. Снимает защёлку факт, а не таймер:
    запись назвала другое слово спустя :data:`TOOK_SECONDS` после команды (приёмник её
    не взял), а в записи без слова о паузе - прежние мерки: закладка поехала дальше
    :data:`HELD_MARGIN` или простояла :data:`STILL_SECONDS` после команды.
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
        """Перевернуть слово по собственной команде моста, не дожидаясь ни факта, ни замера.

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

        Пауза берётся из ФАКТА записи, когда показ его туда кладёт
        (:attr:`~torrcast.domain.playback_snapshot.PlaybackSnapshot.paused`): владеющий
        сендер знает слово приёмника через круг опроса, и ждать тут нечего. Факта нет
        (запись писал юнит прежней версии) - работает прежний замер стоящей закладки.

        🔴 Паузой показ называется только дав кадр в ЭТОМ запуске: тёмный экран
        отсекается выше, а показу без кадра стоять нечему. Признак - факт
        (:attr:`~torrcast.domain.playback_snapshot.PlaybackSnapshot.moved`), а не порог
        позиции: у продолжения запись уже несёт чужую, положительную позицию ПРОШЛОГО
        сеанса, и порог `position > 0` называл бы паузой показ, который в ЭТОМ запуске
        ещё не сдвинул её ни разу (TC-1002, живая приёмка 03-09-2026).
        """
        if active:
            if shown is not None and shown.dark_since:
                return TORN
            if shown is not None and shown.paused:
                self._seen = (shown.key, shown.position)  # toggle() ставит защёлку на показ
                fact = PAUSED if shown.moved and shown.paused == "PAUSED" else PLAYING
                self._word = self._word_of_fact(shown.key, fact)
                return self._word
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

    def _word_of_fact(self, key: str, fact: str) -> str:
        """Слово из факта записи; защёлка команды живёт лишь окно её приземления.

        Расходящийся с командой факт внутри окна :data:`TOOK_SECONDS` - это ещё СТАРЫЙ
        факт: показ узнаёт решение приёмника на своём круге опроса и сбрасывает его на
        диск на переходе, а до той записи слово держит защёлка. Окно вышло, а факт
        прежний - приёмник команду не взял, и слово возвращается к правде. Другой показ
        защёлку не наследует и внутри окна.
        """
        if key != self._held_at[0]:
            self._held = ""
        if self._held and self._held != fact and self._clock() - self._since < TOOK_SECONDS:
            return self._held
        self._held = ""
        return fact

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
