"""Останавливает текущий показ и сообщает сохранённую позицию."""

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.ports.console import Console
from torrcast.ports.playback_session import PlaybackSession


class Stop:
    """Сценарий команды ``cast stop``.

    Позицию пишет сам юнит: остановка шлёт ему SIGTERM и ждёт, сторож на выходе
    дописывает состояние. Раздачу за собой юнит убирает тоже сам, и к этой строке он уже
    мёртв. Но умереть он мог и не по-людски - SIGKILL по таймауту, паника, перезагрузка,
    - а раздача переживает свой процесс: она живёт в TorrServer до его перезапуска.
    Поэтому тот же хэш сносится ещё раз, уже отсюда: он берётся из магнита остановленной
    записи, снос идемпотентен, и ничего, кроме этого хэша, не трогается. Когда ничего не
    играло, не трогается и он: раздачу с тем же магнитом в этот момент может греть чужой
    ход.
    """

    def __init__(self, session: PlaybackSession, console: Console) -> None:
        self._session = session
        self._console = console

    def run(self) -> int:
        played = self._session.active()
        key = self._session.key()  # спрашиваем, пока юнит жив: у мёртвого не узнать
        self._session.stop()
        shown = self._session.snapshot(key)
        if not played or shown is None:
            self._console.write(phrase("stop.nothing_playing"))
            return EXIT_OK
        self._session.release(shown.torrent_hash)
        self._console.write(
            phrase(
                "stop.stopped",
                title=shown.title,
                pos=self._hms(shown.position),
                duration=self._hms(shown.duration),
            )
        )
        return EXIT_OK

    @staticmethod
    def _hms(seconds: float) -> str:
        total = int(seconds)
        return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"
