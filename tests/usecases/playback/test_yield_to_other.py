"""Подъём, снятый чужим запуском, кончается отменой; свой подъём идёт дальше."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.usecases.playback.world import FakeProgress
from torrcast.domain.cancelled_error import CancelledError
from torrcast.usecases.playback.launch_owner import OWNER_FILE, LaunchOwner
from torrcast.usecases.playback.yield_to_other import yield_to_other


def test_a_launch_taken_over_ends_in_a_cancel_and_clears_the_line(tmp_path: Path) -> None:
    owner = LaunchOwner.claim(tmp_path)
    (tmp_path / OWNER_FILE).write_text("чужой")
    progress = FakeProgress()

    with pytest.raises(CancelledError):
        yield_to_other(owner, progress)
    assert progress.phases == [""]


@pytest.mark.parametrize("unmarked", [False, True], ids=["own", "no-mark"])
def test_an_own_or_unmarked_launch_goes_on(tmp_path: Path, unmarked: bool) -> None:
    owner = None if unmarked else LaunchOwner.claim(tmp_path)
    progress = FakeProgress()

    yield_to_other(owner, progress)
    assert progress.phases == []
