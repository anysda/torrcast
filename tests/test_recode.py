"""Динамический битрейт (§6.2): профиль тяжести, выбор пресета, стык копии с перекодом."""

from __future__ import annotations

import subprocess

import pytest

from torrcast.recode import PRESETS, Encode, Recoder, Weights, preset_for
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
    """Кратковременное снижение качества владелец разрешил, подгруз — нет (§6.2)."""
    assert preset_for(seconds=60.0, slack=20.0) == PRESETS[-1][0]
    assert preset_for(seconds=60.0, slack=0.0) == PRESETS[-1][0]


def test_the_preset_ladder_is_walked_from_slow_to_fast() -> None:
    """Между «успевает медленный» и «не успевает никто» стоит средний, а не пропасть."""
    seconds = 60.0
    slack = seconds / PRESETS[1][1] / 0.7 + 0.1
    assert preset_for(seconds, slack) == PRESETS[1][0]


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
    """Без ``encode`` команда та же, что была до §6.2, — регресса нарезки быть не может."""
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
    """Тот же кодек и то же разрешение — иначе приёмник заметит стык (§6.2)."""
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
    assert recoder._pick() is None  # всё, что ближе 30 с, уже сделано; дальше — не лезем


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
    weights = Weights.of(_keys(rate=0.5e6), grid)  # 4 Мбит/с — приёмник и не заметит
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
        # кадр раньше, §6.0), у перекода — не измеряется вовсе: там ``-ss`` точен.
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
        # Метка начала совпадает с копией с точностью до кадра, и кадр этот — опорный.
        assert abs(began - copied[number][0]) < 0.1, f"v{number}: метки разъехались"
        assert abs(ended - copied[number][1]) < 0.1, f"v{number}: длина разъехалась"
        assert keyed, f"v{number}: первый кадр не опорный — независимость сегмента враньё"


def test_the_deadline_is_the_packer_not_the_playhead(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Наружу сегмент выкладывает упаковщик, и он идёт впереди показа на ``burst``.

    Считай кодировщик срок по месту показа — и на старте, пока упаковщик разом выложил
    минуту вперёд, тяжёлые куски уходили бы копией. Ровно это и было в первом живом
    прогоне (§6.2): v361 и v362 на 26 и 28 Мбит/с.
    """
    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.played = 0.0
    assert recoder.slack(5) == pytest.approx(grid.start(5), abs=0.1)
    recoder.note(4, recoded=False)  # упаковщик выложил уже пять сегментов
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
    recoder.note(3, recoded=False)  # упаковщик выложил v0…v3
    job = recoder._pick()
    assert job is not None
    assert job[0] == 4


def test_a_run_never_promises_more_than_it_can_deliver_in_time(  # type: ignore[no-untyped-def]
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Длинный заход сам себе создаёт опоздание — он обрывается на первом несрочном куске.

    На стенде эта защита почти не срабатывает (даже ``ultrafast`` идёт вчетверо быстрее
    реального времени), поэтому здесь кодировщику назначается медленная машина.
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
    recoder.note(3, recoded=False)
    job = recoder._pick()
    assert job is not None
    assert job[0] == 4
    assert job[1] < 4 + recoder.run_max - 1  # до конца заход не растянулся


def test_a_copy_waits_while_its_piece_is_being_recoded(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Упаковщик на старте прогона выкладывает минуту разом и обгонял кодировщик.

    Найдено живым прогоном (§6.2): v361 и v362 «Моаны 2» (26 и 28 Мбит/с) уходили копией
    просто потому, что упаковщик успел раньше. Копия теперь ждёт — но только там, докуда
    показу далеко.
    """
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.played = 0.0
    recoder.began = clock.monotonic() - 100.0  # фора на подъём давно вышла
    assert recoder.holding(5)  # заход не идёт, но следующим возьмут ровно этот кусок
    recoder.job = (4, 8, clock.monotonic() + 60.0, clock.monotonic(), 4.0)
    assert recoder.holding(5)
    assert recoder.holding(9)  # следующий заход возьмёт и его — успевается
    assert not recoder.holding(20)  # а так далеко у кодировщика планов ещё нет


def test_a_piece_right_under_the_playhead_is_never_held_back(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Ожидание под носом у показа — это и есть подгруз, а он запрещён (§6.2)."""
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
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
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
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
    packer.hold = lambda slot: slot == 1
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
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
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
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.played = 0.0
    recoder.began = clock.monotonic()
    assert recoder.job is None
    assert recoder.holding(5)  # тяжёлый и далеко — подождём подъёма
    assert not recoder.holding(0)  # упаковку с него не начинали — это не голова прогона
    recoder.played = grid.start(5) - 3.0  # показ почти дошёл — подъём уже не успеет
    assert not recoder.holding(5)


# ------------------------------------------------------- первый сегмент показа (голова)


def test_the_very_first_segment_of_a_run_is_waited_for(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Голова прогона — единственный кусок, который держат прямо под носом у показа.

    Картинки в этот момент нет ни одного кадра, ждать тут значит стартовать, а не
    подгружаться. Уйди голова копией — приёмник встаёт на первой же секунде показа в
    тяжёлом месте (§6.2, 🔴 «первый сегмент уходит как есть»).
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
    weights = Weights.of(_keys(rate=0.5e6), grid)  # 4 Мбит/с — тяжёлого нет вовсе
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
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.opening(7)
    recoder.head_at = clock.monotonic() - recoder.head_wait - 0.1
    assert not recoder.holding(7)


def test_waiting_for_the_head_can_be_switched_off(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """``recode_head_wait = 0`` возвращает поведение до 06-08 вечера — на случай отката."""
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
        recoder.note(slot, recoded=False)
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
    monkeypatch.setattr(stream, "pack_start", lambda *a, **k: (seen.append(("проба", 0)), 0.0)[1])
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
    monkeypatch.setattr(
        stream.Packer,
        "start",
        classmethod(lambda cls, command, *a, **k: (seen.append(command), fake_packer(tmp_path))[1]),
    )
    recoder.opening(3)
    recoder.stopped = True  # один круг: ждать реального ffmpeg тут нечего
    recoder._run(3, 3)
    recoder._run(9, 11)
    assert seen[0][:3] == ["nice", "-n", "0"]
    assert seen[1][:3] == ["nice", "-n", "15"]


def test_a_run_is_counted_by_what_it_published_not_by_what_is_left(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Готовый кусок из каталога уже мог забрать показ — глоб объявлял бы заход провальным.

    Ровно так «перекодировал v0» печаталось как «не дало ни куска за 7 с» (§6.2, 🟡).
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

    Замер на стенде: заход за ``v0`` (7 с) съедал ровно столько же от ожидания ``v358``,
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
    recoder.opening(3)  # перемотали НАЗАД — голова теперь позади захода
    recoder._run(12, 14)
    assert packer.stopped == "голова прогона важнее"


def test_the_pieces_right_after_the_current_run_are_held_too(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Заход за головой берёт ОДИН кусок — а упаковщик за эти секунды выкладывает три.

    Найдено живым Q70D 06-08 вечером: голова `v358` ушла перекодом, а `v359`…`v361`
    (21–26 Мбит/с) — копией, потому что «не наш заход» означало «не держим». Показ упал
    в BUFFERING на 27 опросах из 43.
    """
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.opening(4)
    recoder.job = (4, 4, clock.monotonic() + 60.0, clock.monotonic(), PRESETS[-1][1])
    assert recoder.holding(5)  # следующий за головой — успеется, держим
    assert recoder.holding(6)
    assert not recoder.holding(25)  # а так далеко у кодировщика планов ещё нет


def test_a_piece_after_the_run_is_not_held_if_the_playhead_is_closer(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Считаем по сроку и за пределами захода: не успеть — значит не держать."""
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.played = grid.start(4)
    recoder.job = (4, 4, clock.monotonic() + 600.0, clock.monotonic(), 0.05)  # еле ползёт
    assert not recoder.holding(5)


def test_between_runs_the_copy_still_waits(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Дыра между заходами — это секунды, и в них уходило самое тяжёлое.

    Живой Q70D 06-08 вечером: заход за головой шёл 8 с при форе 6 с, и ровно в этот
    зазор ушёл копией `v359` на 26 Мбит/с («заход не идёт» в журнале).
    """
    import time as clock

    grid = _grid()
    weights = Weights.of(_keys(rate=2.0e6), grid)
    assert weights is not None
    recoder = Recoder(
        source="src", audio=0, grid=grid, spare=tmp_path, weights=weights, threshold=15.0
    )
    recoder.began = clock.monotonic() - 100.0  # фора на подъём давно вышла
    recoder.played = grid.start(5) - 5.0
    assert recoder.job is None
    assert recoder.holding(6)  # до него полтора десятка секунд — следующий заход успеет
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
    recoder.note(3, recoded=False)  # кусок далеко позади показа
    assert recoder.late == 0
    recoder.note(21, recoded=False)
    assert recoder.late == 1


def test_the_tail_of_a_run_is_dropped_and_never_published(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Огрызок за ``-to`` наружу не уезжает — ни от кодировщика, ни от упаковщика.

    Заход кодировщика ограничен ``-to`` с запасом в секунду, и муксер успевает открыть
    следующий файл: в нём секунда фильма вместо десяти. Живой Q70D 06-08-2026, «Тачки 3»:
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
    assert not (run / segment_name(4)).exists()  # докатка — как и была
