"""Поля фонового прогрева и мелкие справки по ним.

Наследует их :class:`torrcast.usecases.warm.warmer.Warmer`, и только он.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.domain.profile import CAUTIOUS
from torrcast.ports.recode.encoding import Encoding
from torrcast.ports.recode.encoding_key import EncodingKey
from torrcast.ports.recode.recode_rival import RecodeRival
from torrcast.usecases.warm._state import Grid, _Run
from torrcast.usecases.warm._warm_count import _all_warmed, _spots_left, _warmed
from torrcast.usecases.warm.settings import CHAIN_RETRY, GUARD_LOW, WARM_NICE, WARM_RATE
from torrcast.usecases.warm.vault import Vault


@dataclass(slots=True)
class _State:
    """Всё, что прогрев про себя знает: место показа, ход прогона и цепочка серий."""

    source: str
    audio: int
    grid: Grid
    vault: Vault
    #: Чем кодировать видео (:class:`torrcast.adapters.recode.encode.Encode`); ``None`` - копия.
    #:
    #: 🔴 Ставится ТЕМ ЖЕ решением, что у живой упаковки
    #: (:func:`torrcast.usecases.playback._warmer._warmer`). Прогретый кусок и живой - это одна лента
    #: для приёмника, и если они закодированы по-разному, на стыке источников у него меняется SPS.
    encode: EncodingKey | None = None
    #: Слоты, которые живой показ отдаёт перекодированными поштучно (тяжёлые куски,
    #: :attr:`torrcast.adapters.recode.recoder.Recoder.targets`). Прогрев обязан положить на диск их
    #: же и такими же: копия тяжёлого куска приёмнику не по зубам, а перекод всего фильма ради пяти
    #: кусков расходится с живой упаковкой во всём остальном.
    spots: tuple[int, ...] = ()
    #: Чем перекодировать :attr:`spots` - тот же :class:`torrcast.adapters.recode.encode.Encode`,
    #: которым их берёт живой кодировщик.
    #:
    #: 🔴 Решение тут приезжает НЕужатым под кусок: живой кодировщик ужимает его сам, уже
    #: зная длину своего захода (:func:`torrcast.adapters.recode.run._run`), и прогрев обязан
    #: повторить тот же счёт на своей длине (:func:`torrcast.usecases.warm.run._run`).
    #: Договор поэтому широкий (:class:`Encoding`, а не :class:`EncodingKey`): ужатие -
    #: часть решения, а не расчёт на стороне прогрева.
    spot_encode: Encoding | None = None
    #: Битрейт, который тянет приёмник (:attr:`torrcast.domain.profile.Profile.recode_at_mbit`).
    #: Второй потолок цели точечного перекода рядом с :attr:`cap`: вес зависит от длины
    #: куска, а этот - нет, и на коротком куске главным оказывается он.
    threshold: float = CAUTIOUS.recode_at_mbit
    #: С какого места смотрим: прогрев идёт отсюда вперёд, голова - потом.
    began_at: int = 0
    #: Потолок веса одного куска у приёмника, байты
    #: (:attr:`torrcast.domain.profile.Profile.max_segment_bytes`). Прогреву он нужен не для
    #: укладки, а для счёта: тяжелее потолка показ прогретое с диска не берёт
    #: (:meth:`torrcast.usecases.feed_pack.feed.Feed._warm`), и запасом такой кусок не является.
    cap: int = CAUTIOUS.max_segment_bytes
    #: Сколько Мбит/с уедет на ТВ в среднем по фильму - паспорт ffprobe, та же цифра, по
    #: которой живой показ строит ровный профиль тяжести
    #: (:meth:`torrcast.adapters.recode.weights.Weights.flat`). Прогреву она нужна там, где
    #: карты опорных кадров нет: без неё вес куска нечем оценить, кроме потолка приёмника,
    #: а потолок - это верхняя граница, а не вес. Ноль - паспорт про видео промолчал.
    delivered: float = 0.0
    rate: float = WARM_RATE
    nice: int = WARM_NICE
    log: Callable[[str], None] | None = None
    #: Запас живого показа, секунды; кладёт :func:`torrcast.usecases.revive_playback._hold._hold` на
    #: каждом опросе.
    slack: float = 0.0
    #: Кодировщик живых кусков (:class:`torrcast.adapters.recode.recoder.Recoder`) или ``None``. Пока
    #: у него идёт заход, прогрев замирает: см. :meth:`_must_yield`.
    rival: RecodeRival | None = None
    #: Прогрев замер под просевшим запасом (:data:`GUARD_LOW`).
    idle: bool = False
    #: С какого момента (монотонные секунды) запас держится над :data:`GUARD_LOW`, пока
    #: прогрев замер; ``0.0`` - ещё не поднялся или прогрев не замирал. По этой выдержке
    #: тесный, но здоровый показ оживляет прогрев, не дожидаясь :data:`GUARD_HIGH`
    #: (:meth:`_may_resume`).
    healthy_since: float = 0.0
    #: Почему прогрев дальше не идёт: бюджет диска, мёртвый источник, место, которое не
    #: легло на сетку, тяжёлые места копией, которые перекодировать нечем. Пусто - идёт.
    trouble: str = ""
    stopped: bool = False
    thread: threading.Thread | None = None
    packer: _Run | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    #: Сколько прогонов оборвалось само (сеть). Считается ради честной строки, не ради лимита.
    breaks: int = 0
    #: Чем продолжить, когда эта серия ляжет на диск целиком: фабрика прогрева следующей
    #: серии (``() -> Warmer | None``) или ``None`` - продолжать нечем.
    #:
    #: Фабрика, а не готовый прогрев: следующей серии нужны и паспорт, и карта опорных
    #: кадров, а это запросы к рою, которые не имеют права идти, пока грузится текущая.
    #: Зовётся ровно один раз и ровно тогда, когда текущая серия уже не нуждается в сети.
    follow: Callable[[], _State | None] | None = None
    #: Прогрев следующей серии, поднятый :meth:`_chain`; ``None`` - ещё не поднимали.
    after: _State | None = None
    #: Через сколько секунд спрашивать следующую серию заново, когда собрать её не вышло
    #: (:data:`CHAIN_RETRY`). Полем, а не константой, ради тестов: они проверяют повтор,
    #: а не ожидание.
    chain_retry: float = CHAIN_RETRY
    #: Сколько раз каждое место уже легло мимо сетки (:meth:`_verify`). Ключ - слот.
    skews: dict[int, int] = field(default_factory=dict)
    #: Слот, который прямо сейчас лёг мимо сетки; ``-1`` - прогон идёт ровно. По нему
    #: :meth:`_run` обрывает заход: промахнулся один кусок - промахнулся весь заход.
    misgrid: int = -1

    def start(self) -> None:
        self.vault.open()
        self.thread = threading.Thread(target=self._work, daemon=True, name="torrcast-warm")
        self.thread.start()

    def stop(self) -> None:
        """Снять прогрев. Прогретое **не трогаем**: показ может продолжиться завтра."""
        self.stopped = True
        with self.lock:
            packer, self.packer = self.packer, None
        if packer is not None:
            packer.stop(keep_files=True, reason="показ окончен")
        if self.after is not None:
            self.after.stop()

    def feed(self, slack: float) -> None:
        """Запас живого показа - прогреву и его продолжению (:meth:`_throttle`).

        Число одно на всю цепочку: и прогрев этой серии, и прогрев следующей тянут из той
        же раздачи и жгут тот же процессор, поэтому проседание показа обязано ронять оба.
        """
        self.slack = slack
        if self.after is not None:
            self.after.feed(slack)

    @property
    def warmed(self) -> float:
        """Сколько секунд фильма показ может взять с диска (:func:`_warmed`)."""
        return _warmed(self.grid, self.vault, self.cap)

    @property
    def done(self) -> bool:
        """Весь фильм на диске: сети дальше не нужно (:func:`_all_warmed`)."""
        return _all_warmed(self.grid, self.vault, self.cap, self.spots, self.spot_encode)

    def _spots_left(self) -> tuple[int, ...]:
        """Тяжёлые куски, ещё не перекодированные точечно (:func:`_spots_left`)."""
        return _spots_left(self.vault, self.spots, self.spot_encode)

    def _busy_rival(self) -> bool:
        """Идёт ли прямо сейчас заход живого перекода (:attr:`rival`)."""
        return bool(self.rival is not None and getattr(self.rival, "working", False))

    def _must_yield(self) -> bool:
        """Обязан ли прогрев замереть. Две причины, и обе про то, что показ важнее.

        Первая, старая: запас живого показа просел ниже :data:`GUARD_LOW`.

        Вторая, замеренная: рядом идёт заход живого перекода. Тяжёлый кусок обязан быть
        готов к своей секунде, и он единственный на всём показе работает по СРОКУ, а не
        впрок. ``nice`` тут не помогает - это замер, а не осторожность: прогрев под
        ``nice 19`` держит 128 % из 400 %, и живой перекод того же куска идёт 1.84×
        вместо 2.62×, то есть теряет 30 %. Ни ``-threads 2`` (2.04×), ни ``cpu.weight=1``
        в cgroup (2.30×) дыру не закрывают - процессор возвращает только ``SIGSTOP``
        (2.62×, вровень с пустой машиной).

        Цена честная и маленькая: заходы живого перекода коротки и редки (на «Тачках 3»
        это 5 кусков из 525), а прогрев работает впрок и ничего не теряет от паузы.
        """
        return self._busy_rival() or (0 < self.slack < GUARD_LOW)

    def _work(self) -> None:
        """Нитка прогрева. Тело живёт в :class:`Warmer`, отсюда его поднимает :meth:`start`."""
        raise NotImplementedError

    def _say(self, text: str) -> None:
        if self.log is not None:
            self.log(text)
