"""Выкладка наружу: что дописано, что придержано, что тяжелее потолка и что пропущено."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tests.usecases.feed_pack.world import lay, packer
from torrcast.adapters.stream_pack.packer_publish import _lay_out

if TYPE_CHECKING:
    from pathlib import Path


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


def test_the_recoded_picture_goes_out_with_the_sound_of_the_copy(tmp_path: Path) -> None:
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

    _lay_out(run, _always, merge=merge, shift_of=lambda *a: 0.25)

    assert (run.out / "v0.ts").read_bytes() == b"mixed"
    assert told == [(0, "склейка")]
    assert not (spare / "v0.ts").exists(), "лишняя копия места осталась лежать"


def test_a_failed_merge_on_a_shifted_run_sends_the_copy_while_it_fits(tmp_path: Path) -> None:
    """Склейки нет, а лента сдвинута: копия своего прогона - меньшее зло, пока влезает."""
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare, cap=4096)
    lay(run.run, 0, size=100)
    lay(spare, 0, size=200)
    _lay_out(run, _always, merge=lambda *a, **k: False, shift_of=lambda *a: 0.25)

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


def test_the_picture_of_the_recode_lies_on_the_timeline_of_this_run(tmp_path: Path) -> None:
    """Склейке передаётся сдвиг ленты прогона: прогон с нуля пишет метки на кадр вперёд
    времени фильма, и картинка перекода обязана лечь на его ленту, а не на свою.

    Заодно тут проверяется порядок дорожек: картинка идёт из перекода, звук - из копии
    ЭТОГО прогона, потому что звук показа обязан остаться одним потоком одного
    кодировщика (замер на «Тачках 3»: дыра 40.7 мс и 2-5 с пересборки на Q70D).
    """
    told: list[tuple[int, str]] = []
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare, told=lambda slot, how: told.append((slot, how)))
    lay(run.run, 0)
    lay(spare, 0, size=2048)
    seen: list[tuple[str, str, float]] = []

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        seen.append((video.name, audio.name, float(kwargs["shift"])))
        dst.write_bytes(b"mixed")
        return True

    _lay_out(run, _always, merge=merge, shift_of=lambda *a: 0.0417)

    assert seen == [("v0.ts", "v0.ts", 0.0417)], "сдвиг ленты прогона не доехал до склейки"
    assert (run.out / "v0.ts").read_bytes() == b"mixed"
    assert told == [(0, "склейка")], "журнал не отличает склейку от голого перекода"


def test_a_merge_that_failed_on_an_unshifted_run_sends_the_recode_as_it_is(
    tmp_path: Path,
) -> None:
    """Сдвиг неизвестен, склейки нет - наружу перекод как есть: тяжёлая копия хуже стыка."""
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare)
    lay(run.run, 0, size=100)
    lay(spare, 0, size=200)

    _lay_out(run, _always, merge=lambda *a, **k: False, shift_of=lambda *a: None)

    assert (run.out / "v0.ts").stat().st_size == 200, "наружу ушла не картинка перекода"


def test_a_copy_over_the_ceiling_loses_even_to_a_broken_seam(tmp_path: Path) -> None:
    """Копия тяжелее потолка не выходит наружу даже ради стыка.

    Кусок, который приёмник не доигрывает вовсе (19.4 МБ дают стоп 8 с), хуже разрыва в
    один кадр.
    """
    told: list[tuple[int, str]] = []
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare, cap=100, told=lambda slot, how: told.append((slot, how)))
    lay(run.run, 0, size=101)
    lay(spare, 0, size=50)

    _lay_out(run, _always, merge=lambda *a, **k: False, shift_of=lambda *a: 0.0417)

    assert (run.out / "v0.ts").stat().st_size == 50
    assert told == [(0, "перекод")]


def test_the_ceiling_weighs_the_finished_merge_and_not_its_halves(tmp_path: Path) -> None:
    """Потолок проверяет готовую склейку, а не её части до запуска ffmpeg.

    Обе половины влезают по отдельности, а готовый MPEG-TS выходит за потолок из-за звука
    и накладных расходов - и тогда наружу идёт голое видео перекода.
    """
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare, cap=100)
    lay(run.run, 0, size=40)
    lay(spare, 0, size=50)

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        dst.write_bytes(b"x" * 101)
        return True

    _lay_out(run, _always, merge=merge, shift_of=lambda *a: 0.0)

    assert (run.out / "v0.ts").stat().st_size == 50
    assert not (run.run / "mix0.ts").exists(), "склейка за потолком осталась лежать"


def test_the_merged_piece_is_not_mistaken_for_a_packed_segment(tmp_path: Path) -> None:
    """Склейка лежит в каталоге прогона, но сегментом не считается.

    «Кусок дописан» - это появление СЛЕДУЮЩЕГО ``v*.ts``, и посторонний файл не имеет
    права на это влиять.
    """
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare)
    for slot in (0, 1, 2):
        lay(run.run, slot)
    lay(spare, 0, size=2048)

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        dst.write_bytes(b"mixed")
        return True

    _lay_out(run, _never, merge=merge, shift_of=lambda *a: 0.0)

    assert (run.out / "v0.ts").read_bytes() == b"mixed"
    # Кусок v2 не дописан (следующего за ним нет) и наружу не ушёл - а ушёл бы, если бы
    # склейка попала в перебор каталога прогона и сдвинула «последний» на единицу.
    assert not (run.out / "v2.ts").exists()
    assert sorted(p.name for p in run.run.glob("v*.ts")) == ["v2.ts"]
