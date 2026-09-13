"""Копия, которой нужен свой GOP после смены кодировщика."""

from pathlib import Path

from tests.usecases.feed_pack.world import lay, packer
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.unsafe_copy import unsafe_copy


def test_a_keyless_copy_after_a_recode_on_a_flat_grid_is_unsafe(tmp_path: Path) -> None:
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare, shrink=lambda *args: True)
    lay(run.run, 0)
    path = run.run / "v0.ts"

    assert unsafe_copy(run, path, path, 0, lambda piece: True, lambda slot: True)


def test_a_copy_never_needs_a_recode_seam_fix_on_the_key_grid(tmp_path: Path) -> None:
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(
        tmp_path,
        spare=spare,
        shrink=lambda *args: True,
        grid=Grid.on_keyframes((0.0, 10.0), 20.0),
    )
    lay(run.run, 0)
    path = run.run / "v0.ts"

    assert not unsafe_copy(run, path, path, 0, lambda piece: True, lambda slot: True)
    assert not unsafe_copy(run, path, path, 0, lambda piece: True, lambda slot: False)
