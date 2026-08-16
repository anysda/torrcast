"""Показывает состояние текущего или последнего сеанса."""

from torrcast.ports.clock import Clock
from torrcast.ports.console import Console
from torrcast.ports.playback_session import PlaybackSession


class Status:
    """Сценарий команды ``cast status``."""

    def __init__(self, session: PlaybackSession, console: Console, clock: Clock) -> None:
        self._session = session
        self._console = console
        self._clock = clock

    def run(self) -> int:
        playing = self._session.active()
        shown = self._session.snapshot(self._session.key() if playing else "")
        if not playing or shown is None:
            if shown is not None and shown.dark_since:
                was = self._at(shown.position) if shown.position else "картинки не было ни кадра"
                self._console.write(
                    f"показ оборвался: {shown.shown_as} - {was} ({shown.dark_reason})"
                )
            else:
                self._console.write("ничего не играет")
                if shown is not None and shown.resumable:
                    self._console.write(
                        f"последнее: «{shown.title}» на {self._hms(shown.position)} / "
                        f"{self._hms(shown.duration)}"
                    )
            return 0
        what = shown.shown_as + (f" · {shown.quality}" if shown.quality else "")
        if shown.dark_since:
            self._console.write(
                f"показ погас: {what} - {self._hms(shown.position)} / {self._hms(shown.duration)}"
            )
            dark = self._clock.monotonic() - shown.dark_since
            darkness = f"темнота {self._hms(dark)}" if dark > 0 else "темнота"
            self._console.write(f"   {darkness} ({shown.dark_reason}) - жду возврата, подниму сам")
        else:
            self._console.write(
                f"играю {what} - {self._hms(shown.position)} / {self._hms(shown.duration)}"
            )
        if shown.warm > 0:
            whole = shown.duration > 0 and shown.warm >= shown.duration * 0.99
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
        return 0

    @classmethod
    def _at(cls, seconds: float) -> str:
        return f"на {cls._hms(seconds)}"

    @staticmethod
    def _hms(seconds: float) -> str:
        total = int(seconds)
        return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"
