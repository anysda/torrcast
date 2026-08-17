"""Выкладка наружу: что дописано, что придержано, что тяжелее потолка и что пропущено."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import torrcast.usecases.feed_pack.packer_publish as publish
from tests.usecases.feed_pack.world import lay, packer
from torrcast.usecases.feed_pack.packer_publish import _lay_out

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _never() -> bool:
    return False


def _always() -> bool:
    return True


def test_only_a_piece_with_a_successor_goes_out_while_the_run_is_alive(tmp_path: Path) -> None:
    """Дописан тот, за которым открылся следующий: последний кусок наружу не идёт.

    Сегментный муксер наполняет файл на месте, поэтому «файл есть» не значит «готов».
    """
    run = packer(tmp_path)
    for slot in (0, 1, 2):
        lay(run.run, slot)

    _lay_out(run, _never)

    assert sorted(p.name for p in run.out.glob("v*.ts")) == ["v0.ts", "v1.ts"]
    assert (run.run / "v2.ts").exists() and run.edge == 1


def test_a_run_that_read_the_input_to_the_end_gives_up_its_last_piece(tmp_path: Path) -> None:
    """Прогон дочитал вход - дописан и последний кусок, соседа ему ждать неоткуда."""
    run = packer(tmp_path)
    for slot in (0, 1, 2):
        lay(run.run, slot)

    _lay_out(run, _always)

    assert sorted(p.name for p in run.out.glob("v*.ts")) == ["v0.ts", "v1.ts", "v2.ts"]
    assert run.edge == 2


def test_the_rollback_and_the_stub_beyond_the_pass_are_deleted_not_published(
    tmp_path: Path,
) -> None:
    """Докатка и обрезок за пределом захода короче своих мест - наружу их нельзя никогда."""
    run = packer(tmp_path, first=1, last=2)
    for slot in (0, 1, 2, 3):
        lay(run.run, slot)

    _lay_out(run, _always)

    assert sorted(p.name for p in run.out.glob("v*.ts")) == ["v1.ts", "v2.ts"]
    assert not (run.run / "v0.ts").exists() and not (run.run / "v3.ts").exists()


def test_a_held_piece_stops_the_publish_and_leaves_no_hole(tmp_path: Path) -> None:
    """Придержанный под перекод кусок останавливает выкладку: дыра увела бы край за неё."""
    held: list[int] = []

    def hold(slot: int, size: int) -> bool:
        held.append(slot)
        return slot == 1

    run = packer(tmp_path, hold=hold)
    for slot in (0, 1, 2, 3):
        lay(run.run, slot)

    _lay_out(run, _always)

    assert sorted(p.name for p in run.out.glob("v*.ts")) == ["v0.ts"]
    assert held == [0, 1] and run.edge == 0


def test_the_recoded_picture_goes_out_with_the_sound_of_the_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Наружу идёт склейка: картинка перекода со звуком копии этого же прогона."""
    told: list[tuple[int, str]] = []
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare, told=lambda slot, how: told.append((slot, how)))
    lay(run.run, 0)
    lay(spare, 0, size=2048)

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        dst.write_bytes(b"mixed")
        return True

    monkeypatch.setattr(publish, "timeline_shift", lambda *a, **k: 0.25)
    monkeypatch.setattr(publish, "merge_tracks", merge)

    _lay_out(run, _always)

    assert (run.out / "v0.ts").read_bytes() == b"mixed"
    assert told == [(0, "склейка")]
    assert not (spare / "v0.ts").exists(), "лишняя копия места осталась лежать"


def test_a_failed_merge_on_a_shifted_run_sends_the_copy_while_it_fits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Склейки нет, а лента сдвинута: копия своего прогона - меньшее зло, пока влезает."""
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare, cap=4096)
    lay(run.run, 0, size=100)
    lay(spare, 0, size=200)
    monkeypatch.setattr(publish, "timeline_shift", lambda *a, **k: 0.25)
    monkeypatch.setattr(publish, "merge_tracks", lambda *a, **k: False)

    _lay_out(run, _always)

    assert (run.out / "v0.ts").stat().st_size == 100, "наружу ушла не копия своего прогона"


def test_a_piece_over_the_ceiling_is_shrunk_and_a_hopeless_one_is_honestly_skipped(
    tmp_path: Path,
) -> None:
    """Тяжёлый кусок ужимается на месте; не вышло - место пропускается, а край идёт дальше.

    Прежний ``break`` тут не двигал край и не удалял копию: несданное копилось до
    потолка, прогон гасили, запрос поднимал его снова - и круг повторялся вечно.
    """
    asked: list[int] = []

    def shrink(slot: int, size: int) -> bool:
        asked.append(slot)
        return False

    run = packer(tmp_path, cap=10, shrink=shrink)
    lay(run.run, 0, size=100)
    lay(run.run, 1, size=5)

    _lay_out(run, _always)

    assert asked == [0], "ужать тяжёлый кусок никто не попробовал"
    assert not (run.out / "v0.ts").exists() and not (run.run / "v0.ts").exists()
    assert (run.out / "v1.ts").exists() and run.edge == 1


def test_without_anyone_to_shrink_the_heavy_piece_the_publish_stops_on_it(
    tmp_path: Path,
) -> None:
    """Ужимать некому - выкладка встаёт на тяжёлом куске: это поведение до TC-467."""
    run = packer(tmp_path, cap=10)
    lay(run.run, 0, size=100)
    lay(run.run, 1, size=5)

    _lay_out(run, _always)

    assert list(run.out.glob("v*.ts")) == [] and run.edge == -1
