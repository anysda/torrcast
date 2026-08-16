"""Показывает состояние текущего или последнего сеанса."""

from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.ports.clock import Clock
from torrcast.ports.console import Console
from torrcast.ports.playback_session import PlaybackSession

#: Доля фильма, с которой прогрев считается полным в статусе. Не единица: хвост сетки
#: короче шага, и последний кусок доезжает позже всех - а «интернет не нужен» верно уже
#: тогда, когда впереди лежит всё, что зритель успеет посмотреть.
WARMED_RATIO = 0.99


class Status:
    """Сценарий команды ``cast status``.

    🔴 Живой юнит не доказывает картинку на экране. Юнит переживает смерть источника
    нарочно - прогретое досматривается без сети, а вернувшийся источник поднимает показ
    сам, - и всё это время играть может быть нечем. Замер: с мёртвым источником юнит жил
    902 с, ``cast status`` все эти минуты отвечал «играю», и человек смотрел в чёрный
    экран, которому инструмент выдавал справку о здоровье. Поэтому отдельный вопрос - не
    «жив ли юнит», а «есть ли кадр»: ответ на него показ кладёт в ту же запись.
    """

    def __init__(self, session: PlaybackSession, console: Console, clock: Clock) -> None:
        self._session = session
        self._console = console
        self._clock = clock

    def run(self) -> int:
        playing = self._session.active()
        shown = self._session.snapshot(self._session.key() if playing else "")
        if not playing or shown is None:
            return self._silence(shown)
        what = shown.shown_as
        # Разрешение - подтверждённое ffprobe у играющего файла, а не заявка имени.
        what += f" · {shown.quality}" if shown.quality else ""
        self._what_is_on(shown, what)
        if shown.warm > 0:
            # Прогрев - это и есть ответ на вопрос «переживёт ли показ обрыв связи»,
            # поэтому он стоит в статусе, а не в отладочной ручке.
            whole = shown.duration > 0 and shown.warm >= shown.duration * WARMED_RATIO
            self._console.write(
                f"   прогрето {self._hms(shown.warm)} из {self._hms(shown.duration)}"
                + (" - весь фильм на диске, интернет не нужен" if whole else "")
            )
        reserve = self._session.cache_reserve(shown)
        if reserve:
            self._console.write(f"   {reserve}")
        self._console.write(
            f"   {shown.key} · файл #{shown.file_index} · дорожка {shown.audio_index + 1} · "
            f"раздача {self._session.stream_address()}, приёмник {self._session.receiver_name()}"
        )
        return EXIT_OK

    def _silence(self, shown: PlaybackSnapshot | None) -> int:
        """Юнита нет: оборванный показ, недосмотренное кино или честная тишина."""
        if shown is not None and shown.dark_since:  # темнота переживает юнит нарочно
            gone = shown.position
            was = f"на {self._hms(gone)}" if gone else "картинки не было ни кадра"
            self._console.write(f"показ оборвался: {shown.shown_as} - {was} ({shown.dark_reason})")
            return EXIT_OK
        self._console.write("ничего не играет")
        if shown is not None and shown.resumable:
            self._console.write(
                f"последнее: «{shown.title}» на {self._hms(shown.position)} / "
                f"{self._hms(shown.duration)}"
            )
        return EXIT_OK

    def _what_is_on(self, shown: PlaybackSnapshot, what: str) -> None:
        """Одна строка про экран: показ идёт или он погас и мы ждём возврата."""
        if not shown.dark_since:
            self._console.write(
                f"играю {what} - {self._hms(shown.position)} / {self._hms(shown.duration)}"
            )
            return
        self._console.write(
            f"показ погас: {what} - {self._hms(shown.position)} / {self._hms(shown.duration)}"
        )
        self._console.write(
            f"   {self._darkness(shown)} ({shown.dark_reason}) - жду возврата, подниму сам"
        )

    def _darkness(self, shown: PlaybackSnapshot) -> str:
        """Сколько на экране темно, для человека.

        Отметку ставил показ, а читает её ``cast status`` - это два процесса и, вообще
        говоря, два взгляда на часы. Поэтому отрицательная разница тут не сбой измерения,
        а сдвинутые часы: про число тогда молчим, про саму темноту - нет.
        """
        dark = self._clock.wall() - shown.dark_since
        return f"темнота {self._hms(dark)}" if dark > 0 else "темнота"

    @staticmethod
    def _hms(seconds: float) -> str:
        total = int(seconds)
        return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"
