"""Общий инвентарь зеркал меню: раздача, план картины и внешний мир меню.

Отдельным файлом, а не фикстурой: единицы пакета спрашивают одну и ту же картину меню
и один и тот же слот внешнего мира, и собирать их заново в каждом зеркале значило бы
разводить редакции одного и того же меню.

Правила отбора тут настоящие: годность раздачи, старьё и вес считает то же окружение,
что и на живом запуске. Подделывается ровно ввод-вывод пульта - вопрос, терминал,
печать, справка и след, - потому что иначе проверялась бы сама подделка.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TypeVar

from torrcast.adapters.choice_environment import environment
from torrcast.domain.config import Config
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.origin import Origin
from torrcast.domain.kind import Kind
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.profile import Profile
from torrcast.domain.rank_settings import ALIVE_SEEDERS
from torrcast.domain.release import Release
from torrcast.ports.choice_environment import ChoiceArgs, ChoiceEnvironment, ChoiceFacts
from torrcast.usecases.choice.configure import _environment_port, configure
from torrcast.usecases.select._plan import _Plan

#: Десятичный гигабайт: в них считают размер раздачи и трекеры, и наша прикидка веса.
GB = 1000**3

#: Два часа картины - в них пересчитывается размер раздачи, когда её взвешивают.
RUNTIME = 7200.0

#: Потолок отбраковки, Мбит/с: раздачи заготовок заведомо под ним и годны по правилам.
WARN_MBIT = 20.0

_PlanT = TypeVar("_PlanT")


def film(
    name: str = "Кино 2020 WEB-DL 1080p",
    *,
    seeders: int = 100,
    size_gb: float = 4.2,
    quality: str | None = "1080p",
    codec: str | None = "H.264",
    kind: Kind = "movie",
) -> Release:
    """Раздача, заведомо годная по правилам отбора: вопрос зеркал - не про её разбор."""
    return Release(
        raw_name=name,
        title="Кино",
        year=2020,
        quality=quality,
        codec=codec,
        voices=("Дубляж",),
        size=int(size_gb * GB),
        seeders=seeders,
        kind=kind,
        magnet=f"magnet-{name}",
    )


def plan(
    title: str = "Кино",
    year: int | None = 2020,
    *,
    seeders: int = 100,
    kind: Kind = "movie",
    part: int | None = None,
    original: str | None = None,
    pool: list[Release] | None = None,
    asked_series: bool = False,
    loose: bool = False,
    last_resort: bool = False,
) -> _Plan:
    """План одной картины меню: пул раздач в порядке ранжира и та же длительность."""
    ranked = pool if pool is not None else [film(f"{title} {year} WEB-DL 1080p", seeders=seeders)]
    return _Plan(
        picture=Picture(
            title=title, year=year, kind=kind, part=part, original=original, releases=ranked
        ),
        ranked=ranked,
        runtime=RUNTIME,
        warn_mbit=WARN_MBIT,
        loose=loose,
        last_resort=last_resort,
        asked_series=asked_series,
    )


def parts(*named: tuple[str, int | None, int]) -> list[_Plan]:
    """Франшиза тройками «название, год, сиды лучшей годной раздачи картины»."""
    return [plan(title, year, seeders=seeders) for title, year, seeders in named]


@dataclass
class Outside:
    """Внешний мир меню, у которого подделан ровно ввод-вывод; правила настоящие.

    Всё, о чём тест не сказал ни слова, считает боевое окружение: годность раздачи,
    старьё, вес в Мбит/с, обрезка строки. Подделаны вопрос, терминал, печать, файл
    пульта, справка и след - то есть ровно то, чего в сухом прогоне нет физически.
    """

    #: Номера, которые называет человек, по одному на вопрос. Кончились - это Enter.
    answers: list[int] = field(default_factory=list)
    tty: bool = True
    #: Строка из файла диагностического пульта; ``None`` - файла нет вовсе.
    command: str | None = None
    #: Порог живости: своё число нужно тем зеркалам, которые мерят сам порог, а не его
    #: боевое значение.
    alive_seeders: int = ALIVE_SEEDERS
    #: Справка, которой меню подписывает картину, когда своей справки ему не передали.
    blurb: Fact = field(default_factory=Fact)
    width: int = 80
    #: Что отвечает справка про паспорт картины; ``None`` - справка отвечает отказом.
    passport: Origin | None = field(default_factory=Origin)

    said: list[str] = field(default_factory=list)
    asked: list[tuple[str, int, int | None]] = field(default_factory=list)
    events: list[tuple[str, str, dict[str, object]]] = field(default_factory=list)
    passports: list[tuple[str, bool]] = field(default_factory=list)
    reads: int = 0

    @property
    def ctl_env(self) -> str:
        return environment.ctl_env

    @property
    def not_found_error(self) -> type[Exception]:
        return NotFoundError

    def read_command(self) -> str | None:
        """Команда пульта одноразовая: файл съеден, и второй раз её уже нет."""
        self.reads += 1
        line, self.command = self.command, None
        return line

    def write(self, line: str) -> None:
        self.said.append(line)

    def stdin_is_tty(self) -> bool:
        return self.tty

    def ask(self, question: str, count: int, default: int | None = 1) -> int:
        """Ответ номером; без заготовленного номера это пустой Enter, то есть дефолт."""
        self.asked.append((question, count, default))
        if self.answers:
            return self.answers.pop(0)
        if default is None:
            raise AssertionError(f"вопрос «{question}» без дефолта, а ответа тест не дал")
        return default

    def columns(self) -> int:
        return self.width

    def fact(self) -> Fact:
        return self.blurb

    def empty_origin(self) -> Origin:
        return Origin()

    def origin(self, title: str, series: bool) -> Origin:
        self.passports.append((title, series))
        if self.passport is None:
            raise NotFoundError(f"справка про «{title}» не отвечает")
        return self.passport

    def shorten(self, text: str) -> str:
        return environment.shorten(text)

    def emit(self, event: str, action: str, **facts: object) -> None:
        self.events.append((event, action, facts))

    def cut(self, text: str, limit: int) -> str:
        return environment.cut(text, limit)

    def bitrate_of(self, release: Release, duration: float) -> float | None:
        return environment.bitrate_of(release, duration)

    def hevc_hope(self, release: Release, last: bool) -> bool:
        return environment.hevc_hope(release, last)

    def is_candidate(
        self,
        release: Release,
        runtime: float,
        warn_mbit: float,
        loose: bool = False,
        hard_mbit: float = 0.0,
        last: bool = False,
        copy_hevc: bool = False,
    ) -> bool:
        return environment.is_candidate(
            release, runtime, warn_mbit, loose, hard_mbit, last, copy_hevc
        )

    def is_dated(self, release: Release, runtime: float) -> bool:
        return environment.is_dated(release, runtime)

    def timed(
        self,
        plan: _PlanT,
        facts: ChoiceFacts | None,
        args: ChoiceArgs,
        config: Config,
        profile: Profile,
    ) -> _PlanT:
        """Пересборка плана на настоящей длительности; зеркалам хватает того же плана."""
        return plan


@contextmanager
def outside(world: ChoiceEnvironment) -> Iterator[None]:
    """Подставить внешний мир меню на время проверки и вернуть боевой обратно."""
    before = _environment_port()
    configure(world)
    try:
        yield
    finally:
        configure(before)
