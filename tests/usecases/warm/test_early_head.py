"""Старт следующей серии ложится на диск заранее, под приоритетом и с уступкой показу."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from tests.usecases.warm.world import FakeEnvironment, lay, vault, warmer, world
from torrcast.usecases.warm.early_head import _early_head
from torrcast.usecases.warm.settings import (
    HEAD_NICE,
    HEAD_RATE,
    HEAD_TRIES,
    START_GRACE,
    WARM_NICE,
    WARM_RATE,
)
from torrcast.usecases.warm.wait_for_picture import _wait_for_picture
from torrcast.usecases.warm.warmer import Warmer

if TYPE_CHECKING:
    from pathlib import Path


class _Laying(Warmer):
    """Прогрев, у которого заход кладёт кусок и записывает, с каким ``nice`` шёл."""

    def _run(self, first: int, last: int, spot: bool = False) -> None:
        _TAKEN.append((first, spot, self.nice))
        _RATES.append(self.rate)
        if spot:
            self.vault.spot(first).touch()
        else:
            lay(self.vault, first)


class _Stubborn(_Laying):
    """Перекод старта не ложится никогда."""

    def _run(self, first: int, last: int, spot: bool = False) -> None:
        _TAKEN.append((first, spot, self.nice))
        lay(self.vault, first)


_TAKEN: list[tuple[int, bool, int]] = []
_RATES: list[float] = []


def _next(root: Path, kind: Any = _Laying) -> Warmer:
    """Прогрев следующей серии с тяжёлым стартом."""
    _TAKEN.clear()
    _RATES.clear()
    return warmer(
        root,
        kind=kind,
        vault=vault(root, key="следующая"),
        spots=(0,),
        spot_encode=cast("Any", object()),
    )


def _current(root: Path, **kwargs: Any) -> Warmer:
    """Прогрев текущей серии, у которой показ уже дал кадр: запас мерили, указатель пошёл."""
    warm = warmer(root, slack=60.0, **kwargs)
    warm.shown(10.0, True)
    warm.shown(12.0, True)
    assert warm.framed
    return warm


def test_the_next_start_is_laid_and_recoded_while_this_episode_only_began(
    tmp_path: Path,
) -> None:
    """Копия, затем перекод поверх неё - и больше ничего из следующей серии."""
    world()
    warm = _current(tmp_path)
    following = _next(tmp_path)
    warm.follow = lambda: following

    _early_head(warm)

    assert _TAKEN == [(0, False, WARM_NICE), (0, True, HEAD_NICE)], "старт не лёг заранее"
    assert following.vault.spot(0).exists()
    assert warm.after is following and following.ahead
    assert following.thread is None, "остальная следующая серия отобрала бы раздачу у текущей"
    assert following.nice == WARM_NICE, "приоритет остался и у остального прогрева"
    assert following.landing is not None and following.landing.is_set()


def test_the_next_start_is_read_without_the_warming_ceiling(tmp_path: Path) -> None:
    """Старт - один кусок у самого стыка: потолок темпа прогрева ему только срок съедает."""
    world()
    warm = _current(tmp_path)
    following = _next(tmp_path)
    warm.follow = lambda: following

    _early_head(warm)

    assert _RATES == [HEAD_RATE, HEAD_RATE], "копия и перекод старта ждали потолка прогрева"
    assert following.rate == WARM_RATE, "остальной прогрев читает прежним темпом"


class _Rival:
    """Живой перекод, который занят первые ``busy`` вопросов."""

    def __init__(self, busy: int) -> None:
        self.busy = busy

    @property
    def working(self) -> bool:
        self.busy -= 1
        return self.busy >= 0


def test_a_live_recode_holds_the_early_start_back(tmp_path: Path) -> None:
    """Живое окно показа сильнее прогрева: заход старта ждёт конца живого захода."""
    fake = world()
    warm = _current(tmp_path, rival=_Rival(busy=4))
    following = _next(tmp_path)
    warm.follow = lambda: following

    _early_head(warm)

    assert len(fake.slept) >= 4, "старт следующей серии не уступил живому перекоду"
    assert _TAKEN[-1] == (0, True, HEAD_NICE)


def test_a_start_that_never_lands_is_left_to_its_own_warming(tmp_path: Path) -> None:
    """Прогонов не больше :data:`HEAD_TRIES`: прогрев текущей серии не стоит из-за следующей."""
    world()
    warm = _current(tmp_path)
    following = _next(tmp_path, kind=_Stubborn)
    warm.follow = lambda: following

    _early_head(warm)

    assert len(_TAKEN) == HEAD_TRIES


def test_a_broken_factory_is_asked_once_and_left_to_the_chain(tmp_path: Path) -> None:
    """Повторы при обрыве сети - дело цепочки, а не прогрева текущей серии."""
    world()
    warm = _current(tmp_path)
    asked = 0

    def _follow() -> Warmer:
        nonlocal asked
        asked += 1
        raise OSError("раздача молчит")

    warm.follow = _follow

    _early_head(warm)

    assert asked == 1 and warm.after is None


def test_the_next_episode_does_not_reach_further_ahead(tmp_path: Path) -> None:
    """У прогрева следующей серии своей следующей заранее нет: одна серия вперёд."""
    world()
    warm = _current(tmp_path, ahead=True)
    warm.follow = lambda: _next(tmp_path)

    _early_head(warm)

    assert warm.after is None


def test_nothing_to_follow_is_remembered_for_the_chain(tmp_path: Path) -> None:
    """Фильм или последняя серия: ответ не изменится, и цепочка второй раз не спрашивает."""
    world()
    warm = _current(tmp_path)
    warm.follow = lambda: None

    _early_head(warm)

    assert warm.follow is None


def test_no_step_while_the_show_never_measured_its_slack(tmp_path: Path) -> None:
    """Прогрев тронулся по :data:`START_GRACE` при нулевом запасе: кадра не было, шага нет.

    Копия и перекод следующей серии шли под ``nice 10``, пока у текущей не было ни
    кадра: :meth:`_must_yield` при нулевом запасе ложен. Такой показ - дело :func:`_chain`.
    """
    fake = world()
    warm = warmer(tmp_path)
    asked: list[bool] = []
    warm.follow = lambda: asked.append(True)
    _wait_for_picture(warm)
    assert fake.now >= 1000.0 + START_GRACE, "ожидание вышло не по START_GRACE"
    naps = len(fake.slept)

    _early_head(warm)

    assert asked == [] and warm.after is None, "шаг к следующей серии без кадра текущей"
    assert len(fake.slept) == naps, "и прогрев текущей серии не ждёт второй START_GRACE"


@dataclass
class _Polled(FakeEnvironment):
    """Часы, на каждом сне которых показ опрашивает приёмник: позиция и играет ли он."""

    show: Warmer | None = None
    polls: list[tuple[float, bool]] = field(default_factory=list)

    def sleep(self, seconds: float) -> None:
        FakeEnvironment.sleep(self, seconds)
        if self.show is not None and self.polls:
            self.show.shown(*self.polls.pop(0))


def test_after_a_seek_to_the_end_the_step_waits_for_a_frame_there(tmp_path: Path) -> None:
    """Перемотка к концу: упаковка у конца файла даёт запас 90, но кадра там ещё нет.

    Живой прогон: шаг стартовал за секунду до «играю». Шаг ждёт кадра на новом месте -
    сдвига указателя играющего приёмника, а не слова ``PLAYING``.
    """
    fake = cast("_Polled", world(kind=_Polled))
    warm = _current(tmp_path)
    warm.shown(1400.0, False)  # перемотка к концу: указатель прыгнул
    warm.packed()
    # Первый ``PLAYING`` приходит с докаткой указателя до места захода, картинки ещё нет.
    landing = [(1400.0, False), (1400.3, True), (1400.3, True), (1401.8, True)]
    fake.show, fake.polls = warm, landing
    following = _next(tmp_path)
    asked: list[float] = []

    def _follow() -> Warmer:
        asked.append(warm.shown_at)
        return following

    warm.follow = _follow

    _early_head(warm)

    assert asked == [1401.8], "шаг к следующей серии раньше кадра на новом месте"
    assert _TAKEN[-1] == (0, True, HEAD_NICE)
