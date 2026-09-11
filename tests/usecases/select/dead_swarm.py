"""Служба раздач в объёме одного вопроса «жива ли записанная раздача» - для её зеркал."""

from __future__ import annotations

from tests.fakes.clock import FakeClock
from torrcast.domain.pick_settings import RECORDED_CONTACT
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torr_file import TorrFile

MOVIE = [TorrFile(0, "Кино/Кино.1080p.mkv", 8 * 1024**3), TorrFile(1, "Кино/cover.jpg", 1024)]
SILENT = f"рой пуст - за {RECORDED_CONTACT:.0f} с ни одного пира"


class Swarm:
    """Служба раздач в объёме одного вопроса: жива ли записанная раздача.

    ``needs`` - сколько секунд рою нужно на метаданные: меньше этого срока раздача не
    отвечает вовсе, столько и больше - отдаёт свои файлы. Так подделка отличает медленную
    живую раздачу от мёртвой ровно тем, чем их отличает бой, - бюджетом ожидания.

    ``talks_at`` - с какой секунды часов с роем поговорили; ``None`` - ни с кем и никогда,
    а служба при этом честно видит адреса из DHT (замеренный облик мёртвого роя,
    :func:`torrcast.domain.swarm_alive.swarm_alive`). ``quiet`` - служба про рой молчит вовсе.
    """

    def __init__(
        self,
        files: list[TorrFile] | None = None,
        needs: float = 0.0,
        talks_at: float | None = 0.0,
        clock: FakeClock | None = None,
        quiet: bool = False,
    ) -> None:
        self.files = MOVIE if files is None else files
        self.needs = needs
        self.talks_at = talks_at
        self.clock = clock if clock is not None else FakeClock()
        self.quiet = quiet
        self.added: list[str] = []
        self.asked: list[float] = []

    def __call__(self, url: str, timeout: float = 30.0) -> Swarm:
        return self

    def add(self, magnet: str) -> str:
        self.added.append(magnet)
        return "hash-кино"

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
    ) -> list[TorrFile]:
        self.asked.append(timeout)
        if timeout < self.needs:
            raise SwarmError(f"раздача не отдала метаданные за {timeout:.0f} с - нет пиров")
        return list(self.files)

    def status(self, torrent_hash: str) -> dict[str, int]:
        if self.quiet:
            return {}
        if self.talks_at is not None and self.clock.now >= self.talks_at:
            return {"total_peers": 96, "active_peers": 1, "half_open_peers": 25}
        return {"total_peers": 8, "half_open_peers": 8}
