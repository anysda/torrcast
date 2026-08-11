"""Динамический битрейт: профиль тяжести, выбор пресета, стык копии с перекодом."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from torrcast.recode import (
    DEADLINE_MARGIN,
    FULL_PRESET,
    MAXRATE_GAIN,
    NEIGHBOUR_TOLL,
    PRESETS,
    RECODE_HEIGHT,
    Encode,
    Pace,
    Recoder,
    Weights,
    level_for,
    preset_for,
)
from torrcast.stream import (
    FilmKeys,
    Grid,
    Packer,
    ffmpeg_pack_command,
    pack_start,
    segment_name,
)

from .conftest import fake_packer


def _keys(duration: float = 300.0, gop: float = 2.0, rate: float = 2.0e6) -> FilmKeys:
    """Ровная карта: опорный кадр каждые ``gop`` секунд, ``rate`` байт в секунду."""
    at = [round(k * gop, 3) for k in range(int(duration / gop) + 1)]
    return FilmKeys(duration=duration, at=at, offset=[int(t * rate) for t in at], kind="mkv")


def _grid(duration: float = 300.0, gop: float = 2.0, step: float = 10.0) -> Grid:
    return Grid.on_keyframes(_keys(duration, gop).at, duration, step)


# --------------------------------------------------------------------- профиль тяжести


def test_the_profile_is_known_before_a_single_segment_is_packed() -> None:
    """Байты и секунды каждого сегмента считаются из карты — до всякой упаковки."""
    keys = _keys(rate=2.0e6)  # 2 МБ/с = 16 Мбит/с ровно
    grid = _grid()
    weights = Weights.of(keys, grid)
    assert weights is not None
    assert len(weights.raw) == grid.count
    assert weights.at(0) == pytest.approx(16.0, abs=0.1)


def test_a_map_without_offsets_gives_no_profile_instead_of_a_guess() -> None:
    """Кэш карты прошлой версии смещений не несёт — профиля нет, и это честный отказ."""
    bare = FilmKeys(duration=300.0, at=_keys().at, offset=[], kind="mkv")
    assert Weights.of(bare, _grid()) is None


def test_the_container_is_heavier_than_what_leaves_for_the_tv() -> None:
    """Поправка вычитается: у релиза с десятью дорожками контейнер врёт на 4 Мбит/с."""
    weights = Weights.of(_keys(rate=2.5e6), _grid(), extra=4.0)
    assert weights is not None
    assert weights.raw[0] == pytest.approx(20.0, abs=0.1)
    assert weights.at(0) == pytest.approx(16.0, abs=0.1)


def test_the_correction_is_refined_by_what_was_actually_published() -> None:
    """Первый же выложенный сегмент-копия правит поправку — гадать по ffprobe не надо."""
    weights = Weights.of(_keys(rate=2.5e6), _grid())
    assert weights is not None
    assert weights.at(0) == pytest.approx(20.0, abs=0.1)
    span = _grid().span(0)
    weights.calibrate(0, int(16.0e6 * span / 8), span)  # на деле уехало 16 Мбит/с
    assert weights.extra == pytest.approx(4.0, abs=0.2)


def test_a_recoded_segment_never_poisons_the_correction() -> None:
    """Перекодированный кусок легче любой поправки — по нему калиброваться нельзя."""
    weights = Weights.of(_keys(rate=2.5e6), _grid())
    assert weights is not None
    span = _grid().span(0)
    weights.calibrate(0, int(0.5e6 * span / 8), span)  # «сегмент» легче поправки
    assert weights.measured == 0


def test_heavy_slots_are_the_ones_the_receiver_cannot_take() -> None:
    keys = _keys(rate=2.0e6)
    grid = _grid()
    weights = Weights.of(keys, grid)
    assert weights is not None
    assert weights.heavy(15.0) == tuple(range(grid.count))
    assert weights.heavy(17.0) == ()


# ------------------------------------------------------------------------ выбор пресета


def test_a_distant_piece_is_encoded_at_the_best_quality_that_fits() -> None:
    """До куска пять минут, кодировать шестьдесят секунд — успевает самый качественный."""
    assert preset_for(seconds=60.0, slack=300.0) == PRESETS[0][0]


def test_a_piece_that_is_almost_here_gets_the_fastest_preset() -> None:
    """Кратковременное снижение качества допустимо, а подгруз — нет."""
    assert preset_for(seconds=60.0, slack=20.0) == PRESETS[-1][0]
    assert preset_for(seconds=60.0, slack=0.0) == PRESETS[-1][0]


def test_the_preset_ladder_is_walked_from_slow_to_fast() -> None:
    """Между «успевает медленный» и «не успевает никто» стоит средний, а не пропасть."""
    seconds = 60.0
    slack = seconds / PRESETS[1][1] / DEADLINE_MARGIN + 0.1
    assert preset_for(seconds, slack) == PRESETS[1][0]


# ------------------------------------------------------------------------- цель перекода


def _went(mbit: float) -> float:
    """Сколько Мбит/с получит приёмник в худшем случае кодера: пик, звук, mpegts."""
    from torrcast.stream import AUDIO_MBIT, TS_OVERHEAD

    return (mbit * MAXRATE_GAIN + AUDIO_MBIT) * TS_OVERHEAD


def test_the_target_of_a_long_piece_is_counted_from_its_length_not_pinned() -> None:
    """🔴 TC-483: 9 Мбит/с на 20-секундном куске - это 23 МБ при потолке 16.

    Длина куска сетки задаётся картой опорных кадров и доходит до 20 с, а цель
    кодировщика была константой. Не влезал САМ ПЕРЕКОД, а не только копия: ловушка на
    выходе (:meth:`torrcast.stream.Packer.publish`) ловила это уже после того, как
    процессор был потрачен на кусок, который заведомо не влезал.
    """
    cap = 16_000_000
    pinned = 9.0 * 20.0 / 8 * 1e6
    assert pinned > cap * 1.4, "прибитые 9 Мбит/с кладут в 20 с около 23 МБ"

    fitted = Encode(mbit=9.0).fit(20.0, cap)
    assert _went(fitted.mbit) * 20.0 / 8 <= cap / 1e6, "кусок обязан влезать по весу"
    # А короткому куску ронять качество не за что: там те же 16 МБ терпят все девять.
    assert Encode(mbit=9.0).fit(10.0, cap).mbit == 9.0


def test_the_target_never_rises_above_the_one_already_standing() -> None:
    """Вверх не перекодируем: потолок умеет только опустить цель, но не поднять её."""
    cap = 16_000_000
    assert Encode(mbit=4.0).fit(2.0, cap).mbit == 4.0, "короткий кусок не повод разгоняться"
    assert Encode(mbit=9.0).fit(2.0, cap).mbit == 9.0


def test_the_target_fits_the_receivers_bitrate_ceiling_too_when_asked() -> None:
    """🔴 TC-495: потолка два, и по весу кусок может влезать, а по битрейту - нет.

    Живой показ 11-08: ужатие на месте отдало кусок длиной 9.55 с на 10.94 Мбит/с при
    потолке приёмника около десяти. По весу те же 13 МБ влезали с запасом - чем короче
    кусок, тем больше мегабит в секунду помещается в одни и те же 16 МБ.
    """
    cap, rate = 16_000_000, 10.0
    by_weight = Encode(mbit=9.0).fit(9.55, cap)
    assert _went(by_weight.mbit) > rate, "один вес приёмник от подгруза не спасает"

    both = Encode(mbit=9.0).fit(9.55, cap, rate)
    assert _went(both.mbit) <= rate, "кусок обязан влезать и в битрейт приёмника"
    assert _went(both.mbit) * 9.55 / 8 <= cap / 1e6, "и по весу он влезать не перестал"


# -------------------------------------------------------------- команда перекодирования


def test_an_encoding_run_has_no_run_in_because_ss_is_exact() -> None:
    """При перекодировании ``-ss`` точен: первый пакет стоит ровно на границе сетки.

    Ровно на этом сгорела первая версия: измеренный пробным прогоном ``at`` уводил весь
    прогон на сегмент назад, и ``v359`` содержал место ``v360``.
    """
    grid = _grid()
    command = ffmpeg_pack_command(
        "src", 0, "/run", grid, 5, grid.start(5), encode=Encode(), until=7
    )
    assert command[command.index("-segment_start_number") + 1] == "5"
    times = command[command.index("-segment_times") + 1].split(",")
    assert float(times[0]) == pytest.approx(grid.start(6) - grid.start(5), abs=0.01)


def test_an_encoding_run_stops_at_the_slot_it_was_asked_for() -> None:
    """Заход кодировщика ограничен: перемотка обязана успевать переприоритезировать."""
    grid = _grid()
    command = ffmpeg_pack_command(
        "src", 0, "/run", grid, 5, grid.start(5), encode=Encode(), until=7
    )
    assert float(command[command.index("-to") + 1]) == pytest.approx(grid.end(7) + 1.0, abs=0.01)
    assert len(command[command.index("-segment_times") + 1].split(",")) == 3


def test_the_copy_path_is_untouched_by_the_encoder() -> None:
    """Без ``encode`` команда та же, что и до перекода, — регресса нарезки быть не может."""
    grid = _grid()
    command = ffmpeg_pack_command("src", 0, "/run", grid, 5, grid.start(5) - 3.0)
    assert command[command.index("-c:v") + 1] == "copy"
    assert "-to" not in command
    assert "-force_key_frames" not in command


def test_forced_keyframes_stand_on_the_grid_and_a_touch_earlier() -> None:
    """Границы печатаются с тремя знаками: округление вверх уводило опорный кадр вперёд,
    и на стыке копии с перекодом терялся кадр. Просим ровно на допуск муксера раньше."""
    grid = _grid()
    keys = Encode().args(grid, 5, 6)
    forced = [float(x) for x in keys[keys.index("-force_key_frames") + 1].split(",")]
    assert forced[0] < grid.start(5)
    assert grid.start(5) - forced[0] == pytest.approx(0.02, abs=0.001)
    assert len(forced) == 3


def test_the_encoder_keeps_the_codec_and_caps_the_bitrate() -> None:
    """Тот же кодек и то же разрешение — иначе приёмник заметит стык."""
    args = Encode(preset="superfast", mbit=12.0).args(_grid(), 0, 1)
    assert args[args.index("-c:v") + 1] == "libx264"
    assert args[args.index("-preset") + 1] == "superfast"
    assert args[args.index("-maxrate") + 1].rstrip("M") == "12.96"
    assert "-vf" not in args and "-s" not in args  # разрешение не трогаем


# ------------------------------------------------------------------ выкладка и приоритет


def test_a_ready_recoded_piece_goes_out_instead_of_the_heavy_copy(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Выкладка осталась в одном месте: перекод побеждает копию внутри :meth:`publish`."""
    out = tmp_path / "out"
    spare = out / "recode"
    spare.mkdir(parents=True)
    packer = fake_packer(out, first=0)
    packer.spare = spare
    packer.run.mkdir(parents=True, exist_ok=True)
    (packer.run / segment_name(0)).write_bytes(b"heavy" * 100)
    (packer.run / segment_name(1)).write_bytes(b"next")
    (spare / segment_name(0)).write_bytes(b"light")
    packer.publish()
    assert (out / segment_name(0)).read_bytes() == b"light"
    assert not (packer.run / segment_name(0)).exists()
    assert not (spare / segment_name(0)).exists()
    assert packer.edge == 0


def test_without_a_recoded_piece_the_copy_still_goes_out(tmp_path) -> None:  # type: ignore[no-untyped-def]
    out = tmp_path / "out"
    spare = out / "recode"
    spare.mkdir(parents=True)
    packer = fake_packer(out, first=0)
    packer.spare = spare
    packer.run.mkdir(parents=True, exist_ok=True)
    (packer.run / segment_name(0)).write_bytes(b"heavy")
    (packer.run / segment_name(1)).write_bytes(b"next")
    packer.publish()
    assert (out / segment_name(0)).read_bytes() == b"heavy"
    assert packer.edge == 0


def test_the_nearest_heavy_piece_ahead_is_taken_first(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Порядок работы — от места показа вперёд: дальний кусок подождёт."""
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.played = grid.start(10)
    job = recoder._pick()
    assert job is not None
    assert job[0] == 10


def test_a_seek_reprioritises_the_queue(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Перемотка меняет место показа — и следующий заход берётся уже от нового места."""
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.played = grid.start(2)
    assert (recoder._pick() or (None,))[0] == 2
    recoder.played = grid.start(20)
    assert (recoder._pick() or (None,))[0] == 20


def test_nothing_beyond_the_horizon_is_encoded_in_advance(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Горизонт — это не время, а tmpfs: готовые куски лежат в памяти."""
    grid = _grid(duration=3000.0)
    weights = Weights.of(_keys(duration=3000.0, rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src",
        audio=0,
        grid=grid,
        spare=tmp_path,
        weights=weights,
        threshold=15.0,
        ahead=30.0,
    )
    recoder.played = 0.0
    recoder.done = set(range(0, 20))
    assert recoder._pick() is None  # всё, что ближе 30 с, уже сделано; дальше - не лезем


def test_a_run_is_never_longer_than_the_cap(tmp_path) -> None:  # type: ignore[no-untyped-def]
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src",
        audio=0,
        grid=grid,
        spare=tmp_path,
        weights=weights,
        threshold=15.0,
        run_max=3,
    )
    job = recoder._pick()
    assert job is not None
    assert job[1] - job[0] + 1 <= 3


def test_played_pieces_leave_the_cache(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """tmpfs не резиновая: готовый кусок позади показа больше не нужен."""
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    (tmp_path / segment_name(0)).write_bytes(b"x")
    (tmp_path / segment_name(20)).write_bytes(b"x")
    recoder.done = {0, 20}
    recoder.played = grid.start(21)
    recoder._sweep()
    assert not (tmp_path / segment_name(0)).exists()
    assert (tmp_path / segment_name(20)).exists()


def test_a_film_with_no_heavy_pieces_starts_no_encoder(tmp_path) -> None:  # type: ignore[no-untyped-def]
    grid = _grid()
    weights = Weights.of(_keys(rate=0.5e6), grid)  # 4 Мбит/с - приёмник и не заметит
    assert weights is not None
    said: list[str] = []
    recoder = Recoder(
        source="src",
        audio=0,
        grid=grid,
        spare=tmp_path,
        weights=weights,
        threshold=15.0,
        log=said.append,
    )
    recoder.start()
    assert recoder.thread is None
    assert "перекодировать нечего" in said[0]


# ------------------------------------------------------------------ живой ffmpeg: стык


@pytest.mark.usefixtures("clip")
def test_a_recoded_piece_lands_on_the_same_place_with_the_same_stamps(clip, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Настоящий ffmpeg: перекодированный сегмент занимает то же место с теми же метками.

    Это и есть бесшовность в проверяемом виде: приёмнику отдаётся кусок с тем же
    абсолютным PTS, той же длины и с опорным кадром в начале — на стыке ему нечего
    заметить, кроме битрейта.
    """
    # Карта берётся ffprobe'ом, а не :func:`keyframes`: здесь важны настоящие опорные
    # кадры настоящего файла, а не путь их добычи (его проверяет ``test_keymap.py``).
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-skip_frame", "nokey",
         "-show_entries", "frame=pts_time:format=duration", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    rows = [r.strip().rstrip(",") for r in probe.stdout.splitlines() if r.strip()]
    at = sorted(float(r) for r in rows[:-1])
    grid = Grid.on_keyframes(at, float(rows[-1]), step=4.0)
    if grid.count < 4:
        pytest.skip("клип слишком короткий для сетки из четырёх сегментов")
    slot, last = 1, 2

    def run(encode: Encode | None) -> dict[int, tuple[float, float, bool]]:
        where = tmp_path / ("enc" if encode else "copy")
        (where / "run").mkdir(parents=True)
        # У копии место старта измеряется пробным прогоном (``-ss`` уводит на опорный
        # кадр раньше), у перекода - не измеряется вовсе: там ``-ss`` точен.
        at = grid.start(slot) if encode else pack_start(str(clip), grid.start(slot))
        command = ffmpeg_pack_command(
            str(clip), 0, str(where / "run"), grid, slot, at,
            readrate=0.0, encode=encode, until=last if encode else -1,
        )  # fmt: skip
        packer = Packer.start(command, where, where / "run", slot)
        packer.proc.wait(timeout=180)
        packer.publish()
        facts = {}
        for path in where.glob("v*.ts"):
            number = int(path.stem[1:])
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                 "packet=pts_time,flags", "-of", "csv=p=0", str(path)],
                capture_output=True, text=True, check=False,
            )  # fmt: skip
            rows = [r.split(",") for r in probe.stdout.strip().splitlines() if r]
            if not rows:
                continue
            stamps = sorted(float(r[0]) for r in rows)
            first_key = next((float(r[0]) for r in rows if "K" in r[1]), -1.0)
            facts[number] = (stamps[0], stamps[-1], abs(stamps[0] - first_key) < 0.001)
        return facts

    copied = run(None)
    recoded = run(Encode(preset="ultrafast", mbit=1.0))
    for number in range(slot, last + 1):
        assert number in recoded, f"кодировщик не отдал v{number}"
        assert number in copied, f"копия не отдала v{number}"
        began, ended, keyed = recoded[number]
        # Метка начала совпадает с копией с точностью до кадра, и кадр этот - опорный.
        assert abs(began - copied[number][0]) < 0.1, f"v{number}: метки разъехались"
        assert abs(ended - copied[number][1]) < 0.1, f"v{number}: длина разъехалась"
        assert keyed, f"v{number}: первый кадр не опорный - независимость сегмента враньё"


@pytest.mark.usefixtures("clip")
def test_the_fast_preset_really_sends_constrained_baseline(clip, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Что уходит на телевизор, читаем из SPS, а не из командной строки.

    Улика: в аргументах стоял ``-profile:v high``, а в потоке был ``profile_idc=66``.
    У x264 профиль - потолок, а не пол: на ``ultrafast`` (без CABAC и без 8x8dct) он
    остаётся Constrained Baseline, сколько ни проси High. Приёмник его берёт, поэтому
    здесь закреплён ФАКТ, а не желание: поднять профиль наружу - это смена потока,
    и делается она не правкой аргументов, а живой приёмкой на Q70D.
    """
    bsfs = subprocess.run(["ffmpeg", "-hide_banner", "-bsfs"], capture_output=True, text=True)
    if "trace_headers" not in bsfs.stdout:
        pytest.skip("ffmpeg собран без trace_headers - SPS не разобрать")
    out = tmp_path / "v0.ts"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", clip, "-t", "2",
         *Encode(preset=FULL_PRESET, mbit=2.0).args(_grid(), 0, 1), "-an", str(out)],
        check=True, capture_output=True,
    )  # fmt: skip
    trace = subprocess.run(
        ["ffmpeg", "-v", "trace", "-i", str(out), "-c", "copy", "-bsf:v", "trace_headers",
         "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    # Строка разбора выглядит как ``... 8  profile_idc  01000010 = 66``: имя поля и
    # значение после ``=``. Берём первое вхождение каждого - это первый заголовок потока.
    wanted = ("profile_idc", "entropy_coding_mode_flag", "max_num_ref_frames")
    fields: dict[str, str] = {}
    for line in trace.stderr.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[-2] != "=":
            continue
        for name in wanted:
            if name in parts:
                fields.setdefault(name, parts[-1])
    got = fields.get("profile_idc")
    assert got == "66", f"профиль потока сменился: {got}"
    assert fields.get("entropy_coding_mode_flag") == "0", "включился CABAC - это другой поток"
    # ffprobe про refs врёт всем файлам (это поле декодера), настоящее число - из SPS.
    assert fields.get("max_num_ref_frames") == "1", "выросло опорных кадров - вырос и DPB"


def test_the_deadline_is_the_packer_not_the_playhead(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Наружу сегмент выкладывает упаковщик, и он идёт впереди показа на ``burst``.

    Считай кодировщик срок по месту показа — и на старте, пока упаковщик разом выложил
    минуту вперёд, тяжёлые куски уходили бы копией. Ровно это и было в первом живом
    прогоне: v361 и v362 на 26 и 28 Мбит/с.
    """
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.played = 0.0
    assert recoder.slack(5) == pytest.approx(grid.start(5), abs=0.1)
    recoder.note(4, "копия")  # упаковщик выложил уже пять сегментов
    assert recoder.slack(5) == pytest.approx(grid.start(5) - grid.end(4), abs=0.1)


def test_what_the_packer_already_published_is_never_re_encoded(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Выложенный кусок перекодировать поздно: приёмник его либо забрал, либо заберёт."""
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.played = 0.0
    recoder.note(3, "копия")  # упаковщик выложил v0...v3
    job = recoder._pick()
    assert job is not None
    assert job[0] == 4


def test_a_run_never_promises_more_than_it_can_deliver_in_time(  # type: ignore[no-untyped-def]
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Длинный заход сам себе создаёт опоздание — он обрывается на первом несрочном куске.

    На обычной машине эта защита почти не срабатывает (даже ``ultrafast`` идёт вчетверо
    быстрее реального времени), поэтому здесь кодировщику назначается медленная машина.
    """
    import torrcast.recode as module

    monkeypatch.setattr(module, "PRESETS", (("medium", 0.5), ("veryfast", 0.6)))
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.played = 0.0
    recoder.note(3, "копия")
    job = recoder._pick()
    assert job is not None
    assert job[0] == 4
    assert job[1] < 4 + recoder.run_max - 1  # до конца заход не растянулся


def test_a_copy_waits_while_its_piece_is_being_recoded(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Упаковщик на старте прогона выкладывает минуту разом и обгонял кодировщик.

    Найдено живым прогоном: v361 и v362 «Моаны 2» (26 и 28 Мбит/с) уходили копией
    просто потому, что упаковщик успел раньше. Копия теперь ждёт — но только там, докуда
    показу далеко.
    """
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    recoder.played = 0.0
    recoder.began = clock.monotonic() - 100.0  # фора на подъём давно вышла
    assert recoder.holding(5)  # заход не идёт, но следующим возьмут ровно этот кусок
    recoder.job = (4, 8, clock.monotonic() + 60.0, clock.monotonic(), 4.0)
    assert recoder.holding(5)
    assert recoder.holding(9)  # следующий заход возьмёт и его - успевается
    assert not recoder.holding(20)  # а так далеко у кодировщика планов ещё нет


def test_a_piece_right_under_the_playhead_is_never_held_back(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Ожидание под носом у показа — это и есть подгруз, а он запрещён."""
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    recoder.began = clock.monotonic() - 100.0
    recoder.job = (4, 8, clock.monotonic() + 60.0, clock.monotonic(), 4.0)
    recoder.played = grid.start(5)  # показ уже здесь
    assert not recoder.holding(4)
    assert not recoder.holding(5)


def test_an_overdue_recode_stops_holding_the_copy(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Ждать мертвеца нельзя: просрочен срок — копия уходит как есть."""
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    recoder.played = 0.0
    recoder.began = clock.monotonic() - 100.0
    recoder.job = (4, 8, clock.monotonic() - 1.0, clock.monotonic() - 200.0, 4.0)
    assert not recoder.holding(5)


def test_publishing_stops_at_a_held_piece_and_leaves_no_hole(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Выложить кусок за придержанным — значит увести край за дыру, и запрос дыры стал бы
    для :meth:`Feed._steer` перемоткой назад."""
    out = tmp_path / "out"
    out.mkdir()
    packer = fake_packer(out, first=0)
    packer.run.mkdir(parents=True, exist_ok=True)
    for slot in range(4):
        (packer.run / segment_name(slot)).write_bytes(b"x")
    packer.hold = lambda slot, size=0: slot == 1
    packer.publish()
    assert (out / segment_name(0)).exists()
    assert not (out / segment_name(1)).exists()
    assert not (out / segment_name(2)).exists()
    assert packer.edge == 0
    assert (packer.run / segment_name(1)).exists()  # копия жива и дождётся своего часа


def test_a_slow_recode_is_not_worth_waiting_for(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Ждать стоит только то, что успеет: перекод, который не поспевает, копию не держит."""
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    recoder.began = clock.monotonic() - 100.0
    recoder.played = grid.start(4)  # до v5 остались секунды одного сегмента
    recoder.job = (4, 8, clock.monotonic() + 600.0, clock.monotonic(), 0.05)
    assert not recoder.holding(5)


def test_while_the_encoder_is_still_starting_the_copy_still_waits(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Упаковщик выкладывает burst разом, а ffmpeg кодировщика ещё поднимается.

    Без этой форы первые тяжёлые куски уходили копией просто потому, что процесс не успел
    стартовать, — на живом Q70D это стоило подвиса на 8.6 с.
    """
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    recoder.played = 0.0
    recoder.began = clock.monotonic()
    assert recoder.job is None
    assert recoder.holding(5)  # тяжёлый и далеко - подождём подъёма
    assert not recoder.holding(0)  # упаковку с него не начинали - это не голова прогона
    recoder.played = grid.start(5) - 3.0  # показ почти дошёл - подъём уже не успеет
    assert not recoder.holding(5)


# ------------------------------------------------------- первый сегмент показа (голова)


def test_the_very_first_segment_of_a_run_is_waited_for(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Голова прогона — единственный кусок, который держат прямо под носом у показа.

    Картинки в этот момент нет ни одного кадра, ждать тут значит стартовать, а не
    подгружаться. Уйди голова копией — приёмник встаёт на первой же секунде показа в
    тяжёлом месте — это и был случай «первый сегмент уходит как есть».
    """
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.opening(7)
    assert recoder.holding(7)


def test_a_light_first_segment_is_never_waited_for(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Лёгкому фильму перекодирование не мешает: голову держать не за чем и не за кого."""
    grid = _grid()
    weights = Weights.of(_keys(rate=0.5e6), grid)  # 4 Мбит/с - тяжёлого нет вовсе
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.opening(7)
    assert not recoder.holding(7)


def test_waiting_for_the_head_has_a_ceiling(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Кодировщик не поднялся — копия уходит как есть: тяжёлый кусок лучше чёрного экрана."""
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    recoder.opening(7)
    recoder.head_at = clock.monotonic() - recoder.head_wait - 0.1
    assert not recoder.holding(7)


def test_waiting_for_the_head_can_be_switched_off(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """``recode_head_wait = 0`` возвращает прежнее поведение — на случай отката."""
    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src",
        audio=0,
        grid=grid,
        spare=tmp_path,
        weights=weights,
        threshold=10.0,
        head_wait=0.0,
    )
    recoder.opening(7)
    assert not recoder.holding(7)


def test_a_ready_head_is_not_waited_for_a_second_longer(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Перекод лёг в каталог — держать нечего, :meth:`Packer.publish` возьмёт его сам."""
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.opening(7)
    (tmp_path / segment_name(7)).write_bytes(b"x")
    assert not recoder.holding(7)


def test_the_head_is_encoded_alone_and_therefore_fastest(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Голову берём заходом в один кусок: в общем заходе срок считался бы по последнему,
    вышел бы superfast, и первый сегмент был бы готов к пятой секунде вместо третьей."""
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.opening(7)
    assert recoder._pick() == (7, 7)
    assert preset_for(grid.span(7), recoder.slack(7)) == PRESETS[-1][0]


def test_a_seek_makes_the_new_place_the_head_and_rewinds_the_edge(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Перемотка назад: край упаковки обязан уехать назад вместе с ней.

    Иначе :meth:`_pick` считает всё позади уже выложенным и до конца показа не берётся
    ни за один кусок — включая тот, с которого перемотка и начинается.
    """
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.opening(0)
    for slot in range(12):
        recoder.note(slot, "копия")
    recoder.opening(3)  # перемотали назад
    assert recoder.edge == 2
    assert recoder.played == grid.start(3)
    assert recoder._pick() == (3, 3)


def test_the_packer_tells_the_encoder_where_the_run_begins(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Кодировщик узнаёт о новом месте показа раньше пробного прогона (0.5–1.7 с).

    Иначе он начинает голову позже упаковщика, и придерживать её копию нечем.
    """
    from torrcast import stream

    grid = _grid()
    seen: list[tuple[str, int]] = []

    class _Stub:
        spare = tmp_path / "recode"

        def opening(self, slot: int) -> None:
            seen.append(("голова", slot))

        def note(self, slot: int, recoded: bool) -> None: ...

        def holding(self, slot: int) -> bool:
            return False

    recoder = _Stub()

    def _probe(*a: object, **k: object) -> float:
        seen.append(("проба", 0))
        return 0.0

    monkeypatch.setattr(stream, "pack_start", _probe)
    monkeypatch.setattr(
        stream.Packer, "start", classmethod(lambda cls, *a, **k: fake_packer(tmp_path))
    )
    feed = stream.Feed(source="src", audio=0, out=tmp_path, grid=grid, recoder=recoder)
    feed.restart(5)
    assert seen == [("голова", 5), ("проба", 0)]


def test_the_head_run_is_not_niced_behind_the_packer(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Голову ждёт старт показа, а не запас впрок: каждая её секунда — чёрный экран.

    Замер («Моана 2» 13.3 ГБ, v0 длиной 19.96 с, ultrafast): ``nice 15`` — 8.05 с,
    ``nice 0`` — 5.84 с.
    """
    from torrcast import stream

    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    seen: list[list[str]] = []

    def _remember(cls: object, command: list[str], /, *a: object, **k: object) -> Packer:
        seen.append(command)
        return fake_packer(tmp_path)

    monkeypatch.setattr(stream.Packer, "start", classmethod(_remember))
    recoder.opening(3)
    recoder.stopped = True  # один круг: ждать реального ffmpeg тут нечего
    recoder._run(3, 3)
    recoder._run(9, 11)
    assert seen[0][:3] == ["nice", "-n", "0"]
    assert seen[1][:3] == ["nice", "-n", "15"]


def test_a_run_takes_its_target_from_its_longest_piece(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """🔴 TC-483: заход идёт одним ``-b:v`` на все куски, значит судит самый длинный.

    Куски сетки по опорным кадрам разной длины, и прибитая цель не влезала в потолок веса
    ровно на длинных. Взять среднюю по заходу нельзя: короткие соседи её вытянут вверх, и
    длинный кусок снова уедет за потолок - а ловить это на выходе поздно, процессор уже
    потрачен.
    """
    from torrcast import stream

    grid = Grid(bounds=(0.0, 6.0, 26.0, 32.0), duration=45.0, on_keys=True)
    weights = Weights.of(_keys(rate=4.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    seen: list[list[str]] = []

    def _remember(cls: object, command: list[str], /, *a: object, **k: object) -> Packer:
        seen.append(command)
        return fake_packer(tmp_path)

    monkeypatch.setattr(stream.Packer, "start", classmethod(_remember))
    recoder.stopped = True

    recoder._run(0, 2)  # куски 6, 20 и 6 с - судит двадцатисекундный
    long_target = float(seen[-1][seen[-1].index("-b:v") + 1].rstrip("M"))
    assert long_target == pytest.approx(Encode(mbit=9.0).fit(20.0, recoder.cap).mbit, abs=0.01)
    assert _went(long_target) * 20.0 / 8 <= recoder.cap / 1e6, "20 с обязаны влезть в потолок"

    recoder._run(0, 0)  # а сам по себе шестисекундный кусок качества не теряет
    assert float(seen[-1][seen[-1].index("-b:v") + 1].rstrip("M")) == pytest.approx(9.0)


def test_a_run_is_counted_by_what_it_published_not_by_what_is_left(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Готовый кусок из каталога уже мог забрать показ — глоб объявлял бы заход провальным.

    Ровно так «перекодировал v0» печаталось как «не дало ни куска за 7 с».
    """
    from torrcast import stream

    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    monkeypatch.setattr(
        stream.Packer,
        "start",
        classmethod(lambda cls, *a, **k: fake_packer(tmp_path, first=3, code=0, edge=4)),
    )
    recoder.stopped = True
    recoder._run(3, 4)  # каталог пуст: показ уже забрал оба куска наружу
    assert recoder.made == 2
    assert recoder.done == {3, 4}


def test_the_head_preempts_a_run_that_works_ahead(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Заход впрок бросается ради головы: её ждёт чёрный экран, а его — только tmpfs.

    Живой замер: заход за ``v0`` (7 с) съедал ровно столько же от ожидания ``v358``,
    и голова не успевала к сроку, хотя сама кодируется 9 с.
    """
    from torrcast import stream

    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    packer = fake_packer(tmp_path, first=0, edge=-1)
    monkeypatch.setattr(stream.Packer, "start", classmethod(lambda cls, *a, **k: packer))
    recoder.opening(0)
    recoder.played = grid.start(12)  # показ ушёл вперёд, кодировщик работает впрок за ним
    recoder.opening(3)  # перемотали НАЗАД - голова теперь позади захода
    recoder._run(12, 14)
    assert packer.stopped == "голова прогона важнее"


def test_the_pieces_right_after_the_current_run_are_held_too(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Заход за головой берёт ОДИН кусок — а упаковщик за эти секунды выкладывает три.

    Найдено на живом Q70D: голова `v358` ушла перекодом, а `v359`…`v361`
    (21–26 Мбит/с) — копией, потому что «не наш заход» означало «не держим». Показ упал
    в BUFFERING на 27 опросах из 43.
    """
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    recoder.opening(4)
    recoder.job = (4, 4, clock.monotonic() + 60.0, clock.monotonic(), PRESETS[-1][1])
    assert recoder.holding(5)  # следующий за головой - успеется, держим
    assert recoder.holding(6)
    assert not recoder.holding(25)  # а так далеко у кодировщика планов ещё нет


def test_a_piece_after_the_run_is_not_held_if_the_playhead_is_closer(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Считаем по сроку и за пределами захода: не успеть — значит не держать."""
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    recoder.played = grid.start(4)
    recoder.job = (4, 4, clock.monotonic() + 600.0, clock.monotonic(), 0.05)  # еле ползёт
    assert not recoder.holding(5)


def test_between_runs_the_copy_still_waits(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Дыра между заходами — это секунды, и в них уходило самое тяжёлое.

    Живой Q70D: заход за головой шёл 8 с при форе 6 с, и ровно в этот
    зазор ушёл копией `v359` на 26 Мбит/с («заход не идёт» в журнале).
    """
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    recoder.began = clock.monotonic() - 100.0  # фора на подъём давно вышла
    recoder.played = grid.start(5) - 5.0
    assert recoder.job is None
    assert recoder.holding(6)  # до него полтора десятка секунд - следующий заход успеет
    assert not recoder.holding(5)  # а этот уже под носом: ждать значит подгружаться


def test_a_heavy_copy_behind_the_playhead_is_not_counted_as_late(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """После перемотки прошлый прогон дописывает то, чего никто не увидит.

    Живой прогон: перемотка с 4900 на 5904 — и `v362`/`v363` доехали копией в журнал как
    опоздание, хотя показ ушёл оттуда за секунду до этого.
    """
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.opening(20)
    recoder.note(3, "копия")  # кусок далеко позади показа
    assert recoder.late == 0
    recoder.note(21, "копия")
    assert recoder.late == 1


def test_the_head_is_waited_for_while_the_encoder_is_still_on_it(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Потолок ожидания головы считается по РАБОТЕ кодировщика, а не по секундомеру.

    Живой Q70D, «Тачки 3»: голова (17.4 с фильма, 28.9 Мбит/с) кодировалась
    16 с, потому что те же 58 МБ в это время тянул из холодного роя упаковщик. Ожидание
    сдавалось на 12-й секунде, копия уезжала на ТВ — и приёмник вставал на её стыке со
    следующим куском на 10 с. Лишние 4 с ожидания были бесплатны: картинка всё равно
    появлялась на 16-й секунде.
    """
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    now = clock.monotonic()
    recoder.opening(7)
    recoder.head_at = now - recoder.head_wait - 1.0  # потолок по секундомеру вышел
    recoder.job = (7, 7, now + 5.0, now - 13.0, PRESETS[-1][1])  # заход за головой идёт
    assert recoder.holding(7)
    recoder.job = (9, 12, now + 5.0, now - 13.0, PRESETS[-1][1])  # заход чужой - не ждём
    assert not recoder.holding(7)


def test_the_head_wait_has_a_hard_ceiling_even_while_encoding(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Кодировщик, который не кончает, не имеет права держать чёрный экран без предела."""
    import time as clock

    from torrcast.recode import HEAD_LIMIT

    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    now = clock.monotonic()
    recoder.opening(7)
    recoder.head_at = now - recoder.head_wait * HEAD_LIMIT - 0.1
    recoder.job = (7, 7, now + 60.0, now - 30.0, PRESETS[-1][1])
    assert not recoder.holding(7)


def test_a_copy_heavier_than_the_cap_is_never_released_on_a_deadline(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Копию тяжелее :data:`MAX_SEGMENT_BYTES` не отпускают по сроку вовсе.

    Замер, ради которого правило написано («Тачки 3», старт 3880): сетка
    предсказала вес ``v364`` по ``ceiling_mbit`` («тяжёлое перекодируют») в 11.7 МБ,
    кодировщик к сроку не успел, срок вышел — и на ТВ уехала копия на **51.4 МБ**.
    Двадцать опросов ``BUFFERING`` за 46 с. Срок тут ни при чём: такой кусок приёмник не
    доигрывает ни при каких обстоятельствах, значит отпускать его некуда.
    """
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=4.0e6), grid)  # 32 Мбит/с: 10 с весят 40 МБ
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    recoder.played = 0.0
    recoder.began = clock.monotonic() - 100.0
    # Срок захода вышел двести секунд назад - по прежнему правилу копия ушла бы наружу.
    recoder.job = (4, 8, clock.monotonic() - 1.0, clock.monotonic() - 200.0, 4.0)
    assert recoder.holding(5), "просроченный перекод тяжёлую копию не освобождает"
    assert recoder.blocked == 5, "кодировщик обязан узнать, что выкладка встала на v5"
    # И даже под самым носом у показа: подгруз в 2 с дешевле срыва приёмника на 8.
    recoder.played = grid.start(5)
    assert recoder.holding(5)


def test_the_encoder_weighs_pieces_by_the_receivers_cap_not_its_own(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Потолок веса куска - свойство ПРИЁМНИКА, и мерка у показа с каталогом перекода одна.

    Раньше каталог перекода судил по осторожному умолчанию
    (:data:`torrcast.stream.MAX_SEGMENT_BYTES`), а показ - по потолку своего приёмника
    (:attr:`torrcast.stream.Feed.cap`): приёмник с другой меркой получал от кодировщика не
    свою. Пока приёмник один, числа совпадают, и разницы не видно - ровно поэтому её и
    надо закрыть числом, а не глазами.
    """
    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)  # 12 Мбит/с: 10 с весят 15 МБ
    assert weights is not None
    spacious = Recoder(source="src", audio=0, grid=grid, spare=tmp_path, weights=weights)
    assert not spacious.oversize(5), "в 16 МБ этот кусок влезает"
    assert 5 not in spacious.targets

    tight = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, cap=12_000_000
    )
    assert tight.oversize(5), "у приёмника с потолком 12 МБ тот же кусок уже за потолком"
    assert 5 in tight.targets, "и кодировщик обязан взять его заранее"


def test_the_weight_of_a_copy_is_taken_from_the_file_when_it_exists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Вес копии берётся у самого файла, а предсказание — только пока файла нет.

    Предсказание по карте зажато потолком перекодирования и на «Тачках 3» промахнулось
    вчетверо (11.7 МБ против 51.4). Честный ``stat`` не промахивается никогда.
    """
    grid = _grid()
    weights = Weights.of(_keys(rate=1.5e6), grid)  # по карте кусок лёгкий: 15 МБ
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    assert not recoder.oversize(5), "по карте - влезает"
    assert recoder.oversize(5, size=51_400_000), "а по факту приехало вчетверо больше"


def test_a_long_light_piece_is_recoded_too_because_it_is_too_heavy(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Кодировщик отвечает за два класса кусков, и они не совпадают.

    Замер по картам трёх релизов при пороге 10 Мбит/с: «Моана» 2016 — лёгкое кино, где
    тяжёлых кусков почти нет, а увесистых семь, самый большой 18.3 МБ при замеренной
    границе срыва приёмника 19.4 МБ. Такой кусок раньше не брал никто: битрейт ниже
    порога, а вес выше потолка.
    """
    grid = _grid(gop=20.0, step=10.0)  # опорные кадры редкие: сегмент = 20 с фильма
    weights = Weights.of(_keys(gop=20.0, rate=1.1e6), grid)  # 8.8 Мбит/с - не тяжёлый
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    assert weights.at(3) < recoder.threshold, "по битрейту приёмник его тянет"
    assert 3 in recoder.targets, "но 22 МБ одним куском он не доигрывает"


def test_the_bulky_copy_stays_inside_when_the_encoder_has_given_up(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Предохранитель ожидания не превращается в обход потолка приёмника."""
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=4.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    recoder.played = 0.0
    recoder.began = clock.monotonic() - 100.0

    recoder.done.add(5)  # заход над этим куском ничего не дал и повторять его нечем
    assert not recoder.holding(5), "предохранитель ожидания по-прежнему заканчивает выдержку"

    recoder.done.discard(5)
    assert recoder.holding(5)
    recoder.stuck[5] = clock.monotonic() - recoder.over_wait - 0.1  # предохранитель
    assert not recoder.holding(5), "предохранитель ожидания по-прежнему заканчивает выдержку"

    out = tmp_path / "out"
    out.mkdir()
    packer = fake_packer(out, first=5)
    packer.run.mkdir(parents=True, exist_ok=True)
    (packer.run / segment_name(5)).write_bytes(b"x" * 16_000_001)
    (packer.run / segment_name(6)).write_bytes(b"next")
    packer.hold = lambda slot, size: False  # выдержка уже закончилась
    packer.publish()
    assert not (out / segment_name(5)).exists(), "тяжёлая копия не выходит после выдержки"


def test_a_held_piece_stops_holding_once_its_recode_is_ready(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Перекод лёг в каталог — выкладка идёт дальше, и кодировщик про затор забывает."""
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=4.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=10.0
    )
    recoder.played = 0.0
    recoder.began = clock.monotonic() - 100.0
    assert recoder.holding(5)
    assert recoder.blocked == 5

    (tmp_path / segment_name(5)).write_bytes(b"x")
    assert not recoder.holding(5)
    assert recoder.blocked == -1, "затор рассосался, и чужие заходы бросать больше незачем"


def test_the_tail_of_a_run_is_dropped_and_never_published(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Огрызок за ``-to`` наружу не уезжает — ни от кодировщика, ни от упаковщика.

    Заход кодировщика ограничен ``-to`` с запасом в секунду, и муксер успевает открыть
    следующий файл: в нём секунда фильма вместо десяти. Живой Q70D, «Тачки 3»:
    такой `v311` (1.3 МБ вместо 11) уехал на ТВ как готовый кусок — приёмник встал на
    14 с и потерял 16 секунд фильма.
    """
    run, out = tmp_path / "run", tmp_path / "out"
    run.mkdir()
    out.mkdir()
    for slot in (4, 5, 6, 7):
        (run / segment_name(slot)).write_bytes(b"x" * 100)
    packer = fake_packer(out=out, run=run, first=5, last=6, code=0)
    packer.publish()
    assert sorted(p.name for p in out.glob("v*.ts")) == ["v5.ts", "v6.ts"]
    assert packer.edge == 6
    assert not (run / segment_name(7)).exists()  # огрызок убран, а не оставлен на потом
    assert not (run / segment_name(4)).exists()  # докатка - как и была


def test_the_correction_comes_from_the_passport_not_from_guesswork() -> None:
    """Разрыв «контейнер → ТВ» известен из ffprobe до первого же сегмента.

    И он не константа: по замерам у «Моаны 2» (10 озвучек, 12 субтитров)
    4.4 Мбит/с, у «Тачек 3» 2.2, у «Моаны» 2016 — 0.6. Слепая калибровка сходилась к
    этому числу за 8–10 выложенных сегментов, то есть первую минуту показа профиль врал.
    """
    grid = _grid()
    weights = Weights.of(_keys(rate=2.5e6), grid, delivered=16.0)  # контейнер 20 Мбит/с
    assert weights is not None
    assert weights.container == pytest.approx(20.0, abs=0.1)
    assert weights.extra == pytest.approx(4.0, abs=0.1)
    assert weights.at(0) == pytest.approx(16.0, abs=0.1)


def test_a_silent_passport_falls_back_to_blind_calibration() -> None:
    """mp4 без тегов mkvmerge веса дорожки не несёт — поправка набирается по факту."""
    weights = Weights.of(_keys(rate=2.5e6), _grid(), delivered=0.0)
    assert weights is not None
    assert weights.extra == 0.0
    assert weights.measured == 0


def test_the_passport_is_not_thrown_away_by_the_first_noisy_segment() -> None:
    """Паспорт — среднее по всему фильму, один сегмент — шум: пусть правит, но не рушит."""
    grid = _grid()
    weights = Weights.of(_keys(rate=2.5e6), grid, delivered=16.0)
    assert weights is not None
    weights.calibrate(0, int(20.0e6 / 8 * grid.span(0)), grid.span(0))  # «поправки нет»
    assert weights.extra == pytest.approx(3.4, abs=0.2)  # сдвинулся, но не обнулился


# ------------------------------------------------------------ звук на стыке с перекодом


def test_the_recoded_piece_goes_out_with_the_copy_s_sound(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Наружу — картинка перекода и звук копии: у звука показа один прогон на всё.

    Кадровая сетка AAC отсчитывается от ``-ss`` прогона, поэтому на первом куске каждого
    захода перекода звук копии обрывался, а звук перекода начинался позже: замер на
    «Тачках 3» — дыра 40.7 мс, и Q70D платил за неё 2–5 секундами пересборки.
    """
    out = tmp_path / "out"
    spare = out / "recode"
    spare.mkdir(parents=True)
    packer = fake_packer(out, first=0)
    packer.spare = spare
    packer.run.mkdir(parents=True, exist_ok=True)
    (packer.run / segment_name(0)).write_bytes(b"copy")
    (packer.run / segment_name(1)).write_bytes(b"next")
    (spare / segment_name(0)).write_bytes(b"recode")
    seen: list[tuple[str, str]] = []

    def merge(video, audio, dst, timeout=30.0, shift=0.0):  # type: ignore[no-untyped-def]
        seen.append((video.name, audio.name))
        dst.write_bytes(b"mixed")
        return True

    monkeypatch.setattr("torrcast.stream.merge_tracks", merge)
    packer.publish()
    assert seen == [(segment_name(0), segment_name(0))]  # картинка из перекода, звук из копии
    assert (out / segment_name(0)).read_bytes() == b"mixed"
    assert not (spare / segment_name(0)).exists()  # перекод забрали
    assert not (packer.run / segment_name(0)).exists()  # копию выбросили
    assert packer.edge == 0


def test_a_failed_merge_still_sends_the_recoded_piece(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Склейку не сверили с лентой прогона (сдвиг неизвестен) — наружу перекод как есть:
    это ровно сегодняшнее поведение, а тяжёлая копия из-под приёмника хуже стыка."""
    out = tmp_path / "out"
    spare = out / "recode"
    spare.mkdir(parents=True)
    packer = fake_packer(out, first=0)
    packer.spare = spare
    packer.run.mkdir(parents=True, exist_ok=True)
    (packer.run / segment_name(0)).write_bytes(b"heavy copy")
    (packer.run / segment_name(1)).write_bytes(b"next")
    (spare / segment_name(0)).write_bytes(b"recode")
    monkeypatch.setattr("torrcast.stream.merge_tracks", lambda *a, **k: False)
    monkeypatch.setattr("torrcast.stream.timeline_shift", lambda *a, **k: None)
    packer.publish()
    assert (out / segment_name(0)).read_bytes() == b"recode"
    assert packer.edge == 0


def test_the_recoded_picture_lies_on_the_run_s_own_timeline(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Склейке передаётся сдвиг ленты прогона: прогон с нуля пишет метки на кадр
    вперёд времени фильма, и картинка перекода обязана лечь на его ленту, а не на свою."""
    out = tmp_path / "out"
    spare = out / "recode"
    spare.mkdir(parents=True)
    packer = fake_packer(out, first=0)
    packer.spare = spare
    packer.run.mkdir(parents=True, exist_ok=True)
    (packer.run / segment_name(0)).write_bytes(b"copy")
    (packer.run / segment_name(1)).write_bytes(b"next")
    (spare / segment_name(0)).write_bytes(b"recode")
    told: list[tuple[int, str]] = []
    packer.told = lambda slot, how: told.append((slot, how))
    seen: list[float] = []

    def merge(video, audio, dst, timeout=30.0, shift=0.0):  # type: ignore[no-untyped-def]
        seen.append(shift)
        dst.write_bytes(b"mixed")
        return True

    monkeypatch.setattr("torrcast.stream.merge_tracks", merge)
    monkeypatch.setattr("torrcast.stream.timeline_shift", lambda *a, **k: 0.0417)
    packer.publish()
    assert seen == [0.0417]
    assert (out / segment_name(0)).read_bytes() == b"mixed"
    assert told == [(0, "склейка")]  # журнал различает склейку и голый перекод


def test_a_failed_merge_on_a_shifted_run_sends_the_copy(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Лента прогона сдвинута, а склейка не вышла — наружу КОПИЯ своего же прогона.

    Перекод как есть тут не «сегодняшнее поведение», а гарантированный разрыв: на голове
    захода приёмник получил бы кадр с меткой назад, а на хвосте — дыру в кадр.
    Копия своего прогона стыкуется с соседями точно, и пока она не тяжелее потолка
    (:data:`torrcast.stream.MAX_SEGMENT_BYTES`), она меньшее зло.
    """
    out = tmp_path / "out"
    spare = out / "recode"
    spare.mkdir(parents=True)
    packer = fake_packer(out, first=0)
    packer.spare = spare
    packer.run.mkdir(parents=True, exist_ok=True)
    (packer.run / segment_name(0)).write_bytes(b"copy")
    (packer.run / segment_name(1)).write_bytes(b"next")
    (spare / segment_name(0)).write_bytes(b"recode")
    told: list[tuple[int, str]] = []
    packer.told = lambda slot, how: told.append((slot, how))
    monkeypatch.setattr("torrcast.stream.merge_tracks", lambda *a, **k: False)
    monkeypatch.setattr("torrcast.stream.timeline_shift", lambda *a, **k: 0.0417)
    packer.publish()
    assert (out / segment_name(0)).read_bytes() == b"copy"
    assert not (spare / segment_name(0)).exists()  # перекод этому месту больше не нужен
    assert told == [(0, "копия")]


def test_a_too_heavy_copy_loses_even_to_a_broken_seam(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Копия тяжелее потолка не выходит наружу даже ради стыка: кусок, который приёмник
    не доигрывает вовсе (19.4 МБ дают стоп 8 с), хуже разрыва в один кадр."""
    from torrcast.stream import MAX_SEGMENT_BYTES

    out = tmp_path / "out"
    spare = out / "recode"
    spare.mkdir(parents=True)
    packer = fake_packer(out, first=0)
    packer.spare = spare
    packer.run.mkdir(parents=True, exist_ok=True)
    (packer.run / segment_name(0)).write_bytes(b"x" * (MAX_SEGMENT_BYTES + 1))
    (packer.run / segment_name(1)).write_bytes(b"next")
    (spare / segment_name(0)).write_bytes(b"recode")
    told: list[tuple[int, str]] = []
    packer.told = lambda slot, how: told.append((slot, how))
    monkeypatch.setattr("torrcast.stream.merge_tracks", lambda *a, **k: False)
    monkeypatch.setattr("torrcast.stream.timeline_shift", lambda *a, **k: 0.0417)
    packer.publish()
    assert (out / segment_name(0)).read_bytes() == b"recode"
    assert told == [(0, "перекод")]


def test_a_merge_heavier_than_the_cap_is_not_sent_to_the_receiver(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Потолок проверяет готовую склейку, а не её части до запуска ffmpeg."""
    from torrcast.stream import MAX_SEGMENT_BYTES

    out = tmp_path / "out"
    spare = out / "recode"
    spare.mkdir(parents=True)
    packer = fake_packer(out, first=0)
    packer.spare = spare
    packer.run.mkdir(parents=True, exist_ok=True)
    (packer.run / segment_name(0)).write_bytes(b"copy")
    (packer.run / segment_name(1)).write_bytes(b"next")
    (spare / segment_name(0)).write_bytes(b"recode")

    def merge(video, audio, dst, timeout=30.0, shift=0.0):  # type: ignore[no-untyped-def]
        dst.write_bytes(b"x" * (MAX_SEGMENT_BYTES + 1))
        return True

    monkeypatch.setattr("torrcast.stream.merge_tracks", merge)
    packer.publish()
    assert (out / segment_name(0)).read_bytes() == b"recode"
    assert (out / segment_name(0)).stat().st_size <= MAX_SEGMENT_BYTES


def test_the_timeline_shift_of_garbage_is_unknown(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Сверить ленту не по чему — так и говорим: ``None``, а не «сдвига нет»."""
    from torrcast.stream import timeline_shift

    copy, recode = tmp_path / "c.ts", tmp_path / "r.ts"
    copy.write_bytes(b"not a stream")
    recode.write_bytes(b"also not a stream")
    assert timeline_shift(copy, recode) is None


def test_the_merged_piece_is_not_mistaken_for_a_packed_segment(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Склейка лежит в каталоге прогона, но сегментом не считается: «кусок дописан» —
    это появление СЛЕДУЮЩЕГО ``v*.ts``, и посторонний файл не имеет права на это влиять."""
    out = tmp_path / "out"
    spare = out / "recode"
    spare.mkdir(parents=True)
    packer = fake_packer(out, first=0)
    packer.spare = spare
    packer.run.mkdir(parents=True, exist_ok=True)
    for slot in (0, 1, 2):
        (packer.run / segment_name(slot)).write_bytes(b"copy")
    (spare / segment_name(0)).write_bytes(b"recode")

    def merge(video, audio, dst, timeout=30.0, shift=0.0):  # type: ignore[no-untyped-def]
        dst.write_bytes(b"mixed")
        return True

    monkeypatch.setattr("torrcast.stream.merge_tracks", merge)
    packer.publish()
    assert (out / segment_name(0)).read_bytes() == b"mixed"
    # Кусок v2 не дописан (следующего за ним нет) и наружу не ушёл - а ушёл бы, если бы
    # склейка попала в перебор каталога прогона и сдвинула «последний» на единицу.
    assert not (out / segment_name(2)).exists()
    assert sorted(p.name for p in packer.run.glob("v*.ts")) == [segment_name(2)]


def test_merge_of_garbage_leaves_no_file_and_says_so(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Не вышло — значит не вышло: ни файла-огрызка, ни ``True``."""
    from torrcast.stream import merge_tracks

    video, audio, dst = tmp_path / "v.ts", tmp_path / "a.ts", tmp_path / "mix.ts"
    video.write_bytes(b"not a stream")
    audio.write_bytes(b"also not a stream")
    assert merge_tracks(video, audio, dst) is False
    assert not dst.exists()


# ------------------------------------------------------------------ сплошной перекод


def test_a_codec_the_receiver_cannot_decode_is_a_decision_about_the_file() -> None:
    """Кодек решается один раз и на весь файл, а не на кусок.

    Посегментное решение (тяжёлый — перекодируем, лёгкий — копией) на HEVC-релизе даёт
    смешанный поток H.264 и HEVC, а его приёмник не доигрывает: замер на живом Q70D —
    24 с картинки и вечная петля «залип → перезагрузка» ровно на границе первого
    HEVC-куска. Поэтому признак файла — паспорт ffprobe, и ничего больше.
    """
    from torrcast.cli import _encode_all
    from torrcast.state import Config

    config = Config(recode=True, recode_mbit=9.0)
    whole = _encode_all(config, "hevc")
    assert whole is not None, "HEVC обязан перекодироваться целиком"
    assert (whole.preset, whole.mbit) == (FULL_PRESET, 9.0), "пресет замерен, потолок прежний"
    assert _encode_all(config, "h264") is None, "H.264 уезжает копией, как и раньше"
    assert _encode_all(config, "") is None, "паспорт молчит - прежнее поведение"
    assert _encode_all(Config(recode=False), "hevc") is None, "перекодирование выключено"


def test_the_whole_file_run_encodes_every_segment_to_the_end_of_the_film() -> None:
    """Прогон сплошного перекода не ограничен ни куском, ни заходом.

    Отличие от захода кодировщика ровно в этом: ``-to`` нет вовсе, а принудительные
    опорные кадры стоят на КАЖДОЙ границе сетки до конца фильма — иначе сегментный муксер
    с ``-break_non_keyframes 0`` ждал бы кадр кодировщика и резал бы куда попало.
    """
    grid = _grid()
    command = ffmpeg_pack_command("src", 0, "/run", grid, 0, 0.0, encode=Encode(preset=FULL_PRESET))
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-preset") + 1] == FULL_PRESET
    assert "-to" not in command, "сплошной перекод идёт до конца входа"
    forced = [float(x) for x in command[command.index("-force_key_frames") + 1].split(",")]
    assert len(forced) == grid.count, "опорный кадр обязан стоять на каждой границе"
    assert forced[-1] == pytest.approx(grid.start(grid.count - 1) - 0.02, abs=0.001)


def test_full_recode_packing_skips_the_pilot_run(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """У перекодирующего прогона докатки нет: ``-ss`` точен, пробный прогон вреден.

    Вреден дважды: измеренное место старта увело бы весь прогон на сегмент назад (эта
    грабля стоила отладки ещё кодировщику), а сам он стоит 0.5-1.7 с пути старта — тех
    самых, которыми сплошной перекод оплачивает свою голову.
    """
    from torrcast import stream

    grid = _grid()
    seen: list[list[str]] = []

    def _pilot(*a: object, **k: object) -> float:
        raise AssertionError("пробный прогон при сплошном перекоде звать нельзя")

    def _remember(cls: object, command: list[str], /, *a: object, **k: object) -> Packer:
        seen.append(command)
        return fake_packer(tmp_path)

    monkeypatch.setattr(stream, "pack_start", _pilot)
    monkeypatch.setattr(stream.Packer, "start", classmethod(_remember))
    feed = stream.Feed(
        source="src", audio=0, out=tmp_path, grid=grid, encode=Encode(preset=FULL_PRESET)
    )
    feed.restart(5)

    command = seen[0]
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-segment_start_number") + 1] == "5", "докатки нет"
    assert command[command.index("-ss") + 1] == f"{grid.start(5):.3f}"


def test_a_light_source_is_not_blown_up_to_the_ceiling() -> None:
    """Битрейт сплошного перекода считается от источника, а потолок остаётся потолком.

    🔴 Замер на живом Q70D (TC-29, «Bocchi the Rock» — 1.3 Мбит/с HEVC, 0.2 ГБ на 23
    минуты): перекод «в 9 Мбит/с» раздул аниме всемеро и положил в сегменты 18.3 и
    21.4 МБ при потолке 16 и замеренной границе срыва 19.4 — то есть сплошной перекод
    сам себе сделал ровно тот тяжёлый кусок, ради которого всё это затевалось.
    """
    from torrcast.cli import _encode_all
    from torrcast.recode import FULL_FLOOR, FULL_GAIN
    from torrcast.state import Config

    config = Config(recode=True, recode_mbit=9.0)
    light = _encode_all(config, "hevc", 1.28)
    assert light is not None and light.mbit == pytest.approx(1.28 * FULL_GAIN)
    heavy = _encode_all(config, "hevc", 12.0)
    assert heavy is not None and heavy.mbit == 9.0, "потолок перекодирования не сдвинулся"
    thin = _encode_all(config, "hevc", 0.4)
    assert thin is not None and thin.mbit == FULL_FLOOR, "ниже пола 1080p разваливается"
    blind = _encode_all(config, "hevc", 0.0)
    assert blind is not None and blind.mbit == 9.0, "паспорт молчит - идём по потолку"


def test_a_frame_above_the_receivers_ceiling_is_scaled_down_instead_of_refused() -> None:
    """🔴 TC-222: 2160p едет сплошным перекодом вниз до 1080p - и говорит об этом вслух.

    Замер TC-157 на 4 vCPU: тот же ``ultrafast`` без скейла идёт 1.03x реального времени,
    со скейлом до 1080p - 1.53x. То есть скейл не «ещё одна нагрузка», а разгрузка: x264
    получает вчетверо меньше пикселей. Поэтому «нет 1080p» перестало значить «показа нет».
    """
    from torrcast.cli import _encode_all
    from torrcast.profile import CAUTIOUS
    from torrcast.state import Config
    from torrcast.stream import recode_note

    whole = _encode_all(Config(), "hevc", 20.0, 10, CAUTIOUS, frame=2160)
    assert whole is not None and whole.scaled, "4К обязано ужиматься, а не ехать как есть"
    assert whole.out_frame == RECODE_HEIGHT == CAUTIOUS.recode_frame
    args = whole.args(_grid(), 0, 2)
    assert "-vf" in args, "без фильтра перекод сменил бы кодек, но не кадр"
    chain = args[args.index("-vf") + 1]
    # Габарит, а не одна высота: скоуп 3840x1600 - это тоже 2160p, и ``-2:1080`` развернул
    # бы его в 2592x1080 - кадр шире 1080p, то есть ровно то, чего приёмник не берёт.
    assert chain.startswith("scale=w=min(iw\\,1920):h=min(ih\\,1080)")
    assert "force_original_aspect_ratio=decrease" in chain

    # ...и человек, выбравший 4К-раздачу, читает это строкой, а не догадывается по чёткости.
    assert recode_note("hevc 10 бит", 0.0, 2160, whole.out_frame) == (
        "видео hevc 10 бит - перекодирую на ходу целиком, 2160p - играю в 1080p"
    )
    # На 1080p не поменялось ничего: ни фильтра, ни строки.
    same = _encode_all(Config(), "hevc", 20.0, 10, CAUTIOUS, frame=1080)
    assert same is not None and not same.scaled and "-vf" not in same.args(_grid(), 0, 2)
    assert recode_note("hevc 10 бит") == "видео hevc 10 бит - перекодирую на ходу целиком"


def test_the_level_in_the_stream_matches_the_frame_that_actually_leaves() -> None:
    """🔴 TC-224: уровень считается от кадра, а не пишется строкой.

    Уровень - обещание декодеру «кадр не больше такого-то», и меряется оно в макроблоках
    16x16. У 4.1 их 8192: 1080p (120x68 = 8160) влезает, 2160p (240x135 = 32400) больше
    вчетверо. Прибитая строка «4.1» на 4К-кадре была прямым враньём в поток и держалась
    ровно на том, что 4К до кодировщика не доходило.
    """
    from torrcast.profile import CAUTIOUS

    assert level_for(1080) == "4.1", "1080p влезает в 4.1 - на нём не меняется ничего"
    assert level_for(720) == "4.1", "ниже 4.1 не опускаемся: уровень потолок, а не заявка"
    assert level_for(0) == "4.1", "кадра не спрашивали - прежнее поведение"
    assert level_for(2160) == "5.1", "32400 макроблоков - это уже 5.1, и врать тут нечем"

    # Верно по построению, а не по совпадению: наружу уходит ужатый кадр, и уровень
    # считается от него же. Приёмник с другим потолком получит свой честный уровень.
    scaled = Encode(preset=FULL_PRESET, mbit=9.0, frame=2160, ceiling=CAUTIOUS.recode_frame)
    assert "4.1" in scaled.args(_grid(), 0, 2), "ужали до 1080p - 4.1 стал честным"
    huge = Encode(preset=FULL_PRESET, mbit=9.0, frame=2160, ceiling=2160)
    assert not huge.scaled and "5.1" in huge.args(_grid(), 0, 2), "не ужали - назвали как есть"


def test_the_tonemap_is_a_conversion_not_a_relabel_and_it_is_measured() -> None:
    """🔴 TC-223: метки BT.709 ставятся ТОЛЬКО вместе с преобразованием цвета.

    Пометить кадр в PQ как BT.709, не преобразовав его, - переклеенный ярлык: приёмник
    развернёт яркость не той кривой, и картинка поедет тусклой. Поэтому метки и цепочка
    ходят парой: есть тонемап - есть метки, нет тонемапа - уезжают СВОИ метки источника,
    какие и уезжали до этой правки.

    Цена замерена (09-08-2026, 4 vCPU, «Матрица» 2160p HDR10, тяжёлое место 93 с,
    ``ultrafast`` 9 Мбит/с): один скейл до 1080p - 1.34-1.41x реального времени, скейл с
    тонемапом - 1.00x, тонемап до скейла (на 4К) - 0.37x. Запас съеден целиком, поэтому
    настройка по умолчанию выключена, а порядок в цепочке - скейл первым.
    """
    from torrcast.recode import TONEMAP
    from torrcast.state import Config

    assert not Config().recode_tonemap, "по умолчанию выключен: 1.00x - это ноль запаса"

    plain = Encode(preset=FULL_PRESET, mbit=9.0, frame=2160, ceiling=1080)
    assert "-color_primaries" not in plain.args(_grid(), 0, 2), "нет тонемапа - нет и меток"

    colored = Encode(preset=FULL_PRESET, mbit=9.0, frame=2160, ceiling=1080, hdr=True)
    args = colored.args(_grid(), 0, 2)
    chain = args[args.index("-vf") + 1]
    assert TONEMAP in chain, "метка без преобразования - переклеенный ярлык"
    assert chain.index("scale=") < chain.index(TONEMAP), "тонемап работает уже на 1080p"
    assert [args[args.index(k) + 1] for k in ("-color_primaries", "-color_trc", "-colorspace")] == [
        "bt709"
    ] * 3


def test_the_grid_weighs_a_fully_recoded_file_by_our_bitrate_not_the_source() -> None:
    """Сетка обязана резать по тому, что уедет на ТВ, а уедет наш перекод.

    Тот же замер: карта лёгкого HEVC разрешала куски по 15-20 с, потому что в файле они
    и правда лёгкие. После перекода вес куска задаём мы, и сетка обязана знать об этом
    ДО первого сегмента — иначе потолок 16 МБ не сработает ни разу.
    """
    from torrcast.stream import MAX_SEGMENT_BYTES

    keys = _keys(duration=300.0, gop=7.0, rate=0.16e6)  # 1.3 Мбит/с - лёгкое аниме
    naive = Grid.on_keyframes(keys.at, 300.0, 10.0, sizes=keys.offset, ceiling_mbit=9.0)
    fixed = Grid.on_keyframes(keys.at, 300.0, 10.0, sizes=keys.offset, fixed_mbit=9.4)

    assert max(naive.span(k) for k in range(naive.count)) > 13.0, "карта разрешает длинные"
    worst = max(fixed.span(k) * 9.4e6 / 8 for k in range(fixed.count))
    assert worst <= MAX_SEGMENT_BYTES, "перекодированный кусок обязан влезать в потолок"


def test_a_scaled_down_4k_show_gets_its_grid_weighed_by_our_bitrate_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-222: у ужатого 4К сетка считается по НАШИМ 9 Мбит/с, а не по карте исходника.

    Ловушка тут своя, и она новая: раньше 4К до сетки не доходило вовсе. 2160p на
    4 Мбит/с - для карты файл лёгкий, она разрешает куски по 17 с; а уедет в них наш
    перекод на 9 Мбит/с, то есть 20 МБ при потолке приёмника 16. Сплошной перекод сам
    себе делает тот тяжёлый кусок, ради которого он и заведён.

    Сетка тут строится настоящая - той же :func:`torrcast.cli._layout`, что и на показе;
    подменена только карта опорных кадров, чтобы не ходить в рой.
    """
    from torrcast.cli import _layout
    from torrcast.profile import CAUTIOUS
    from torrcast.state import Config
    from torrcast.stream import AUDIO_MBIT, TS_OVERHEAD

    keys = _keys(duration=595.0, gop=8.5, rate=0.5e6)  # 4 Мбит/с - для карты это лёгкий файл
    monkeypatch.setattr("torrcast.stream.film_keys", lambda url: keys)

    grid, whole = _layout(Config(), "http://ts/x", 595.0, "h264", 4.0, depth=8, frame=2160)
    assert whole is not None and whole.mbit == 9.0, "4К поехало сплошным перекодом"
    ours = (whole.mbit + AUDIO_MBIT) * TS_OVERHEAD
    # Хвост сетки в счёт не идёт: он по правилу такой, какой остался, и потолок веса на
    # него не распространялся никогда - это не про 4К и не про эту правку.
    worst = max(grid.span(k) * ours * 1e6 / 8 for k in range(grid.count - 1))
    assert worst <= CAUTIOUS.max_segment_bytes, "кусок обязан влезать в потолок приёмника"

    # А по карте исходника та же сетка разрешила бы куски, в которые наш перекод не влез бы.
    naive = Grid.on_keyframes(keys.at, 595.0, Config().hls_segment, sizes=keys.offset)
    assert max(naive.span(k) * ours * 1e6 / 8 for k in range(naive.count - 1)) > 20e6


# ------------------------------------------------------------- фактическая скорость


def test_the_deadline_keeps_half_the_slack_in_reserve() -> None:
    """Кусок, который по табличке ложится в срок «впритык», пресетом получше не идёт.

    Улика, ради которой запас поднят: в журнале показа ``veryfast`` шёл 1.00-1.30x при
    табличных 1.40, и кусок, посчитанный успевающим, приезжал поздно. Замер разброса -
    тот же кусок тем же пресетом идёт 2.62x в одиночку и 1.84x рядом с прогревом: решение,
    принятое на пустой машине, обесценивается в 1.43 раза, если сосед проснулся после него.
    """
    assert DEADLINE_MARGIN <= 0.5, "запас по сроку меньше половины - соседа он не держит"
    seconds = 60.0
    table = ((PRESETS[0][0], 1.0), (PRESETS[-1][0], 10.0))
    # Ровно столько, сколько кодировать: старая арифметика (0.7 срока) сказала бы «успею».
    assert preset_for(seconds, slack=seconds * 0.9, presets=table) == PRESETS[-1][0]
    assert preset_for(seconds, slack=seconds * 2.5, presets=table) == PRESETS[0][0]


def test_before_the_first_run_the_pace_plans_as_if_a_neighbour_is_working() -> None:
    """Прогрев поднимается через 45 с после старта показа и живёт весь фильм, так что
    «соседа нет» - это не про показ, а про стенд, где снимали таблицу."""
    pace = Pace()
    assert pace.seen == 0
    assert pace.plan == NEIGHBOUR_TOLL < 1.0, "первый заход планируется по чистой табличке"
    assert pace.table()[0][1] == pytest.approx(PRESETS[0][1] * NEIGHBOUR_TOLL)
    assert pace.speed(PRESETS[1][0]) == pytest.approx(PRESETS[1][1] * NEIGHBOUR_TOLL)
    assert pace.speed("такого пресета нет") == pace.table()[-1][1]


def test_a_slow_run_drags_the_whole_ladder_down_not_just_its_own_preset() -> None:
    """Замер соседа: прогрев роняет veryfast, superfast и ultrafast на одни и те же 30 %.
    Потеря множительная, поэтому один заход уточняет срок для ВСЕХ пресетов - в том числе
    тех, которыми на этом показе ещё не ходили."""
    pace = Pace()
    # Заход средним пресетом вышел вдвое медленнее таблички.
    got = pace.record(PRESETS[1][0], seconds=100.0, spent=100.0 / (PRESETS[1][1] / 2))
    assert got == pytest.approx(0.5)
    assert pace.plan == pytest.approx(0.5), "первый замер не лёг в план целиком"
    for (name, table), (same, planned) in zip(PRESETS, pace.table(), strict=True):
        assert name == same
        assert planned == pytest.approx(table * 0.5)


def test_a_fast_machine_earns_back_the_quality_the_table_forbids() -> None:
    """Промах таблицы в другую сторону не безобиднее: на лёгком материале тот же veryfast
    идёт 2.62x, и по прибитым числам показ отказывался бы от качества, которое успевает."""
    pace = Pace()
    seconds, slack = 60.0, 60.0
    assert preset_for(seconds, slack, pace.table()) == PRESETS[-1][0]
    for _ in range(3):
        pace.record(PRESETS[-1][0], seconds=100.0, spent=100.0 / (PRESETS[-1][1] * 2.0))
    assert pace.plan > 1.0
    assert preset_for(seconds, slack, pace.table()) == PRESETS[0][0]


def test_the_plan_takes_the_worst_recent_run_not_the_average() -> None:
    """Сосед просыпается и засыпает, и среднее по такому ряду - скорость, которой не было
    ни разу. Планируем по худшему из недавних: промах в эту сторону стоит подгруза."""
    pace = Pace()
    pace.record(PRESETS[0][0], seconds=100.0, spent=100.0 / (PRESETS[0][1] * 2.0))
    pace.record(PRESETS[0][0], seconds=100.0, spent=100.0 / (PRESETS[0][1] * 0.5))
    assert pace.factor > 0.5, "среднее не поднялось - проверять нечего"
    assert pace.plan == pytest.approx(0.5), "план взял среднее, а не худший заход"


def test_a_run_that_gave_nothing_is_not_a_speed_measurement() -> None:
    """Заход, брошенный перемоткой или сорвавшийся, мерит помеху, а не скорость."""
    pace = Pace()
    for bad in ((0.0, 10.0), (10.0, 0.0), (-1.0, 10.0)):
        assert pace.record(PRESETS[0][0], *bad) == NEIGHBOUR_TOLL
    assert pace.record("не наш пресет", 10.0, 1.0) == NEIGHBOUR_TOLL
    assert pace.seen == 0, "негодный заход попал в замер"


def test_the_recoder_plans_by_the_measured_pace_not_by_the_table(tmp_path: Path) -> None:
    """Сквозь кодировщик: тот же кусок, тот же срок, а пресет разный - потому что на этой
    машине с этими соседями замерена другая скорость."""
    grid = _grid()
    keys = _keys()
    weights = Weights.of(keys, grid)
    assert weights is not None
    recoder = Recoder(
        source="s",
        audio=0,
        grid=grid,
        spare=tmp_path,
        weights=weights,
    )
    idle = recoder.working
    recoder.job = (0, 0, 0.0, 0.0, 1.0)
    assert (idle, recoder.working) == (False, True), "прогреву не по чему уступать кодировщику"

    quick = recoder.pace.table()[-1][1]
    recoder.pace.record(PRESETS[-1][0], seconds=100.0, spent=100.0 / (PRESETS[-1][1] / 4))
    assert recoder.pace.table()[-1][1] < quick, "замер не дошёл до кодировщика"
