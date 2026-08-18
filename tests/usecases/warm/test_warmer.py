"""Прогрев целиком: нитка работы, порядок участков и справки, которыми он о себе говорит."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from tests.usecases.warm.world import (
    FakeEnvironment,
    counting,
    falling,
    lay,
    vault,
    warmer,
    world,
)
from torrcast.usecases.warm.settings import GUARD_HIGH
from torrcast.usecases.warm.warmer_state import _State

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _Rival:
    working: bool = False


def test_the_warming_is_the_state_it_stands_on(tmp_path: Path) -> None:
    """Поля и справки прогрев берёт из своей базы, а не заводит вторые."""
    warm = warmer(tmp_path)

    assert isinstance(warm, _State)
    assert warm.line().startswith("прогрето"), "строка о себе потерялась"


def test_the_thread_starts_the_work_and_the_stop_ends_it(tmp_path: Path) -> None:
    """Нитка поднимается через :meth:`start` и снимается через :meth:`stop`."""
    world()
    kind, taken = counting()
    warm = warmer(tmp_path, kind=kind, slack=GUARD_HIGH + 1.0)

    warm.start()
    assert warm.thread is not None
    warm.thread.join(timeout=5.0)

    assert taken == [(0, warm.grid.count - 1, False)], "нитка не взялась за первый участок"
    warm.stop()
    assert warm.stopped


def test_the_work_yields_before_it_even_raises_a_run(tmp_path: Path) -> None:
    """Уступка начинается раньше первого захода: пробный прогон - это тоже ffmpeg."""

    class _Impatient(FakeEnvironment):
        warm: Any = None

        def sleep(self, seconds: float) -> None:
            super().sleep(seconds)
            self.warm.stopped = True

    kind, taken = counting()
    fake = cast(_Impatient, world(_Impatient))
    warm = warmer(tmp_path, kind=kind, slack=GUARD_HIGH + 1.0)
    warm.rival = _Rival(working=True)
    fake.warm = warm

    warm._work()

    assert taken == [], "прогрев поднял прогон посреди чужого захода"
    assert fake.slept == [0.5]


def test_a_whole_film_says_it_is_ready_and_moves_to_the_next_episode(tmp_path: Path) -> None:
    """Работа кончилась - строка человеку, метка в журнал, след и следующая серия."""
    fake = world()
    said: list[str] = []
    warm = warmer(tmp_path, slack=GUARD_HIGH + 1.0, log=said.append)
    following = warmer(tmp_path, vault=vault(tmp_path, key="следующая"))
    warm.follow = lambda: following
    for slot in range(warm.grid.count):
        lay(warm.vault, slot)

    warm._work()

    assert any("интернет больше не нужен" in line for line in said)
    assert fake.named("прогрев готов")["секунд"] == round(warm.grid.duration)
    assert (fake.events[0][0], fake.events[0][1]) == ("warmth", ("ready",))
    assert warm.after is following, "цепочка не тронулась после готовой серии"
    following.stop()


def test_heavy_places_without_a_recode_stop_the_work_but_not_the_chain(tmp_path: Path) -> None:
    """Тяжёлые места копией - не «готово», но и работа прогрева на них кончилась."""
    world()
    warm = warmer(tmp_path, slack=GUARD_HIGH + 1.0, cap=10, log=[].append)
    for slot in range(warm.grid.count):
        lay(warm.vault, slot, size=1000)

    warm._work()

    assert "остались копией" in warm.trouble
    assert not warm.done, "фильм назвался готовым при местах, которых без сети не досмотреть"


def test_a_tight_budget_stops_the_work_before_the_run(tmp_path: Path) -> None:
    """Бюджет спрашивается ДО захода: греть в упёртый раздел нечего."""
    world()
    kind, taken = counting()
    warm = warmer(tmp_path, kind=kind, vault=vault(tmp_path, budget=1), slack=GUARD_HIGH + 1.0)
    said: list[str] = []
    warm.log = said.append

    warm._work()

    assert taken == [], "заход пошёл в упёртый бюджет"
    assert "бюджет диска" in warm.trouble


def test_a_crash_inside_the_work_never_kills_the_show(tmp_path: Path) -> None:
    """Прогрев не имеет права ронять показ: своя беда - это строка и пауза."""
    fake = world()
    said: list[str] = []
    warm = warmer(
        tmp_path,
        kind=falling(RuntimeError("сорвалось")),
        slack=GUARD_HIGH + 1.0,
        log=said.append,
    )

    warm._work()

    assert any("прогрев сорвался" in line for line in said)
    assert fake.slept[-1] == 5.0
