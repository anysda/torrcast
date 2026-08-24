"""Подготовка одного релиза целиком в фоне: раздача, файл, дорожки."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import Media
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.contact_wait import ContactWait


@dataclass(slots=True)
class _Prep:
    """Подготовка одного релиза целиком в фоне: раздача, файл, дорожки.

    Это и есть прогрев под меню. Фазы идут своим ходом в отдельном потоке, а показ
    спрашивает только результат — поэтому 17 секунд ffprobe на «Моане 2» уходят из
    критического пути в паузу между вопросами.

    Каждая фаза имеет **бюджет**: не уложилась — это не «зависло насмерть» без единого
    слова, а :attr:`error` и следующий релиз в очереди.
    """

    number: int
    release: Release
    torrent_hash: str = ""
    #: Прогрев оказался ненужным: показ ушёл на другую картину или другой релиз. Такая
    #: раздача убирается из TorrServer сразу - иначе два лишних торрента тянули бы кэш
    #: и полосу у самого показа.
    dropped: bool = False
    video: TorrFile | None = None
    files: list[TorrFile] = field(default_factory=list)
    media: Media | None = None
    error: str = ""
    #: Отказ, которым кончилась подготовка (``error`` - его строка для человека).
    #: Нужен именно типом: «умерло собственное звено» опознаётся по классу
    #: исключения, а не по префиксу текста - текст пишется языком зрителя и правится.
    failure: TorrcastError | None = None
    #: Спрашивать рой по ПОЛНЫМ бюджетам фазы, без отсрочек на первый контакт
    #: (:data:`PEER_GRACE`, :data:`SWARM_GRACE`). Отсрочки существуют, чтобы не занимать
    #: место в очереди безнадёжной раздачей, и стоит их ошибка ровно этого места - пока
    #: в очереди есть кого спросить. Когда спрашивать больше некого, платить отсрочкам
    #: нечем: терпеливо спрашивается один-единственный релиз (:meth:`Bench._recheck`).
    patient: bool = False
    #: Отсрочка первого контакта с роем (:class:`torrcast.ports.contact_wait.ContactWait`);
    #: заводит её стенд, а часы пускает вопрос к этому релизу.
    contact_wait: ContactWait | None = None
    phase: str = "очередь"
    started: float = field(default_factory=time.monotonic)
    meta: float = 0.0
    read: float = 0.0
    #: Фактическая доставка во время прогрева: ``(секунд от старта, прочитано байт)``.
    #: Счётчик снимается, пока файл действительно читают, а не после остановки спроса.
    supply: list[tuple[float, float]] = field(default_factory=list)
    ready: threading.Event = field(default_factory=threading.Event)

    @property
    def want(self) -> TorrFile:
        if self.video is None:
            raise InfraError("файл раздачи не выбран")
        return self.video

    @property
    def found(self) -> Media:
        if self.media is None:
            raise InfraError("поток не прочитан")
        return self.media

    @property
    def timing(self) -> str:
        return f"метаданные {self.meta:.1f} с, дорожки {self.read:.1f} с"
