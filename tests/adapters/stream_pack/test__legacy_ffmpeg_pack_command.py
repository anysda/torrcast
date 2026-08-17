"""Проверяет, что прежняя сборка команды упаковщика не разъехалась со своей заменой."""

from __future__ import annotations

import dataclasses

import pytest

from torrcast.adapters.stream_pack._legacy_ffmpeg_pack_command import _legacy_ffmpeg_pack_command
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.grid import Grid

GRID = Grid.uniform(60.0, 8.0)
LIFTED = dataclasses.replace(GRID, origin=0.083)
KEYED = Grid.on_keyframes([0.0, 9.0, 21.0, 30.0, 45.0], 60.0, 10.0)


@pytest.mark.parametrize("grid", [GRID, LIFTED, KEYED])
@pytest.mark.parametrize(("slot", "at"), [(0, 0.0), (2, 16.0), (2, 14.0), (3, 40.0)])
@pytest.mark.parametrize("until", [-1, 2])
def test_the_old_and_the_new_assembly_give_the_very_same_command(
    grid: Grid, slot: int, at: float, until: int
) -> None:
    """Живой путь идёт через новую сборку, а эта осталась рядом со своей заменой.

    Пока она тут лежит, она обязана давать ровно ту же команду: разъехавшись, она стала
    бы вторым, тихо неверным описанием нарезки - и первый же зовущий получил бы куски,
    не совпадающие с манифестом.
    """
    old = _legacy_ffmpeg_pack_command("вход", 0, "/пак", grid, slot, at, 1.0, 5.0, None, until)
    new = ffmpeg_pack_command("вход", 0, "/пак", grid, slot, at, 1.0, 5.0, None, until)
    assert old == new


def test_a_run_told_it_stands_past_its_boundary_is_pulled_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-629. Рез «раньше начала прогона» - несуществующее место, и на списке с минусом
    сегментный муксер не режет ВООБЩЕ. Зажим кричит в журнал, а не подменяет число молча.
    """
    command = _legacy_ffmpeg_pack_command("вход", 0, "/пак", GRID, 2, 24.0)
    cuts = [float(x) for x in command[command.index("-segment_times") + 1].split(",")]
    assert min(cuts) >= 0.0, "список резов ушёл в минус"
