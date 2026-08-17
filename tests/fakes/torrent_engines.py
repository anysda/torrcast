"""Заводит тестам подставную службу раздач и помнит, с какими сроками её просили."""

from dataclasses import dataclass, field

from tests.fakes.torrent_engine import FakeTorrentEngine


@dataclass
class FakeTorrentEngines:
    #: Одна и та же служба на все заводы: тест смотрит её обращения после сценария.
    engine: FakeTorrentEngine = field(default_factory=FakeTorrentEngine)
    #: С какими адресом и сроком её заводили: короткий срок сторожа - не то же самое,
    #: что обычный срок показа, и разница видна только здесь.
    asked: list[tuple[str, float]] = field(default_factory=list)

    def __call__(self, base_url: str, timeout: float = 30.0) -> FakeTorrentEngine:
        self.asked.append((base_url, timeout))
        return self.engine
