"""Останавливает текущий показ и сообщает сохранённую позицию."""

from torrcast.ports.console import Console
from torrcast.ports.playback_session import PlaybackSession


class Stop:
    """Сценарий команды ``cast stop``."""

    def __init__(self, session: PlaybackSession, console: Console) -> None:
        self._session = session
        self._console = console

    def run(self) -> int:
        played = self._session.active()
        key = self._session.key()
        self._session.stop()
        shown = self._session.snapshot(key)
        if not played or shown is None:
            self._console.write("ничего не играет")
            return 0
        if shown.torrent_hash:
            self._session.release(shown.torrent_hash)
        self._console.write(
            f"остановлено: «{shown.title}» на {self._hms(shown.position)} / "
            f"{self._hms(shown.duration)}"
        )
        return 0

    @staticmethod
    def _hms(seconds: float) -> str:
        total = int(seconds)
        return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"
