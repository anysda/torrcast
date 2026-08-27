"""Выкладка наружу: что дописано, что придержано, что тяжелее потолка и что пропущено."""

from __future__ import annotations

import math
import subprocess
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest

from tests.conftest import CLIP_RATE, CLIP_SECONDS
from tests.usecases.feed_pack.world import FakeProc, lay, packer
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.pack_origin import pack_origin
from torrcast.adapters.stream_pack.pack_start import pack_start
from torrcast.adapters.stream_pack.packer_publish import _lay_out
from torrcast.adapters.stream_pack.track_starts import track_starts
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.domain.hls_settings import SPLIT_SLACK
from torrcast.domain.segment_container import FMP4
from torrcast.domain.track_place import TRACK_PLACE_MAX

if TYPE_CHECKING:
    from pathlib import Path


def _never() -> bool:
    return False


def _always() -> bool:
    return True


def _on_place(piece: str | Path) -> tuple[float, float]:
    """Обе дорожки склейки на месте своего слота: стенд это знает, а не меряет ffprobe.

    Ноль тут не годится: сверяются метки с ГРАНИЦЕЙ слота, а сетки у этих прогонов нет -
    значит и промаха нет ни у одной дорожки (:func:`_merged_out`).
    """
    return 0.0, 0.0


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

    _lay_out(run, _always, merge=merge, starts_of=_on_place)

    assert (run.out / "v0.ts").read_bytes() == b"mixed"
    assert told == [(0, "склейка")]
    assert not (spare / "v0.ts").exists(), "лишняя копия места осталась лежать"


def test_a_failed_merge_sends_the_copy_of_its_own_run_while_it_fits(tmp_path: Path) -> None:
    """Склейки нет: перекод принёс бы свой звук, поэтому копия своего прогона меньшее зло."""
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare, cap=4096)
    lay(run.run, 0, size=100)
    lay(spare, 0, size=200)
    _lay_out(run, _always, merge=lambda *a, **k: False)

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


def test_a_piece_shrunk_in_place_is_not_reported_as_a_failed_merge(tmp_path: Path) -> None:
    """🔴 TC-693. Ужатие на месте зовётся ужатием: склейку оно не пробовало вовсе.

    «Перекод» в журнале означает ровно одно - готовый кусок кодировщика, у которого
    склейка со звуком копии НЕ вышла, то есть заявка на разбор стыка. Ужатию склеивать
    нечего и не с чем: оно само и есть единственная версия куска. Пока оба звались одним
    словом, каждый ужатый кусок печатал «склейка не вышла» - на ровной сетке это 818
    ложных заявок на разбор за фильм.
    """
    told: list[tuple[int, str]] = []
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare, cap=10, told=lambda slot, how: told.append((slot, how)))
    lay(run.run, 0, size=100)

    def shrink(slot: int, size: int) -> bool:
        lay(spare, slot, size=5)
        return True

    run.shrink = shrink
    _lay_out(
        run,
        _always,
        merge=lambda *a, **k: False,
        shift_of=lambda *a: 0.0,
        keyless=lambda piece: False,
        starts_of=_on_place,
    )

    assert told == [(0, "ужатие")], "ужатый кусок назван перекодом - это ложный стык в журнале"


def test_a_piece_shrunk_in_place_goes_out_with_the_audio_of_its_own_copy(tmp_path: Path) -> None:
    """🔴 TC-708. Ужатие - второй прогон ffmpeg, и звук у него свой: сетка AAC считается
    от ``-ss`` прогона, а у соседей ``-ss`` другой.

    Живой замер на приставке (1080p, 13.5 Мбит/с, ужато одно место окна): у соседей-копий
    стык звука +0.021333 с - ровно один кадр AAC, - а у ужатого места на входе +0.074667
    (дыра 53 мс) и на выходе -0.053334 (метки назад). Приёмник на этом месте сам говорит
    ``DEMUXER_UNDERFLOW`` по звуку и встаёт в BUFFERING: 4.1-4.3 с потерянной плёнки в
    прогонах без склейки против нуля в трёх прогонах подряд с ней. Тяжёлая копия этого же
    места лежит рядом, и её звук - тот самый непрерывный поток, что уехал в соседей.
    """
    seen: list[tuple[str, str]] = []
    told: list[tuple[int, str]] = []
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare, cap=10, told=lambda slot, how: told.append((slot, how)))
    lay(run.run, 0, size=100)

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        seen.append((video.parent.name, audio.parent.name))
        dst.write_bytes(b"m" * 5)
        return True

    def shrink(slot: int, size: int) -> bool:
        lay(spare, slot, size=5)
        return True

    run.shrink = shrink
    _lay_out(
        run,
        _always,
        merge=merge,
        shift_of=lambda *a: 0.0,
        keyless=lambda piece: False,
        starts_of=_on_place,
    )

    assert seen == [("recode", "pack")], "ужатое место ушло со звуком своего же прогона"
    assert told == [(0, "ужатие")]
    assert (run.out / "v0.ts").read_bytes() == b"m" * 5, "наружу ушла не склейка"


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
    seen: list[tuple[str, str, float | None]] = []

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        seen.append((video.name, audio.name, kwargs.get("shift")))
        dst.write_bytes(b"mixed")
        return True

    _lay_out(run, _always, merge=merge, shift_of=lambda *a: 0.0417, starts_of=_on_place)

    assert seen == [("v0.ts", "v0.ts", None)], "картинку перекода подвинули под голову копии"
    assert (run.out / "v0.ts").read_bytes() == b"mixed"
    assert told == [(0, "склейка")], "журнал не отличает склейку от голого перекода"


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

    _lay_out(run, _always, merge=lambda *a, **k: False)

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

    _lay_out(run, _always, merge=merge, shift_of=lambda *a: 0.0, starts_of=_on_place)

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

    _lay_out(run, _never, merge=merge, shift_of=lambda *a: 0.0, starts_of=_on_place)

    assert (run.out / "v0.ts").read_bytes() == b"mixed"
    # Кусок v2 не дописан (следующего за ним нет) и наружу не ушёл - а ушёл бы, если бы
    # склейка попала в перебор каталога прогона и сдвинула «последний» на единицу.
    assert not (run.out / "v2.ts").exists()
    assert sorted(p.name for p in run.run.glob("v*.ts")) == ["v2.ts"]


def test_a_recode_without_a_leading_key_frame_is_thrown_out_instead_of_shown(
    tmp_path: Path,
) -> None:
    """🔴 TC-698. Перекод без опорного кадра в начале - кусок БЕЗ КАРТИНКИ, и наружу он не идёт.

    Склейка со звуком копии копирует поток ``-c copy``, а копирование выбрасывает всё до
    первого опорного кадра: нет его вовсе - выброшено всё видео, и зритель получает
    десять секунд звука на чёрном экране. Живой замер: 12 таких кусков из 39 (0.32-0.47 МБ
    вместо 9-11), приёмник умирает на них трижды за четыре минуты. Спасти такой кусок
    нечем (сегмент обязан быть самостоятельным), поэтому место идёт дальше обычным путём
    копии - то есть ужатием на месте.

    ⚠️ Сверка стоит именно ЗДЕСЬ, а не в самом заходе кодировщика, и это замер, а не
    вкус: заход выкладывает свои куски по ходу дела, показ забирает их раньше, чем
    заход кончится, и та же сверка на конце захода пропустила зрителю 2 куска из 38,
    тогда как здесь их ноль из 35.
    """
    told: list[tuple[int, str]] = []
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare, told=lambda slot, how: told.append((slot, how)))
    lay(run.run, 0)
    lay(spare, 0, size=2048)

    _lay_out(
        run, _always, merge=lambda *a, **k: True, keyless=lambda piece: True, starts_of=_on_place
    )

    assert told == [(0, "копия")], "кусок без картинки уехал зрителю"
    assert not (spare / "v0.ts").exists(), "негодный перекод остался лежать готовым куском"
    assert (run.out / "v0.ts").read_bytes() == b"x" * 1024, "наружу ушла не копия"


def test_a_recode_that_starts_with_a_key_frame_still_goes_out_as_a_merge(tmp_path: Path) -> None:
    """Отрицательная проба к TC-698: исправный перекод сверка не трогает."""
    told: list[tuple[int, str]] = []
    spare = tmp_path / "recode"
    spare.mkdir()
    run = packer(tmp_path, spare=spare, told=lambda slot, how: told.append((slot, how)))
    lay(run.run, 0)
    lay(spare, 0, size=2048)

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        dst.write_bytes(b"m" * 3072)
        return True

    _lay_out(run, _always, merge=merge, keyless=lambda piece: False, starts_of=_on_place)

    assert told == [(0, "склейка")]


#: Заход кодировщика в пробе ниже: с какого куска сетки и по какой. Кусок без опорного
#: кадра берётся на ВНУТРЕННИХ границах захода, поэтому одной границы тут мало, а
#: начинаться заход обязан не с нуля: своё место в ленте ему задаёт ``-ss``, и от него же
#: считается кадровая сетка кодировщика.
_FIRST, _LAST = 1, 3


def _video_packets(piece: Path) -> list[str]:
    """Флаги видеопакетов куска по порядку; пусто - видео в куске нет вовсе."""
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "packet=flags",
         "-of", "csv=p=0", str(piece)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def _pack(
    source: str, where: Path, grid: Grid, slot: int, encode: Encode | None, by_time: bool = False
) -> Path:
    """Один заход ffmpeg по сетке ``grid`` до :data:`_LAST` включительно.

    ``by_time`` - резать по ВРЕМЕНИ с прежним допуском, то есть так, как режет заход,
    который опорных кадров не ставит. Перекодирующий заход ставит их сам и режет по ним
    (:data:`torrcast.adapters.ffmpeg.pack_command.KEY_CUT_SLACK`), поэтому куска без опорного
    кадра больше не даёт - а предохранителю выкладки такой кусок нужен предметом, и
    берётся он ровно тем резом, который его и порождал.
    """
    where.mkdir(parents=True)
    command = ffmpeg_pack_command(source, 0, str(where), grid, slot, grid.start(slot),
                                  readrate=0.0, encode=encode, until=_LAST)  # fmt: skip
    if by_time:
        command[command.index("-break_non_keyframes") + 1] = "1"
        command[command.index("-segment_time_delta") + 1] = f"{SPLIT_SLACK:g}"
    subprocess.run(command, check=True, capture_output=True, timeout=300)
    return where


def _keyless(spare: Path) -> list[int]:
    """Куски захода, начинающиеся НЕ с опорного кадра."""
    heads = {slot: _video_packets(spare / segment_name(slot)) for slot in range(_FIRST, _LAST + 1)}
    return [slot for slot, flags in heads.items() if flags and not flags[0].startswith("K")]


def test_a_recode_pass_on_a_flat_grid_never_lands_without_a_keyframe(
    clip: str, tmp_path: Path
) -> None:
    """🔴 TC-775. На ровной сетке потолок битрейта работает: наружу идёт перекод, а не копия.

    Предохранитель TC-698 задуман на редкий кусок, а на ровной сетке он срабатывал на
    КАЖДОМ: рез шёл по времени, принудительный опорный кадр доставался куску слева, и
    выкладка выбрасывала перекод целиком - вместе с потолком битрейта, который в нём и
    уезжал. Наружу вместо него шла копия исходника, каким бы тяжёлым он ни был.

    Меряется цель, а не её признак: сколько кусков захода уехало КАРТИНКОЙ ПЕРЕКОДА.
    Ровно её вес и держит потолок профиля; копия на этом месте значит, что потолка нет.
    Сверху - положительный контроль на самом входе: ролик обязан быть таким, где старый
    рез по времени этот дефект даёт (:data:`tests.conftest.CLIP_RATE`), иначе проба зелена
    не потому, что рез исправлен, а потому, что ловить было нечего.
    """
    grid = Grid.uniform(float(CLIP_SECONDS))
    run = _pack(clip, tmp_path / "copy", grid, 0, None)
    encode = Encode(preset="ultrafast", mbit=1.0)
    assert _keyless(_pack(clip, tmp_path / "by-time", grid, _FIRST, encode, by_time=True)), (
        "рез по времени на этом ролике куска без опорного кадра не даёт - ловить нечего"
    )

    spare = _pack(clip, tmp_path / "recode", grid, _FIRST, encode)
    assert not _keyless(spare), "перекод встал без опорного кадра - выкладка выбросит его"

    told: list[tuple[int, str]] = []
    out = tmp_path / "out"
    out.mkdir()
    packer(tmp_path, proc=FakeProc(code=0), out=out, run=run, spare=spare, last=_LAST,
           told=lambda slot, how: told.append((slot, how))).publish()  # fmt: skip

    # Слот 0 перекода не ждал - заход начинается с :data:`_FIRST`, и копия там честная.
    assert [pair for pair in told if pair[0] >= _FIRST] == [
        (slot, "склейка") for slot in range(_FIRST, _LAST + 1)
    ], "наружу ушла копия - потолок битрейта профиля на ровной сетке не работает"


def _recode_run(source: str, where: Path, grid: Grid, slot: int, delta: str | None) -> Path:
    """Один заход кодировщика от ``slot`` до конца фильма; ``delta`` подменяет допуск реза."""
    where.mkdir(parents=True)
    command = ffmpeg_pack_command(
        source, 0, str(where), grid, slot, grid.start(slot),
        readrate=0.0, encode=Encode(preset="ultrafast", mbit=1.0), until=grid.count - 1,
    )  # fmt: skip
    if delta is not None:
        command[command.index("-segment_time_delta") + 1] = delta
    subprocess.run(command, check=True, capture_output=True, timeout=300)
    return where


def _slot_offsets(where: Path, grid: Grid) -> dict[int, float]:
    """Промах первого кадра каждого куска против границы ЕГО НОМЕРА, настоящим ffprobe."""
    found = {}
    for piece in sorted(where.glob("v*.ts")):
        number = int(piece.stem[1:])
        found[number] = track_starts(piece)[0] - grid.origin - grid.start(number)
    return found


def test_a_recode_pass_on_a_keyed_grid_keeps_every_piece_on_its_own_slot(
    clip_mp4_24fps: str, tmp_path: Path
) -> None:
    """На сетке по опорным кадрам номер файла перекода обязан остаться номером слота.

    Граница такой сетки - сам опорный кадр, и рез идёт по кадру (``-break_non_keyframes
    0``). Но ``-ss`` уезжает в команду с тремя знаками, и граница, округлившаяся вверх до
    миллисекунды, роняет свой кадр точной перемоткой: первый пакет прогона встаёт на кадр
    позже границы, и цель каждого реза сдвигается на период кадра - за окно
    :data:`SPLIT_SLACK`. Муксер ждёт следующий опорный кадр, склеивает два слота в один
    файл, а файлы считает ПОДРЯД: дальше номер файла перестаёт быть номером слота, и
    сползание монотонно. Замер настоящим ffmpeg на этом ролике до правки: все резы захода
    уехали ровно на слот (+10.417 с) при исправном звуке. На ролике, чьи границы
    округляются вниз или ложатся на миллисекунды ровно, кадр не роняется и класс невидим
    (:func:`tests.conftest.clip_mp4_24fps`), поэтому слот захода СЧИТАЕТСЯ по карте -
    первый, чья граница округляется вверх.

    Меряется цель, а не признак: первый кадр каждого выданного куска против границы его
    номера. Сверху - положительный контроль: тот же заход с прежним узким допуском обязан
    сползти, иначе вход не способен показать дефект и зелёный цвет пробы ничего не значит.
    """
    grid = Grid.on_keyframes(
        _keyframes(clip_mp4_24fps), float(CLIP_SECONDS), origin=pack_origin(clip_mp4_24fps)
    )
    slot = next(k for k in range(1, grid.count - 2) if round(grid.start(k), 3) > grid.start(k))

    tight = _slot_offsets(
        _recode_run(clip_mp4_24fps, tmp_path / "tight", grid, slot, f"{SPLIT_SLACK:g}"), grid
    )
    assert any(miss > TRACK_PLACE_MAX for miss in tight.values()), (
        f"с прежним допуском заход не сполз ({tight}) - вход не способен показать дефект"
    )

    made = _recode_run(clip_mp4_24fps, tmp_path / "recode", grid, slot, None)
    got = _slot_offsets(made, grid)
    assert len(got) == grid.count - slot, (
        f"кусков {len(got)} вместо {grid.count - slot} - рез потерян, файлы посчитаны подряд"
    )
    for number, miss in got.items():
        assert abs(miss) <= TRACK_PLACE_MAX, (
            f"v{number} начинается на {miss:+.3f} с от границы своего номера - "
            "номер файла перестал быть номером слота"
        )


def test_a_piece_without_a_single_video_frame_never_reaches_the_viewer(
    clip: str, tmp_path: Path
) -> None:
    """🔴 TC-698 живьём: ни один выложенный кусок не уходит зрителю без картинки.

    Куски тут не подрисованы, а нарезаны настоящим ffmpeg с резом ПО ВРЕМЕНИ - тем самым,
    которым режет заход, не ставящий опорных кадров. При таком резе принудительный опорный
    кадр вправе лечь по ту сторону границы, и тогда следующий кусок начинается кадром без
    ``K``. Склейка со звуком копии копирует поток ``-c copy``, копирование выбрасывает всё
    до первого опорного кадра - и наружу уходят десять секунд звука на чёрном экране.

    Мера тут одна и она про зрителя: что именно легло в каталог показа. Сверху стоит
    положительный контроль - заход обязан ХОТЯ БЫ РАЗ встать без опорного кадра, иначе
    проба зелена не потому, что выкладка работает, а потому, что ловить было нечего. На
    роликах, чья кадровая сетка делит границу нацело, этого не случается ни разу
    (:data:`tests.conftest.CLIP_RATE`), и такой вход прятал бы дефект целиком.
    """
    grid = Grid.uniform(float(CLIP_SECONDS))
    run = _pack(clip, tmp_path / "copy", grid, 0, None)
    spare = _pack(
        clip, tmp_path / "recode", grid, _FIRST, Encode(preset="ultrafast", mbit=1.0), by_time=True
    )
    out = tmp_path / "out"
    out.mkdir()

    assert _keyless(spare), "заход ни разу не встал без опорного кадра - выкладке нечего ловить"

    # Процесс вышел нулём: прогон дочитал вход, и «дописан ли последний кусок» решает
    # один этот код - выкладке есть что отдавать наружу до самого :data:`_LAST`.
    packer(tmp_path, proc=FakeProc(code=0), out=out, run=run, spare=spare, last=_LAST).publish()

    laid = sorted(out.glob("v*.ts"))
    assert laid, "выкладка не отдала наружу ни одного куска"
    for piece in laid:
        assert _video_packets(piece), f"{piece.name} - ни одного видеокадра, зрителю чёрный экран"


def _keyframes(source: str) -> list[float]:
    """Опорные кадры ролика, снятые с самого файла.

    Границы сетки обязаны лечь на НАСТОЯЩИЕ кадры, а не на расчётный шаг ``-g``: кодировщик
    ставит опорные кадры и по смене сцены тоже, и сетка по расчётному шагу встала бы между
    ними. Тогда прогон садится на кадр раньше своей границы, у него появляется докатка -
    то есть собственный рез, - и предмет пробы исчезает: список резов уже не пуст.
    """
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-skip_frame", "nokey",
         "-show_entries", "frame=pts_time", "-of", "csv=p=0", source],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return sorted(float(line.strip(", ")) for line in done.stdout.splitlines() if line.strip(", "))


def _deliver(source: str, where: Path, grid: Grid, slot: int) -> Path:
    """Упаковать заход от ``slot`` до конца фильма и выложить его так, как это делает показ."""
    run, out = where / "run", where / "out"
    run.mkdir(parents=True)
    out.mkdir(parents=True)
    last = grid.count - 1
    at = pack_start(source, grid.start(slot))
    assert at == pytest.approx(grid.start(slot), abs=SPLIT_SLACK), (
        f"заход встал на {at:.3f} вместо своей границы {grid.start(slot):.3f} - "
        "у такого захода есть докатка, то есть свой рез, и ловить тут нечего"
    )
    subprocess.run(
        ffmpeg_pack_command(source, 0, str(run), grid, slot, at, readrate=0.0, until=last),
        check=True, capture_output=True, timeout=300,
    )  # fmt: skip
    packer(where, proc=FakeProc(code=0), out=out, run=run, first=slot, last=last, grid=grid,
           cap=1 << 40).publish()  # fmt: skip
    return out


def _stamps(piece: Path) -> list[float]:
    """Метки видеопакетов куска по порядку."""
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "packet=dts_time",
         "-of", "csv=p=0", str(piece)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return [float(line.strip(", ")) for line in done.stdout.splitlines() if line.strip(", ")]


def test_the_tail_redone_alone_is_the_same_tail_as_in_the_whole_pass(
    clip_mp4: str, tmp_path: Path
) -> None:
    """🔴 TC-771. Хвост, переделанный в одиночку, уезжает зрителю целиком, а не половиной.

    Заход в один-единственный слот-хвост - это штатная работа прогрева: заход, доведённый
    не до конца, оставляет слоты, которые потом переделываются поодиночке. Границ сетки
    внутри такого захода нет вовсе, список резов выходил пустым, а пустой список для
    сегментного муксера значит не «не режь», а «режь своим умолчанием» - и хвост
    закрывался на первом же опорном кадре за второй секундой. Замер настоящим ffmpeg до
    правки: 2.113 с / 554 788 Б вместо 7.884 с / 2 086 048 Б, то есть зритель терял конец
    фильма. Начало у обрезка при этом верное, и сверка начала (:func:`segment_start`) его
    пропускала: длину куска не сверял никто.

    Меряется то, что уехало зрителю: файл в каталоге показа, а не кусок в каталоге
    прогона. Эталон тут не число из отчёта, а тот же хвост из общего захода - оба
    нарезаны настоящим ffmpeg из одного файла по одной сетке.
    """
    grid = Grid.on_keyframes(_keyframes(clip_mp4), float(CLIP_SECONDS))
    last = grid.count - 1
    assert grid.on_keys and last >= 2, "нужна сетка по опорным кадрам и хвост, а не весь фильм"

    whole = _deliver(clip_mp4, tmp_path / "whole", grid, 0)
    lone = _deliver(clip_mp4, tmp_path / "lone", grid, last)

    tail = segment_name(last)
    assert (lone / tail).exists(), "хвост, переделанный в одиночку, наружу не вышел вовсе"
    assert _stamps(lone / tail) == pytest.approx(_stamps(whole / tail), abs=SPLIT_SLACK), (
        "хвост в одиночку нарезан не так, как в общем заходе - зритель теряет конец фильма"
    )


def test_a_tail_the_muxer_cut_by_its_own_default_never_reaches_the_viewer(
    clip_mp4: str, tmp_path: Path
) -> None:
    """🔴 TC-771, второй рубеж: обрезанный кусок наружу не идёт, кто бы его ни нарезал.

    Куски тут не подрисованы: заход нарезан настоящим ffmpeg, у которого отобран список
    резов, - ровно то, что делает сегментный муксер, когда резать ему не сказали. Первый
    кусок такого захода закрыт вдвое раньше своего места, и все прежние заборы он проходил:
    номер у него свой, начало верное (``segment_start``), сосед в каталоге открыт. Ловит
    его только длина - и ловит по слову самого ffmpeg, по его же списку нарезки.

    Один этот рубеж дефект не лечит: место остаётся непрогретым, и следующий круг возьмётся
    за него снова. Он отвечает за другое - что обрезок не уедет зрителю ни при каком
    стечении обстоятельств.
    """
    grid = Grid.on_keyframes(_keyframes(clip_mp4), float(CLIP_SECONDS))
    last = grid.count - 1
    run, out = tmp_path / "run", tmp_path / "out"
    run.mkdir()
    out.mkdir()

    command = ffmpeg_pack_command(
        clip_mp4, 0, str(run), grid, last, grid.start(last), readrate=0.0, until=last
    )
    if "-segment_times" in command:
        cut = command.index("-segment_times")
        command = command[:cut] + command[cut + 2 :]
    subprocess.run(command, check=True, capture_output=True, timeout=300)
    assert len(list(run.glob("v*.ts"))) > 1, (
        "муксер не разрезал хвост своим умолчанием - проверять тут нечего"
    )

    packer(tmp_path, proc=FakeProc(code=0), out=out, run=run, first=last, last=last, grid=grid,
           cap=1 << 40).publish()  # fmt: skip

    assert not list(out.glob("v*.ts")), "обрезанный хвост уехал зрителю"


#: Ролик пробы ниже: опорные кадры вдвое реже шага сетки. Ровно это и делает промах карты
#: видимым - на ролике с частыми кадрами рез успевает встать почти на место.
_LYING_STEP = 10.01


def _sparse_clip(where: Path) -> str:
    """Ролик, у которого опорные кадры стоят вдвое реже шага сетки."""
    path = where / "sparse.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc2=size=320x180:rate={CLIP_RATE}",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", "180",
         "-c:v", "libx264", "-preset", "ultrafast", "-g", "480", "-sc_threshold", "0",
         "-bf", "3", "-c:a", "aac", "-movflags", "+faststart", "-y", str(path)],
        check=True, capture_output=True, timeout=300,
    )  # fmt: skip
    return path.as_uri()


def _places(pieces: list[Path], grid: Grid) -> dict[str, tuple[float, float]]:
    """Промах обеих дорожек каждого куска от границы его слота - настоящим ffprobe."""
    found: dict[str, tuple[float, float]] = {}
    for piece in pieces:
        want = grid.start(int(piece.stem[1:])) + grid.origin
        picture, sound = track_starts(piece)
        found[piece.name] = (picture - want, sound - want)
    return found


@pytest.mark.ffmpeg
def test_no_piece_carries_the_sound_of_another_place_when_the_key_map_lied(
    tmp_path: Path,
) -> None:
    """🔴 TC-833. Сетка построена по ВРУЩЕЙ карте - зрителю всё равно не уезжает чужой звук.

    Сетка тут ровно та, что убила показ «Матрицы»: границы обещаны каждые 10 с и объявлены
    опорными кадрами, а настоящие кадры стоят каждые 20 с. Копия режется по кадру
    (``-break_non_keyframes 0``), лишние границы муксер пропускает и начинает считать
    ФАЙЛЫ вместо границ - номер файла перестаёт быть номером слота. Перекод при этом ставит
    опорные кадры сам и режет верно, поэтому его картинка на месте, а звук копии - нет.

    Сверху стоит положительный контроль: если копия на этом входе с сеткой НЕ разъехалась,
    ловить пробе нечего и зелёный цвет ничего не значит.

    Меряется цель, а не признак: у каждого куска, который уехал наружу, звук обязан лежать
    на месте его же картинки - по пакетам, настоящим ffprobe.
    """
    source = _sparse_clip(tmp_path)
    bounds = tuple(round(_LYING_STEP * k, 3) for k in range(18))
    grid = Grid(bounds, 180.0, True, None, pack_origin(source))
    last = 4

    run, spare = tmp_path / "copy", tmp_path / "recode"
    for where, encode in ((run, None), (spare, Encode(preset="ultrafast", mbit=2.0))):
        where.mkdir()
        subprocess.run(
            ffmpeg_pack_command(
                source, 0, str(where), grid, 0, 0.0, readrate=0.0, encode=encode, until=last
            ),
            check=True,
            capture_output=True,
            timeout=300,
        )

    cuts = (run / "pack.csv").read_text("utf-8").splitlines()
    assert len(cuts) < len(bounds) - 1, (
        f"копия нарезала по сетке ({len(cuts)} резов на {len(bounds)} границ) - "
        "промах карты на этом входе не воспроизводится, ловить пробе нечего"
    )

    told: list[tuple[int, str]] = []
    out = tmp_path / "out"
    out.mkdir()
    packer(tmp_path, proc=FakeProc(code=0), out=out, run=run, spare=spare, last=last, grid=grid,
           cap=1 << 40, told=lambda slot, how: told.append((slot, how))).publish()  # fmt: skip

    assert told, "наружу не ушло ни одного куска - мерить нечего"
    places = _places(sorted(out.glob("v*.ts")), grid)
    assert places, "в каталоге показа нет ни одного куска"
    strayed = {
        name: miss
        for name, miss in places.items()
        if not all(abs(off) <= TRACK_PLACE_MAX for off in miss)
    }
    assert not strayed, f"зрителю уехало чужое место (картинка, звук): {strayed}"


def test_the_tape_of_a_show_on_mpegts_is_the_common_origin_and_nothing_is_probed(
    tmp_path: Path,
) -> None:
    """На mpegts метка куска - время фильма: оба захода пакуют одну ленту, поднятую origin.

    Мерить там нечего, и лишнего ffprobe на каждый прогон здесь не появляется.
    """
    asked: list[str] = []
    run = packer(tmp_path, grid=replace(Grid.uniform(60.0, 10.0), origin=100.0))
    lay(run.run, 0)

    def starts(piece: str | Path) -> tuple[float, float]:
        asked.append(str(piece))
        return 1.0, 1.0

    _lay_out(run, _always, starts_of=starts)

    assert run.tape == (100.0, 100.0)
    assert asked == []


def test_the_tape_of_a_show_on_cmaf_is_measured_by_the_first_piece_it_lays_out(
    tmp_path: Path,
) -> None:
    """🔴 На CMAF метка куска - счётчик прогона, у каждой дорожки свой.

    Живой замер: звук куска стоит на 49.792, а картинка ТОГО ЖЕ куска - на 59.809. Пока
    место слота сверялось с временем фильма напрямую, проверка отказывала каждой склейке
    подряд: промах -6204.457 с - ровно место куска на фильме.
    """
    asked: list[str] = []

    def starts(piece: str | Path) -> tuple[float, float]:
        asked.append(str(piece))
        return 59.809, 49.792

    run = packer(tmp_path, container=FMP4, grid=Grid.uniform(60.0, 10.0))
    (run.run / "init.mp4").write_bytes(b"i")
    (run.run / "v0.m4s").write_bytes(b"x" * 1024)
    (run.run / "v1.m4s").write_bytes(b"x" * 1024)

    _lay_out(run, _always, starts_of=starts)

    assert run.tape == (59.809, 49.792)
    assert asked == [f"concat:{run.out / 'init.mp4'}|{run.run / 'v0.m4s'}"], "лента без заголовка"


def test_the_tape_of_the_run_is_not_measured_a_second_time(tmp_path: Path) -> None:
    """Лента - свойство прогона: считать её на каждом куске значило бы спрашивать

    проверяемый кусок о нём самом, да ещё и два ffprobe на каждое место.
    """
    asked: list[str] = []

    def starts(piece: str | Path) -> tuple[float, float]:
        asked.append(str(piece))
        return 59.809, 49.792

    run = packer(tmp_path, container=FMP4, grid=Grid.uniform(60.0, 10.0))
    (run.run / "init.mp4").write_bytes(b"i")
    for slot in range(4):
        (run.run / f"v{slot}.m4s").write_bytes(b"x" * 1024)

    _lay_out(run, _always, starts_of=starts)

    assert len(asked) == 1


def test_a_piece_whose_tracks_did_not_answer_leaves_the_tape_unmeasured(tmp_path: Path) -> None:
    """Считать ленту по одной дорожке нельзя, а сверять место с невычисленной - тем более."""
    run = packer(tmp_path, container=FMP4, grid=Grid.uniform(60.0, 10.0))
    (run.run / "init.mp4").write_bytes(b"i")
    (run.run / "v0.m4s").write_bytes(b"x" * 1024)
    (run.run / "v1.m4s").write_bytes(b"x" * 1024)

    def starts(piece: str | Path) -> tuple[float, float]:
        return math.nan, 49.792

    _lay_out(run, _always, starts_of=starts)

    assert run.tape is None
