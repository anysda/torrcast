"""Формат потока, сетка сегментов и раздача HLS: то, на чём ресивер молча ломается.

Проверяется ровно то, что телевизоры прощать отказываются: TS-сегменты по сетке
:class:`~torrcast.stream.Grid`, один вариант, видео copy, аудио всегда AAC stereo 192k,
VOD-манифест на весь фильм, CORS на всех ответах (включая 404 и preflight) и Range на
сегментах.

Отдельная тема здесь — **абсолютность** сетки. Раньше ffmpeg резал каждые N секунд от
первого пакета своего прогона, то есть имя сегмента значило разное место фильма в
зависимости от того, откуда начали паковать. Теперь граница — это число от нуля фильма, и
почти все тесты ниже про то, что это число одно и то же в манифесте и в команде ffmpeg.

Раздача идёт по http на голом IP — так же, как её видит телевизор.
https проверяется отдельно: это выключенная опция, но она обязана оставаться рабочей.
"""

from __future__ import annotations

import json
import math
import subprocess
import time
from pathlib import Path
from typing import IO, Any

import pytest
import requests

from tests.conftest import CLIP_SECONDS, fake_packer, free_port
from torrcast import stream
from torrcast.cast import Report
from torrcast.keymap import Reader, keyframes, video_track
from torrcast.stream import (
    HLS_SEGMENT_SECONDS,
    MAX_SEGMENT_BYTES,
    MPEGTS_MUX_DELAY,
    PACK_DIR,
    PACK_LIST,
    SPLIT_SLACK,
    Feed,
    FilmKeys,
    Grid,
    HlsServer,
    Packer,
    ffmpeg_pack_command,
    hls_dir,
    mapped_start,
    pack_start,
    parse_manifest,
    segment_name,
)

#: Ровная сетка на два часа: примерно столько и играет полнометражный фильм.
FILM = 7200.0


def _keyframes(duration: float = 600.0, gop: float = 2.08) -> list[float]:
    """Карта опорных кадров «как в жизни»: GOP около двух секунд и сцена-вспышка.

    Вспышка (два десятка опорных кадров за полсекунды) тут не для красоты: именно на ней
    видно, что сетка не рассыпается на огрызки, — :meth:`Grid.on_keyframes` обязана взять
    из этой пачки ровно один кадр.
    """
    keys = [round(k * gop, 3) for k in range(int(duration / gop) + 1)]
    keys += [300.0 + n * 0.02 for n in range(24)]
    return sorted(k for k in keys if k < duration)


def _flag(command: list[str], name: str) -> str:
    """Значение ключа командной строки ffmpeg."""
    return command[command.index(name) + 1]


def _boundaries(command: list[str], at: float) -> dict[int, float]:
    """Что команда обещает нарезать: ``{номер файла: секунда фильма}``.

    Сегментный муксер сравнивает метки с началом своего прогона, поэтому границы лежат в
    команде смещёнными на ``at``; здесь они возвращаются в абсолютное время фильма. Первый
    файл прогона начинается на ``at``, каждый следующий — на своей границе из
    ``-segment_times``.
    """
    first = int(_flag(command, "-segment_start_number"))
    found = {first: at}
    for step, raw in enumerate(_flag(command, "-segment_times").split(",")):
        found[first + step + 1] = at + float(raw)
    return found


@pytest.fixture
def served(tmp_path: Path) -> Any:
    """Живая раздача с одним готовым сегментом — по http, как её берёт ТВ."""
    root, feed = _stub(tmp_path)
    port = free_port()
    server = HlsServer(root, host="127.0.0.1", port=port, feed=feed)
    server.start()
    try:
        yield requests.Session(), f"http://127.0.0.1:{port}"
    finally:
        server.stop()


def _stub(tmp_path: Path) -> tuple[Path, Feed]:
    """Каталог с готовым сегментом ``v0.ts`` и раздача поверх него.

    Упаковки за этой раздачей нет: все тесты ниже спрашивают только то, что уже лежит,
    и ffmpeg тут запускать не за чем.
    """
    root = hls_dir(str(tmp_path / "hls"))
    (root / "v0.ts").write_bytes(bytes(range(256)) * 4)
    return root, Feed(source="", audio=0, out=root, grid=Grid.uniform(20.0), wait=0.0)


def test_the_default_transport_is_plain_http_by_ip(tmp_path: Path) -> None:
    """Раздача по умолчанию — http, и ни серта, ни имени ей не нужно.

    Сервер поднимается **без единого пути к серту** — то есть выключенный https не
    оставляет по себе обязательного файла, который некому положить.
    """
    from torrcast.state import Config

    assert Config().transport == "http"
    assert Config().hls_base_url == "", "имя в базе URL = DNS в пути показа"
    assert Config().hls_port == 8080

    root, feed = _stub(tmp_path)
    port = free_port()
    server = HlsServer(root, host="127.0.0.1", port=port, feed=feed)
    server.start()
    try:
        answer = requests.get(f"http://127.0.0.1:{port}/index.m3u8", timeout=10)
        assert answer.status_code == 200
        assert answer.headers["Access-Control-Allow-Origin"] == "*"
        assert answer.headers["Content-Type"] == "application/vnd.apple.mpegurl"
    finally:
        server.stop()


def test_https_stays_a_working_but_switched_off_option(
    tls: tuple[str, str], tmp_path: Path
) -> None:
    """Код https никуда не делся: включается флагом и играет как раньше."""
    root, feed = _stub(tmp_path)
    port = free_port()
    server = HlsServer(root, tls[0], tls[1], host="127.0.0.1", port=port, tls=True, feed=feed)
    server.start()
    session = requests.Session()
    session.verify = tls[0]  # серт = собственный корень: TLS проверяется по-настоящему
    try:
        answer = session.get(f"https://127.0.0.1:{port}/index.m3u8", timeout=10)
        assert answer.status_code == 200
        assert answer.headers["Access-Control-Allow-Origin"] == "*"
    finally:
        server.stop()


def test_the_playback_address_is_our_own_leg_toward_the_tv(tmp_path: Path) -> None:
    """URL собирается из транспорта, нашего адреса со стороны ТВ и порта.

    Имени в нём нет вовсе — упавший DNS показ не трогает. Ручной ``hls_base_url``
    остаётся запасным выходом и перебивает вычисленный адрес.
    """
    from torrcast import InfraError
    from torrcast.state import Config
    from torrcast.stream import hls_base, our_address

    assert our_address("127.0.0.1") == "127.0.0.1", "адрес берём у ядра, по маршруту"
    assert our_address("") == ""

    assert hls_base(Config(tv="127.0.0.1")) == "http://127.0.0.1:8080"
    assert hls_base(Config(tv="127.0.0.1", transport="https")) == "https://127.0.0.1:8080"
    manual = Config(tv="127.0.0.1", hls_base_url="http://10.0.0.10:8080/")
    assert hls_base(manual) == "http://10.0.0.10:8080"
    with pytest.raises(InfraError):
        hls_base(Config())  # адрес ТВ не задан - маршрута нет, и молчать об этом нельзя


def test_a_segment_name_always_means_the_same_place_of_the_film() -> None:
    """``slot_at`` обратна ``start`` — на обеих сетках и в любой точке.

    Это и есть смысл абсолютной сетки: показ переводит секунду в номер, раздача переводит
    номер обратно в секунду, и оба получают одно и то же независимо от того, откуда начата
    упаковка. Раньше номер значил «сколько сегментов прошло с начала прогона», и после
    каждой перемотки одно и то же имя означало другое место фильма.
    """
    for grid in (Grid.uniform(FILM), Grid.on_keyframes(_keyframes(), 600.0)):
        for slot in range(grid.count):
            assert grid.slot_at(grid.start(slot)) == slot, f"начало {slot}"
            assert grid.slot_at(grid.start(slot) + grid.span(slot) / 2) == slot, f"середина {slot}"
            assert grid.start(slot) < grid.end(slot), f"пустой сегмент {slot}"
        assert grid.slot_at(-10.0) == 0, "до начала фильма - первый сегмент, а не отрицательный"
        assert grid.slot_at(grid.duration * 2) == grid.count - 1, "за концом - последний"
        assert grid.end(grid.count - 1) == grid.duration, "последний сегмент кончается фильмом"


def test_the_manifest_promises_the_whole_film_so_the_tv_has_a_timeline() -> None:
    """Длительность в MEDIA_STATUS = сумме ``EXTINF``, значит она обязана
    быть длиной фильма, а не длиной упакованного.

    Сумма сходится на обеих сетках: и на ровной, где хвост прилипает к последнему куску, и
    на сетке по опорным кадрам, где сегменты разной длины. С ``ENDLIST`` приёмник считает
    манифест VOD — со шкалой, общим временем и перемоткой в любую точку (проверено на
    живом Q70D).
    """
    for grid in (Grid.uniform(5978.5), Grid.on_keyframes(_keyframes(), 600.0)):
        text = grid.manifest()
        segments, ended = parse_manifest(text)
        assert ended, "без ENDLIST для приёмника это эфир: ни шкалы, ни перемотки"
        assert "#EXT-X-PLAYLIST-TYPE:VOD" in text
        assert abs(sum(seconds for _, seconds in segments) - grid.duration) < 0.001
        assert len(segments) == grid.count
        assert segments[0][0] == "v0.ts" and segments[-1][0] == f"v{grid.count - 1}.ts"

    # Ровная сетка на целое число шагов - это ровно столько же сегментов, без хвоста.
    step = float(HLS_SEGMENT_SECONDS)
    whole = Grid.uniform(step * 5)
    assert parse_manifest(whole.manifest())[0] == [(f"v{n}.ts", step) for n in range(5)]
    assert Grid.uniform(5978.5).count == int(5978.5 // step) + 1, "целые куски и хвост"


def test_a_keyframe_grid_never_cuts_a_segment_shorter_than_the_step() -> None:
    """Следующая граница — первый опорный кадр не раньше, чем через шаг.

    Иначе на сцене-вспышке (два десятка опорных кадров за полсекунды) манифест распух бы
    на пустом месте, а приёмник получил бы очередь огрызков вместо сегментов. Хвост —
    единственное исключение: он прилипает к последнему куску, пока короче половины шага,
    поэтому последний сегмент бывает короче остальных, но не короче половины шага.
    """
    step = 10.0
    grid = Grid.on_keyframes(_keyframes(), 600.0, step)

    spans = [grid.span(k) for k in range(grid.count)]
    assert min(spans[:-1]) >= step, "сегмент короче шага - сетка рассыпалась на огрызки"
    assert spans[-1] >= step / 2, "хвост прилипает к последнему куску, а не висит огрызком"
    assert max(spans) < step + 3.0, "GOP около 2 с - длиннее шага плюс GOP сегмента не бывает"

    flash = [b for b in grid.bounds if 300.0 <= b < 300.5]
    assert len(flash) <= 1, "из пачки опорных кадров вспышки в сетку идёт не больше одного"


def test_the_target_duration_covers_the_longest_segment() -> None:
    """``EXT-X-TARGETDURATION`` меньше самого длинного сегмента = битый манифест.

    На ровной сетке это тавтология, а вот на сетке по опорным кадрам сегмент длиннее шага
    на остаток GOP (на «Моане 2» — до 21.5 с при шаге 10), и посчитать цель по шагу было
    бы враньём приёмнику.
    """
    for grid in (Grid.uniform(5978.5), Grid.on_keyframes(_keyframes(), 600.0), Grid.uniform(3.0)):
        longest = max(grid.span(k) for k in range(grid.count))
        assert grid.target() >= longest, "цель короче куска - приёмник вправе не успеть"
        assert grid.target() == max(1, math.ceil(longest)), "цель округляется вверх, и не в ноль"
        assert f"#EXT-X-TARGETDURATION:{grid.target()}" in grid.manifest()


def test_only_a_keyframe_grid_promises_independent_segments() -> None:
    """``EXT-X-INDEPENDENT-SEGMENTS`` — не украшение, а обещание, которое надо держать.

    На сетке по опорным кадрам каждый кусок начинается с ключевого кадра и декодируется
    сам по себе — на этом держится перемотка. На ровной сетке это неправда, и обещать
    приёмнику обратное значило бы врать.
    """
    keyed = Grid.on_keyframes(_keyframes(), 600.0)
    assert keyed.on_keys and "#EXT-X-INDEPENDENT-SEGMENTS" in keyed.manifest()
    flat = Grid.uniform(600.0)
    assert not flat.on_keys and "#EXT-X-INDEPENDENT-SEGMENTS" not in flat.manifest()


def test_stream_format_is_fixed_and_not_negotiable() -> None:
    """Один вариант, видео copy, звук всегда AAC stereo 192k, куски — MPEG-TS.

    Пишет ffmpeg в каталог прогона (:data:`PACK_DIR`), а не сразу наружу: «файл появился»
    у сегментного муксера не значит «кусок дописан» (:meth:`Packer.publish`).
    """
    grid = Grid.uniform(100.0)
    command = ffmpeg_pack_command("http://ts/stream", 1, "/dev/shm/torrcast/pack", grid, 0, 0.0)
    text = " ".join(command)
    assert "-c:v copy" in text, "видео только copy - перекодировать 1080p нам нечем"
    assert "-c:a aac -ac 2 -b:a 192k" in text, "AC3/DTS passthrough запрещён"
    assert "-map 0:v:0 -map 0:a:1" in text, "один вариант и выбранная дорожка по индексу"
    assert "-f segment -segment_format mpegts" in text, "сетку задаёт список, а не один шаг"
    assert command[-1] == "/dev/shm/torrcast/pack/v%d.ts", "имя = место в фильме"
    assert f"-segment_list /dev/shm/torrcast/pack/{PACK_LIST}" in text, "чем сверять факт"
    assert "-copyts" in text, "метки времени - абсолютные, иначе позиция считается от куска"


def test_mpegts_muxer_does_not_shove_its_own_delay_into_the_timestamps() -> None:
    """``-copyts`` без глушения муксера — это время фильма плюс 1.4 с.

    Мультиплексор mpegts по умолчанию сдвигает ВСЕ метки на ``muxdelay + muxpreload``
    (:data:`MPEGTS_MUX_DELAY`). :func:`pack_start` эти флаги ставил всегда, упаковка — нет,
    и на живых «Тачках 3» граница 3965.670 приезжала на ТВ кадром 3967.070. Ровно эти
    +1.400 с двое суток считали доказательством, что карта опорных кадров врёт о релизе.
    Замер после правки: первый кадр сегмента 3965.670, точно в карту.
    """
    grid = Grid.uniform(100.0)
    for at in (0.0, 48.7):
        text = " ".join(ffmpeg_pack_command("u", 0, "/run", grid, 5, at))
        assert "-muxdelay 0" in text and "-muxpreload 0" in text, "иначе метки уедут на 1.4 с"
    assert MPEGTS_MUX_DELAY == 1.4, "замерено на живом файле, а не взято из головы"


def test_a_new_packaging_run_does_not_turn_timestamps_back(
    clip_mp4_bframes: str, tmp_path: Path
) -> None:
    """Заход с нуля и перезаход обязаны писать одну ленту PTS/DTS.

    У H.264 с двумя-тремя B-кадрами первый DTS отрицательный. MPEG-TS по умолчанию
    прячет его и сдвигает весь прогон с нуля вперёд, а перезаход после ``-ss`` уже не
    сдвигает. На стыке получался обратный ход: в боевом тракте замерены 80 мс видео и
    44.6 мс звука. Проверяем настоящие отданные куски через ``ffprobe -show_packets``:
    не только соседей одного прогона, но и замену второго куска новым заходом.
    """
    found = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-skip_frame", "nokey",
         "-show_entries", "frame=pts_time", "-of", "csv=p=0", clip_mp4_bframes],
        check=True, capture_output=True, text=True, timeout=30,
    )  # fmt: skip
    keys = [float(line.strip().rstrip(",")) for line in found.stdout.splitlines() if line.strip()]
    grid = Grid.on_keyframes(keys, CLIP_SECONDS)

    def pack(name: str, slot: int) -> Path:
        run = tmp_path / name
        run.mkdir()
        at = 0.0 if slot == 0 else pack_start(clip_mp4_bframes, grid.start(slot))
        command = ffmpeg_pack_command(
            clip_mp4_bframes, 0, str(run), grid, slot, at, readrate=0.0, until=1
        )
        subprocess.run(command, check=True, capture_output=True, timeout=180)
        return run

    def first_dts(path: Path, stream_name: str) -> float:
        done = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", stream_name, "-show_packets",
             "-show_entries", "packet=dts_time,duration_time", "-of", "json", str(path)],
            check=True, capture_output=True, text=True, timeout=30,
        )  # fmt: skip
        packets = json.loads(done.stdout)["packets"]
        marks = [float(packet["dts_time"]) for packet in packets]
        assert marks, f"ffprobe не нашёл пакетов {stream_name} в {path.name}"
        return min(marks)

    head = pack("head", 0)
    restarted = pack("restarted", 1)
    for stream_name in ("v", "a"):
        clean_start = first_dts(head / "v1.ts", stream_name)
        restarted_start = first_dts(restarted / "v1.ts", stream_name)
        assert restarted_start >= clean_start - 0.001, (
            f"{stream_name}: перезаход сдвинул ленту назад на "
            f"{1000 * (clean_start - restarted_start):.3f} мс"
        )


def test_segment_numbers_mean_the_same_place_wherever_the_run_started() -> None:
    """Границы в ``-segment_times`` абсолютные — вот главная проверка.

    Один и тот же кусок фильма обязан получить один и тот же номер и при упаковке с нуля,
    и при упаковке с середины: именно на этом стоит манифест на весь фильм, перемотка и
    то, что уже упакованное после перезапуска не выбрасывается. Сравниваем не строки
    команды (они разные — муксер считает от начала прогона), а то, что из них следует:
    место каждого номера в фильме.
    """
    for grid in (Grid.uniform(100.0), Grid.on_keyframes(_keyframes(), 600.0)):
        middle = grid.count // 2
        # Прогон от нуля и прогон с середины, начавшийся раньше своей границы (докатка).
        head = _boundaries(ffmpeg_pack_command("u", 0, "/run", grid, 0, 0.0), 0.0)
        late = grid.start(middle) - 1.3
        tail = _boundaries(ffmpeg_pack_command("u", 0, "/run", grid, middle, late), late)

        for slot, second in head.items():
            assert abs(second - grid.start(slot)) < 0.001, f"прогон с нуля: {slot}"
        # Общие номера, кроме докатки: она под чужим номером и наружу не выйдет.
        for slot in (tail.keys() & head.keys()) - {middle - 1}:
            assert abs(tail[slot] - head[slot]) < 0.001, f"место {slot} разъехалось между прогонами"
        assert tail[middle - 1] == pytest.approx(late), "докатка стоит не на границе сетки"
        assert min(tail) == middle - 1, "докатка обязана быть ровно одна и до своего слота"
        assert max(head) == max(tail) == grid.count - 1, "оба прогона знают конец фильма"


def test_the_run_in_is_numbered_below_the_slot_and_only_when_it_is_one() -> None:
    """Номер первого файла прогона: слот минус один, если прогон начался раньше границы.

    ``-ss`` уводит ffmpeg на опорный кадр не позже запрошенного места (замерено: бывает и
    «через один»), и этот огрызок обязан лечь под чужим номером — чтобы
    :meth:`Packer.publish` его выбросил, а не отдал приёмнику как честный сегмент. Когда
    прогон встал ровно на границу, выбрасывать нечего и номер равен слоту.
    """
    grid = Grid.uniform(100.0)

    exact = ffmpeg_pack_command("u", 0, "/run", grid, 5, grid.start(5))
    assert _flag(exact, "-segment_start_number") == "5", "встали на границу - докатки нет"
    assert _flag(exact, "-ss") == "50.000" and exact.index("-ss") < exact.index("-i")

    near = ffmpeg_pack_command("u", 0, "/run", grid, 5, grid.start(5) - SPLIT_SLACK / 2)
    assert _flag(near, "-segment_start_number") == "5", "полкадра - это та же граница"

    behind = ffmpeg_pack_command("u", 0, "/run", grid, 5, 48.7)
    assert _flag(behind, "-segment_start_number") == "4", "докатка ложится под чужой номер"
    assert _flag(behind, "-ss") == "50.000", "просим всё равно своё место, а не место старта"

    head = ffmpeg_pack_command("u", 0, "/run", grid, 0, 0.0)
    assert _flag(head, "-segment_start_number") == "0"
    assert "-ss" not in head, "с начала фильма перематывать нечего"


def test_cutting_inside_a_gop_is_allowed_only_on_a_flat_grid() -> None:
    """``-break_non_keyframes`` — резать ли посреди GOP, и это решает сетка.

    На сетке по опорным кадрам резать посреди GOP не нужно и нельзя: муксер сам дождётся
    опорного кадра и встанет ровно туда, куда обещал манифест. На ровной сетке — наоборот,
    иначе куски разъедутся с манифестом тем сильнее, чем дальше от начала.
    """
    keyed = Grid.on_keyframes(_keyframes(), 600.0)
    assert _flag(ffmpeg_pack_command("u", 0, "/run", keyed, 0, 0.0), "-break_non_keyframes") == "0"
    flat = Grid.uniform(600.0)
    assert _flag(ffmpeg_pack_command("u", 0, "/run", flat, 0, 0.0), "-break_non_keyframes") == "1"


def test_a_space_in_the_run_directory_does_not_quietly_kill_the_packing(
    clip: str, tmp_path: Path
) -> None:
    """Пробел в пути каталога прогона: кусок доходит до показа, а не «ни куска».

    Хвост команды собирался f-строкой и разбивался по пробелам, поэтому путь с пробелом
    внутри приезжал к ffmpeg двумя огрызками: ``-segment_list`` получал половину имени,
    список нарезки не появлялся вовсе, а без него :meth:`Packer.publish` не выкладывает
    наружу ничего — наверх шло «упаковка не дала ни куска» без причины (проверено откатом:
    ровно этот тест на прежнем коде не находит ``v0.ts``). Каталог состояния задаёт человек
    (``TORRCAST_STATE``), пробелы в путях у людей обычное дело, поэтому проверка идёт
    настоящим прогоном ffmpeg, а не сравнением строк команды.
    """
    grid = Grid.uniform(float(CLIP_SECONDS))
    out = tmp_path / "мои фильмы"
    run = out / PACK_DIR
    run.mkdir(parents=True)
    command = ffmpeg_pack_command(clip, 0, str(run), grid, 0, 0.0, readrate=0.0, until=0)
    assert str(run / PACK_LIST) in command, "имя списка обязано доехать до ffmpeg целиком"
    packer = Packer.start(command, out, run, 0, last=0)
    deadline = time.monotonic() + 120
    while packer.poll() is None and time.monotonic() < deadline:
        packer.publish()
        time.sleep(0.2)
    packer.publish()
    packer.stop(keep_files=True, reason="проверка пути с пробелом")
    assert (out / segment_name(0)).exists(), f"ни куска: {packer.why()}"


# --- TC-122: точка захода упаковки берётся из карты, а не пробным прогоном каждый раз ---
# Перемотку демуксера ведёт тот самый индекс контейнера, из которого снята карта, поэтому
# место посадки ``-ss`` вычислимо (:func:`mapped_start`). Проверяется это не рассуждением, а
# настоящим ffmpeg: предсказание против измеренного, на mkv и на mp4.


@pytest.fixture
def offline_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Карта снимается с локального файла: Range-запросы читают путь, а не сеть."""

    def read(self: Reader, offset: int, size: int) -> bytes:
        data = Path(self.url).read_bytes()[offset : offset + size]
        self.taken += len(data)
        self.requests += 1
        return data

    monkeypatch.setattr(Reader, "read", read)


def _map_of(path: str) -> FilmKeys:
    """Карта файла в том виде, в каком её видит показ (:func:`torrcast.stream.film_keys`)."""
    found = keyframes(path)
    track = video_track(found.points)
    video = [p for p in found.points if p.track == track]
    return FilmKeys(found.duration, [p.at for p in video], [p.offset for p in video], found.kind)


@pytest.mark.parametrize("container", ["mkv", "mp4"])
def test_the_entry_point_from_the_map_is_where_ffmpeg_actually_lands(
    clip: str, clip_mp4: str, offline_keys: None, container: str
) -> None:
    """Предсказанное по карте место захода совпадает с измеренным - на каждой границе.

    Демуксер решает: mkv по ``-ss`` в опорный кадр уезжает на предыдущий («через один»),
    mp4 встаёт ровно в него. Поэтому проверяются оба контейнера и все границы подряд, а не
    одна: ошибка на один опорный кадр разъезжает с сеткой весь заход целиком.
    Щуп на .ts этот класс дефектов не воспроизвёл бы вовсе - у mpegts ``-ss`` уезжает
    ВПЕРЁД, и докатки у него не бывает.
    """
    path = clip if container == "mkv" else clip_mp4
    keys = _map_of(path)
    assert keys.kind == container, "тест обязан мерить тот контейнер, который назвал"
    for at in keys.at[2:12]:
        guess = mapped_start(keys, at)
        assert not math.isnan(guess), f"карта молчит про свою же границу {at:.3f}"
        measured = stream._pilot_start(path, at)
        assert guess == pytest.approx(measured, abs=SPLIT_SLACK), (
            f"{container}: карта обещает {guess:.3f} на границе {at:.3f}, а ffmpeg встал "
            f"на {measured:.3f}"
        )


def test_the_map_is_believed_only_after_the_pilot_has_confirmed_it(
    clip: str, offline_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пробный прогон - один на файл, а не один на заход, и он именно сверка.

    Первый заход платит прогон и сверяет им карту; дальше место захода считается по карте
    даром. Дёшево поверить карте сразу проект уже дважды не смог: резы захода муксер
    отмеряет от первого пакета, и заход, вставший не туда, кладёт мимо сетки весь участок.
    """
    monkeypatch.setattr(stream, "_SEEK_OK", {})
    keys = _map_of(clip)
    asked: list[float] = []
    honest = stream._pilot_start

    def counted(url: str, at: float, timeout: float = 0.0) -> float:
        asked.append(at)
        return honest(url, at)

    monkeypatch.setattr(stream, "_pilot_start", counted)
    first, second = keys.at[6], keys.at[9]
    assert pack_start(clip, first, keys=keys) == pytest.approx(mapped_start(keys, first))
    assert pack_start(clip, second, keys=keys) == pytest.approx(mapped_start(keys, second))
    assert asked == [first], f"пробных прогонов {len(asked)}, а карта сверяется один раз"
    assert stream._SEEK_OK[clip] is True


def test_a_lying_map_is_caught_by_the_pilot_and_never_believed_again(
    clip: str, offline_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Карта разошлась с фактом - работает прежний пробный прогон, и место захода верное.

    Подсунута карта, сдвинутая на 0.7 с: предсказание расходится с измеренным больше чем на
    полкадра. Показ обязан этого не заметить - заход всё равно начинается там, где ffmpeg
    встал на самом деле.
    """
    monkeypatch.setattr(stream, "_SEEK_OK", {})
    keys = _map_of(clip)
    lying = keys._replace(at=[second + 0.7 for second in keys.at])
    for at in (keys.at[6], keys.at[9]):
        assert pack_start(clip, at, keys=lying) == pytest.approx(
            stream._pilot_start(clip, at), abs=SPLIT_SLACK
        ), "заход ушёл туда, куда показала врущая карта"
    assert stream._SEEK_OK[clip] is False, "враньё карты запоминается: второй раз не спрашиваем"


def test_the_map_keeps_quiet_where_the_rule_does_not_hold() -> None:
    """``nan`` там, где правило не обязано работать: чужой контейнер, край карты, голова файла.

    Голова - не придирка: у начала файла ffmpeg не пускает dts ниже нуля и сдвигает метки
    на кадр-два вперёд (замер: карта обещает 0.000, факт 0.080), то есть единственное место,
    где права карта, а не прогон.
    """
    keys = FilmKeys(60.0, [0.0, 2.0, 4.0, 6.0], [0, 1, 2, 3], "mkv")
    assert math.isnan(mapped_start(keys, 2.0)), "посадка в самое начало файла - не по карте"
    assert mapped_start(keys, 6.0) == pytest.approx(4.0), "mkv уезжает на предыдущий кадр"
    assert mapped_start(keys._replace(kind="mp4"), 6.0) == pytest.approx(6.0), "mp4 встаёт в него"
    assert math.isnan(mapped_start(keys, 60.0)), "за краем карты соседней строки нет"
    assert math.isnan(mapped_start(keys._replace(kind=""), 6.0)), "контейнер неизвестен"
    assert math.isnan(mapped_start(keys._replace(kind="ts"), 6.0)), "у mpegts своё правило"
    assert math.isnan(mapped_start(None, 6.0)), "карты нет - предсказывать нечем"


def test_readrate_paces_packing_and_can_be_switched_off() -> None:
    grid = Grid.uniform(100.0)
    assert "-readrate" in ffmpeg_pack_command("u", 0, "/run", grid, 0, 0.0, readrate=1.0)
    assert "-readrate" not in ffmpeg_pack_command("u", 0, "/run", grid, 0, 0.0, readrate=0.0)


def test_the_initial_burst_replaces_pausing_the_packer() -> None:
    """Запас впереди приёмника даёт burst, а не пауза процесса.

    Проверяем и то, и другое: флаг ``-readrate_initial_burst`` (ffmpeg ≥ 6.1) на месте и
    стоит до ``-i``, а сигналов остановки в коде показа не осталось вовсе — именно под
    SIGSTOP'ом приёмник намертво вис в BUFFERING при живых сегментах на диске.
    """
    from torrcast import cast as cast_module
    from torrcast import cli as cli_module
    from torrcast import stream as stream_module

    grid = Grid.uniform(100.0)
    command = ffmpeg_pack_command("u", 0, "/run", grid, 0, 0.0, readrate=1.0, burst=60.0)
    assert "-readrate 1 -readrate_initial_burst 60" in " ".join(command)
    assert command.index("-readrate_initial_burst") < command.index("-i")
    quiet = ffmpeg_pack_command("u", 0, "/run", grid, 0, 0.0, readrate=0.0, burst=60.0)
    assert "-readrate_initial_burst" not in quiet

    # В доках про SIGSTOP написано - важно, чтобы его не осталось в КОДЕ показа.
    for module in (stream_module, cli_module, cast_module):
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        assert "send_signal" not in source, f"{module.__name__}: показ шлёт сигналы упаковке"


def test_an_unreadable_keyframe_map_falls_back_to_a_flat_grid_out_loud() -> None:
    """Карту опорных кадров снять не вышло — берём ровную сетку и говорим об этом.

    Молчаливая подмена нарезки — ровно то, из-за чего подвисы расследовали двое суток:
    снаружи «сетка по кадрам» и «ровная сетка» выглядят одинаково, а ведут себя по-разному.
    Настройка ``hls_keyframes=false`` — тот же путь, но по своей воле.
    """
    from torrcast.state import Config
    from torrcast.stream import grid_for

    assert Config().hls_segment == 10.0 and Config().hls_keyframes is True

    said: list[str] = []
    # Порт 1 никем не слушается: карта не читается, и это не авария показа.
    grid = grid_for("http://127.0.0.1:1/film.mkv", 600.0, 10.0, True, say=said.append)
    assert grid == Grid.uniform(600.0, 10.0) and not grid.on_keys
    assert said and "ровно по 10 с" in said[0], "о подмене нарезки показ обязан сказать вслух"

    said.clear()
    told = grid_for("http://127.0.0.1:1/film.mkv", 600.0, 10.0, False, say=said.append)
    assert told == Grid.uniform(600.0, 10.0)
    assert said and "так велено настройкой" in said[0]


def test_a_half_written_segment_never_leaves_the_run_directory(tmp_path: Path) -> None:
    """Наружу выкладывается только дописанный кусок, и «файл есть» этого не значит.

    Сегментный муксер, в отличие от hls, не пишет через временный файл: файл появляется
    пустым и наполняется. Дописан тот, за которым муксер открыл следующий, — а последний
    становится дописанным только когда ffmpeg сам дошёл до конца входа (код 0).
    """
    out = hls_dir(str(tmp_path / "hls"))
    packer = fake_packer(out)
    packer.run.mkdir(parents=True)
    for slot in range(3):
        (packer.run / f"v{slot}.ts").write_bytes(f"кусок {slot}".encode())

    packer.publish()

    assert sorted(p.name for p in out.glob("v*.ts")) == ["v0.ts", "v1.ts"]
    assert (packer.run / "v2.ts").exists(), "последний кусок ещё пишется - наружу ему рано"

    # Код 0: ffmpeg дошёл до конца входа сам - значит дописан и последний кусок.
    packer.proc.code = 0  # type: ignore[attr-defined]
    packer.publish()
    assert sorted(p.name for p in out.glob("v*.ts")) == ["v0.ts", "v1.ts", "v2.ts"]
    assert not list(packer.run.glob("v*.ts")), "в каталоге прогона ничего не осталось"


def test_a_run_in_is_thrown_away_and_never_overwrites_an_honest_segment(
    tmp_path: Path,
) -> None:
    """Регресс сетки: докатка не имеет права затереть готовый сегмент прошлого прогона.

    Прогон почти всегда начинается раньше своей границы, и этот огрызок ffmpeg кладёт под
    именем предыдущего сегмента. Под тем же именем снаружи уже может лежать честный кусок,
    упакованный раньше, — и приёмник, попросив его после перемотки назад, получил бы
    вместо десяти секунд фильма полторы.
    """
    out = hls_dir(str(tmp_path / "hls"))
    (out / "v4.ts").write_bytes(b"honest v4 from the previous run")
    packer = fake_packer(out, first=5)
    packer.run.mkdir(parents=True)
    (packer.run / "v4.ts").write_bytes(b"run-in")  # докатка: 1.3 с вместо десяти
    (packer.run / "v5.ts").write_bytes(b"honest v5")
    (packer.run / "v6.ts").write_bytes(b"half-written")

    packer.publish()

    assert (out / "v4.ts").read_bytes() == b"honest v4 from the previous run", "докатка затёрла"
    assert not (packer.run / "v4.ts").exists(), "докатка не выброшена - прогон копит мусор"
    assert (out / "v5.ts").read_bytes() == b"honest v5"
    assert not (out / "v6.ts").exists(), "последний кусок ещё пишется"


# --- TC-467: тяжёлая копия не имеет права остановить выкладку навсегда ---
# ``break`` на куске тяжелее потолка приёмника оставлял выкладку стоять вечно: край
# не двигался, сама копия не удалялась, а всё за ней копилось в памяти до потолка
# несданного. Потолок гасил прогон, запрос приёмника поднимал его заново - и круг
# повторялся каждые ~3.6 минуты, потому что тяжёлый кусок детерминирован.


def _packer_with_a_heavy_copy(out: Path) -> Packer:
    """Прогон, честно дописавший два куска, первый из которых тяжелее потолка."""
    spare = out / "recode"
    spare.mkdir(parents=True)
    packer = fake_packer(out, first=0, code=0)  # код 0: дописан и последний кусок
    packer.spare = spare
    packer.run.mkdir(parents=True, exist_ok=True)
    (packer.run / segment_name(0)).write_bytes(b"x" * (MAX_SEGMENT_BYTES + 1))
    (packer.run / segment_name(1)).write_bytes(b"next")
    return packer


def test_a_too_heavy_copy_is_shrunk_on_the_spot_and_the_publish_moves_on(
    tmp_path: Path,
) -> None:
    """Копия тяжелее потолка, перекода нет: кусок ужимается прямо на месте, выкладка идёт
    дальше. Прежний ``break`` на этом месте останавливал выкладку навсегда (проверено
    откатом: без починки край так и остаётся ``-1``, наружу не выходит ни одного куска).
    """
    out = hls_dir(str(tmp_path / "hls"))
    packer = _packer_with_a_heavy_copy(out)
    asked: list[int] = []

    def shrink(slot: int, size: int) -> bool:
        asked.append(slot)
        (packer.spare / segment_name(slot)).write_bytes(b"recode")  # type: ignore[operator]
        return True

    packer.shrink = shrink
    packer.publish()

    assert (out / segment_name(0)).read_bytes() == b"recode"
    assert (out / segment_name(1)).read_bytes() == b"next"
    assert packer.edge == 1, "выкладка обязана пройти тяжёлое место, а не встать на нём"
    assert asked == [0], "ужатие спрашивается один раз и только про тяжёлый кусок"


def test_a_copy_that_cannot_be_shrunk_is_skipped_honestly_not_stalled_on(
    tmp_path: Path,
) -> None:
    """Ужать не вышло: место честно пропускается, память не копится, край двигается.

    Пропуск - это тоже решение выкладки, и край двигает именно оно: иначе запрос
    этого места выглядел бы перемоткой назад и крутил бы перепаковку вечно.
    """
    out = hls_dir(str(tmp_path / "hls"))
    packer = _packer_with_a_heavy_copy(out)
    packer.shrink = lambda slot, size: False
    packer.publish()

    assert not (out / segment_name(0)).exists(), "тяжёлый кусок наружу не вышел"
    assert not (packer.run / segment_name(0)).exists(), "копия выброшена - память не копится"
    assert (out / segment_name(1)).read_bytes() == b"next"
    assert packer.edge == 1, "пропуск двигает край: выкладка идёт дальше тяжёлого места"


def test_a_promised_place_is_never_answered_with_a_404(tmp_path: Path) -> None:
    """🔴 TC-501: пропущенное место держится молча, а не отвечается быстрым 404.

    Раньше тут стоял ровно обратный выбор - «ждать нечего, отвечаем сразу», - и он
    считал секунды, а не показ. Считать надо показ: манифест обещает весь фильм
    (:meth:`Grid.manifest`), имя пропущенного куска приёмник УЖЕ получил и придёт за ним
    обязательно, так что вопрос не «отвечать или нет», а «404 или тишина». Замер живого
    показа: на 404 приёмник гасит НЕДОИГРАННЫЙ буфер и уходит в круг «встал - погас -
    поднялся - попросил снова», 24 запроса подряд; на тишине тот же буфер доигрывается до
    конца, а дыру перешагивает его собственный сторож
    (:meth:`torrcast.cast.ChromecastReceiver._nudge`) - сеткой и через 8 с.

    Чего ожидание при этом не делает - так это не поднимает упаковку: тяжёлый кусок
    детерминирован, второй прогон над ним получит ровно ту же копию, и перепаковка
    крутилась бы вечно.
    """
    out = hls_dir(str(tmp_path / "hls"))
    feed = Feed(source="u", audio=0, out=out, grid=Grid.uniform(600.0), wait=0.6)
    feed.skipped.add(5)
    began = time.monotonic()
    assert feed.segment(5) is None, "файла на пропущенном месте нет и не будет"
    assert time.monotonic() - began >= 0.6, "быстрый 404 на обещанное имя - это смерть показа"
    assert feed.packer is None, "пропущенное место не имеет права поднимать упаковку"


def test_the_spot_shrink_packs_the_piece_under_the_cap(clip: str, tmp_path: Path) -> None:
    """Ужатие на месте - настоящий прогон ffmpeg: перекод ложится в ``spare``,
    влезает в потолок, и решение сказано одной честной строкой."""
    from torrcast.recode import Encode, Pace

    class _Recoder:
        """Кодировщик-заглушка: ровно то, что спрашивает ужатие."""

        def __init__(self, spare: Path) -> None:
            self.spare = spare
            self.encode = Encode()
            self.pace = Pace()
            self.threshold = 10.0
            self.over_wait = 60.0
            self.done: set[int] = set()

        def ready(self, slot: int) -> Path | None:
            path = self.spare / segment_name(slot)
            return path if path.exists() else None

    out = hls_dir(str(tmp_path / "hls"))
    spare = out / "recode"
    spare.mkdir(parents=True)
    said: list[str] = []
    feed = Feed(
        source=clip,
        audio=0,
        out=out,
        grid=Grid.uniform(float(CLIP_SECONDS)),
        log=said.append,
        recoder=_Recoder(spare),
    )
    assert feed._shrink(0, MAX_SEGMENT_BYTES + 1) is True
    made = spare / segment_name(0)
    assert made.exists(), "ужатие обязано положить перекод туда, откуда его возьмёт выкладка"
    assert 0 < made.stat().st_size <= MAX_SEGMENT_BYTES
    assert len(said) == 1 and "ужимаю" in said[0], "одно авто-решение - одна честная строка"


def test_the_spot_shrink_aims_under_both_ceilings_of_the_receiver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 TC-495: у приёмника ДВА потолка, а ужатие считало цель по одному - по весу.

    Живой показ 11-08 (сеанс на Q70D): ужатие сработало на слотах 0, 2 и 4, попросив
    8.87, 7.32 и 9.00 Мбит/с, а наружу уехало 9.65, 8.33 и **10.94** Мбит/с при потолке
    битрейта около десяти. Четыре подгруза в первую минуту, и ранние места ровно эти.
    Кусок был короткий, поэтому по весу влезал с запасом: чем короче кусок, тем больше
    мегабит в секунду помещается в одни и те же 16 МБ.

    Сам ffmpeg тут не нужен и не зовётся: проверяется РЕШЕНИЕ, а оно принимается и
    называется вслух до всякого прогона.
    """
    from torrcast.recode import MAXRATE_GAIN, Encode, Pace

    class _Recoder:
        """Кодировщик-заглушка: ровно то, что спрашивает ужатие."""

        def __init__(self, spare: Path) -> None:
            self.spare = spare
            self.encode = Encode()
            self.pace = Pace()
            self.threshold = 10.0  # потолок битрейта приёмника, ``recode_at_mbit``
            self.over_wait = 60.0
            self.done: set[int] = set()

        def ready(self, slot: int) -> Path | None:
            return None

    out = hls_dir(str(tmp_path / "hls"))
    said: list[str] = []
    recoder = _Recoder(out / "recode")
    # Тот самый слот 4 того самого сеанса: 9.55 с фильма.
    feed = Feed(
        source="u",
        audio=0,
        out=out,
        grid=Grid(bounds=(0.0, 9.55), duration=19.1),
        log=said.append,
        recoder=recoder,
    )
    monkeypatch.setattr(
        stream.Packer, "start", classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(OSError()))
    )
    assert feed._shrink(0, MAX_SEGMENT_BYTES + 1) is False  # ffmpeg не поднялся - это не важно
    asked = float(said[0].split(" до ")[1].split()[0])
    went = (asked * MAXRATE_GAIN + stream.AUDIO_MBIT) * stream.TS_OVERHEAD
    assert went <= recoder.threshold, "ужатие обязано укладываться в потолок битрейта"
    assert went * 9.55 / 8 <= feed.cap / 1e6, "и в потолок веса оно укладываться не перестало"


def test_the_spot_shrink_without_a_recoder_skips_the_place_once(tmp_path: Path) -> None:
    """Ужимать нечем (перекод выключен) - честный пропуск, сказанный один раз."""
    out = hls_dir(str(tmp_path / "hls"))
    said: list[str] = []
    feed = Feed(source="u", audio=0, out=out, grid=Grid.uniform(600.0), log=said.append)
    assert feed._shrink(5, MAX_SEGMENT_BYTES + 1) is False
    assert 5 in feed.skipped
    assert len(said) == 1 and "пропускаю" in said[0]
    assert feed._shrink(5, MAX_SEGMENT_BYTES + 1) is False
    assert len(said) == 1, "решение принято один раз - строки не разводим"


def test_what_was_actually_cut_is_checked_against_the_manifest(tmp_path: Path) -> None:
    """``drift`` — единственный способ поймать враньё манифеста, не глядя на ТВ.

    ffmpeg сам ведёт список нарезанного; если он разошёлся с сеткой больше чем на кадр,
    значит карта опорных кадров разъехалась с потоком, и ``EXTINF`` в манифесте — вымысел.
    Первая строка списка не в счёт: в ней муксер пишет начало прогона нулём.
    """
    out = hls_dir(str(tmp_path / "hls"))
    grid = Grid.uniform(100.0)
    packer = fake_packer(out, first=3)
    packer.run.mkdir(parents=True)
    (packer.run / PACK_LIST).write_text(
        "v2.ts,0.000000,30.000000\nv3.ts,30.000000,40.000000\nv4.ts,40.000000,50.000000\n"
    )

    assert packer.cuts() == [(2, 0.0, 30.0), (3, 30.0, 40.0), (4, 40.0, 50.0)]
    assert packer.drift(grid) == 0.0, "нарезано ровно то, что обещано"

    (packer.run / PACK_LIST).write_text(
        "v2.ts,0.000000,30.000000\nv3.ts,30.000000,40.000000\nv4.ts,41.500000,50.000000\n"
    )
    assert packer.drift(grid) == pytest.approx(1.5), "кусок уехал на 1.5 с - так и скажем"

    fresh = fake_packer(hls_dir(str(tmp_path / "fresh")))
    assert fresh.cuts() == [] and fresh.drift(grid) == 0.0, "списка нет - не выдумываем"


def test_a_request_for_an_unpacked_place_repacks_instead_of_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Приёмник мотает сам, а упаковка идёт за ним.

    Запрос сегмента, которого нет, — это и есть перемотка, и единственный правильный
    ответ на неё — начать паковать оттуда. 404 тут запрещён: ресивер, поймавший его,
    отказывается брать LOAD ещё пару минут (замерено на живом ТВ).
    """
    root = hls_dir(str(tmp_path / "hls"))
    started: list[int] = []
    monkeypatch.setattr(Feed, "restart", lambda self, slot: started.append(slot))
    feed = Feed(source="", audio=0, out=root, grid=Grid.uniform(FILM), wait=0.0)

    assert feed.segment(900) is None, "файла нет и упаковка мгновенной не бывает"
    assert started == [900], "перемотка на 9000-ю секунду = упаковка с сегмента 900"

    (root / "v900.ts").write_bytes(b"x")
    assert feed.segment(900) == root / "v900.ts", "готовый кусок отдаём не думая"


def test_a_burst_of_requests_after_a_seek_restarts_packing_only_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Живой Q70D после ``seek`` просит шесть сегментов за одну секунду (замерено: v50…v55).

    Перезапустить упаковку обязан ровно первый из них: шесть ffmpeg'ов подряд на одном
    месте — это шесть заходов в рой и потерянные секунды на каждом.
    """
    root = hls_dir(str(tmp_path / "hls"))
    started: list[int] = []
    monkeypatch.setattr(Feed, "restart", lambda self, slot: started.append(slot))
    feed = Feed(source="", audio=0, out=root, grid=Grid.uniform(FILM), wait=0.0)

    for slot in range(50, 56):
        feed.segment(slot)

    assert started == [50], "остальные пять - префетч того же места, а не пять перемоток"


def test_a_forward_seek_inside_the_run_does_not_wait_out_the_readrate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """28 с чёрного экрана на перемотке вперёд внутри прогона.

    Замер на живом Q70D: перемотка 3984 → 4100 (+116 с) — «запрос v385.ts
    · ждал 57.8 с». Место лежало **внутри** прогона и в семи сегментах за краем, то есть
    по счёту штук это был обычный ход показа. А по времени — нет: упаковка идёт
    ``readrate 1``, и семьдесят секунд фильма впереди края она будет читать семьдесят
    секунд. Ждать столько — это и есть подгруз, только называется иначе.
    """
    grid = Grid.uniform(FILM)
    out = hls_dir(str(tmp_path / "hls"))
    for slot in range(5):
        (out / f"v{slot}.ts").write_bytes(b"x")
    started: list[int] = []
    monkeypatch.setattr(Feed, "restart", lambda self, slot: started.append(slot))
    feed = Feed(source="", audio=0, out=out, grid=grid, wait=0.0, ahead=7, jump=15.0)

    # Прогон только что начался с нуля: первые 60 с фильма он читает на полной скорости,
    # и всё, что попадает в burst, честно «вот-вот допакуется».
    feed.packer = fake_packer(out, edge=4, at=0.0, rate=1.0, burst=60.0)
    feed.segment(5)
    assert started == [], "кусок внутри burst - упаковка достанет его за мгновение"

    # Тот же запрос в семи сегментах за краем: 110-я секунда фильма при планке чтения на
    # 60-й - это 50 секунд ожидания. Перезапуск с этого места стоит 3-4.
    feed.segment(11)
    assert started == [11], "ждать 50 с вместо перезапуска - это и есть чёрный экран"

    # А тот же прогон, проживший сто секунд, дочитал до 160-й: ждать нечего.
    started.clear()
    feed.packer = fake_packer(
        out, edge=4, at=0.0, rate=1.0, burst=60.0, began=time.monotonic() - 100.0
    )
    feed.segment(11)
    assert started == [], "упаковка это место уже прошла - перезапуск был бы вредительством"


def test_the_seek_threshold_is_counted_in_segments_not_in_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Порог «это перемотка, а не обычный ход показа» — ``ahead`` **штук** сегментов.

    В секундах его считать больше нельзя: на сетке по опорным кадрам сегменты разной
    длины, и одно и то же число секунд оказывается то шестью кусками, то тремя. А порог
    нужен ровно затем, чтобы пачка префетча после ``seek`` (шесть штук у живого Q70D) не
    сошла за шесть новых перемоток.
    """
    grid = Grid.on_keyframes(_keyframes(), 600.0)
    out = hls_dir(str(tmp_path / "hls"))
    for slot in range(5):
        (out / f"v{slot}.ts").write_bytes(b"x")
    started: list[int] = []
    monkeypatch.setattr(Feed, "restart", lambda self, slot: started.append(slot))
    feed = Feed(source="", audio=0, out=out, grid=grid, wait=0.0, ahead=7)
    feed.packer = fake_packer(out)

    feed.segment(4 + feed.ahead)
    assert started == [], "семь сегментов впереди края - обычный ход показа, ждём упаковку"

    feed.segment(4 + feed.ahead + 1)
    assert started == [12], "восьмой - уже перемотка, и паковать надо оттуда"


def test_a_seek_back_behind_the_run_repacks_instead_of_waiting_out_the_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Перемотка назад глубже окна при упаковке ОТ НУЛЯ.

    Так это выглядело: упаковка идёт с сегмента 0, показ ушёл на 6-ю минуту, окно
    вымело начало фильма из tmpfs — и зритель мотает в самое начало. Сегмента нет,
    но ``packer.first`` (ноль!) ниже запрошенного, и показ решал, что кусок «вот-вот
    допакуется». Ждал он его все ``wait`` секунд — две минуты тишины на экране, — а
    потом всё равно отвечал 404, после которого приёмник не берёт LOAD ещё пару минут.

    Теперь низ границы — честный край прогона: сегмент ниже края, которого нет на
    диске, паковать некому, и это ровно та же перемотка, что и вперёд.
    """
    grid = Grid.uniform(FILM)
    out = hls_dir(str(tmp_path / "hls"))
    for slot in range(30, 37):  # окно позади показа, начало фильма уже выметено
        (out / f"v{slot}.ts").write_bytes(b"x")
    started: list[int] = []

    def repack(self: Feed, slot: int) -> None:  # упаковка с места и доходит до него
        started.append(slot)
        (out / f"v{slot}.ts").write_bytes(b"x")

    monkeypatch.setattr(Feed, "restart", repack)
    feed = Feed(source="", audio=0, out=out, grid=grid, wait=120.0)
    feed.packer = fake_packer(out, first=0, edge=36)

    began = time.monotonic()
    answer = feed.segment(1)

    assert started == [1], "перемотка назад лечится тем же, чем вперёд: упаковкой с места"
    assert answer == out / "v1.ts", "None здесь - это 404, после которого ТВ молчит минутами"
    assert time.monotonic() - began < 2.0, "две минуты тишины до 404 - та самая беда"


def test_pieces_of_past_runs_never_move_the_edge_of_the_current_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Край упаковки — то, что выложил ЭТОТ прогон, а не то, что лежит в каталоге.

    Каталог показа общий на весь фильм, и в нём честно живут куски прошлых прогонов:
    сетка одна и детерминированная, под именем ``vN`` и до, и после перезапуска лежит
    одно и то же место фильма — такой кусок и отдаётся приёмнику без разговоров. Но к
    вопросу «докуда дошла упаковка» он отношения не имеет, и обе наивные починки
    ломались ровно об это: глоб уводил край то вперёд (запрос назад висел до 404), то
    назад (20 ложных перезапусков за 100 с показа).
    """
    grid = Grid.uniform(FILM)
    out = hls_dir(str(tmp_path / "hls"))
    started: list[int] = []
    monkeypatch.setattr(Feed, "restart", lambda self, slot: started.append(slot))
    feed = Feed(source="", audio=0, out=out, grid=grid, wait=0.0, ahead=7)
    feed.packer = fake_packer(out, first=0, edge=3)
    (out / "v900.ts").write_bytes(b"x")  # кусок прошлого прогона: показ там уже был

    feed.segment(9)
    assert started == [], "девятый - в семи сегментах за краем, это обычный ход показа"

    feed.segment(11)
    assert started == [11], "одиннадцатый - за краем дальше `ahead`, и чужой v900 тут не судья"

    started.clear()
    assert feed.segment(900) == out / "v900.ts", "кусок прошлого прогона честен: сетка одна"
    assert started == [], "и перепаковывать место, которое уже лежит в tmpfs, незачем"


def test_pieces_nobody_asked_for_are_handed_over_by_the_clock_of_the_show(tmp_path: Path) -> None:
    """Выкладка зовётся и тогда, когда у упаковки никто ничего не просит.

    Показ, читающий прогретое с диска (:meth:`Feed._warm`), к упаковке не обращается
    вовсе - а ffmpeg продолжает писать в tmpfs. Замер на стенде, 1080p 9.1 Мбит/с: за 12
    минут фильма несданное выросло до 832 МБ при выложенных 12 МБ и крае на нуле. С
    выкладкой по часам показа тот же прогон держит несданного 2 МБ, а вся память показа
    стоит на 152 МБ - окне ``keep`` секунд, как и задумано.
    """
    out = hls_dir(str(tmp_path / "hls"))
    feed = Feed(source="", audio=0, out=out, grid=Grid.uniform(FILM))
    feed.packer = packer = fake_packer(out, first=0, edge=-1, code=0)
    packer.run.mkdir(parents=True)
    for slot in range(4):
        (packer.run / f"v{slot}.ts").write_bytes(b"x" * 1000)

    assert packer.pending() == 4000, "несданного не видно - расти оно будет молча"
    assert feed.weight() == 4000, "вес показа не считает того, что лежит в каталоге прогона"

    feed.sweep()

    assert packer.edge == 3, "куски так и лежат в памяти, а приёмнику не отдано ничего"
    assert packer.pending() == 0 and feed.weight() == 4000, "выложенное считается дважды"
    assert not packer.halted, "прогон погашен на ровном месте"


def test_the_unhanded_pieces_have_a_ceiling_and_reaching_it_is_said_out_loud(
    tmp_path: Path,
) -> None:
    """У несданного есть потолок, и его достижение - строка, а не тихое съедание памяти.

    Выкладка встаёт на куске, который отдать не может (придержан под перекод, тяжелее
    потолка приёмника), и всё, что за ним, копится в памяти без предела. Прогон, который
    пишет в никуда, гасится: память возвращается, а запрос сегмента поднимет упаковку
    заново (:meth:`_steer`) - ровно как после паузы на пульте.
    """
    said: list[str] = []
    out = hls_dir(str(tmp_path / "hls"))
    feed = Feed(
        source="",
        audio=0,
        out=out,
        grid=Grid.uniform(FILM),
        log=said.append,
        pending_cap=4_000_000,
    )
    feed.packer = packer = fake_packer(out, first=0, edge=-1, code=0)
    packer.run.mkdir(parents=True)
    packer.hold = lambda slot, size=0: True  # выкладке нечего отдать
    for slot in range(5):
        (packer.run / f"v{slot}.ts").write_bytes(b"x" * 1_000_000)

    feed.sweep()

    assert packer.halted, "несданное растёт, а прогон пишет дальше"
    assert packer.pending() == 0, "память показу не вернулась"
    assert any("несданных кусков 5 МБ" in line for line in said), "память съедена молча"


def test_a_piece_finished_by_this_very_poll_is_not_mistaken_for_a_seek_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Приёмник, идущий вплотную за упаковкой, просит кусок за мгновение до его закрытия.

    Показ выкладывает готовое (:meth:`Packer.publish`) ровно там же, где решает, что
    делать с упаковкой, — и кусок, которого секунду назад не было, появляется прямо
    внутри этого решения. Считать его «ниже края, а файла нет», то есть перемоткой
    назад, нельзя: живой замер давал перезапуск упаковки на каждом четвёртом сегменте
    ровного показа.
    """
    out = hls_dir(str(tmp_path / "hls"))
    started: list[int] = []
    monkeypatch.setattr(Feed, "restart", lambda self, slot: started.append(slot))
    feed = Feed(source="", audio=0, out=out, grid=Grid.uniform(FILM), wait=0.0)
    feed.packer = fake_packer(out, first=0, edge=4)
    feed.packer.run.mkdir(parents=True)
    (feed.packer.run / "v5.ts").write_bytes(b"done")  # закрыт: за ним открыт следующий
    (feed.packer.run / "v6.ts").write_bytes(b"half")  # ещё пишется

    assert feed.segment(5) == out / "v5.ts", "кусок допакован - его и отдаём"
    assert started == [], "и это ровный ход показа, а не перемотка назад"
    assert feed.packer.edge == 5, "край прогона подвинулся ровно на выложенное"


def test_segments_left_ahead_after_a_rollback_do_not_pile_up_in_tmpfs(tmp_path: Path) -> None:
    """Уборка смотрела только назад, и откаты копили tmpfs.

    После перемотки назад глубже окна упаковка идёт с нового места, а сегменты той
    минуты, откуда зритель ушёл, остаются в памяти навсегда: окно позади до них не
    достаёт, а вперёд уборка не смотрела вовсе. Десяток откатов подряд — и в tmpfs
    лежат места фильма, которых на экране уже не будет.

    Убирается при этом только заведомо чужое: запас текущего прогона и префетч впереди
    позиции целы — иначе уборка отнимала бы у показа ровно то, ради чего он пакует.
    """
    grid = Grid.uniform(FILM)
    out = hls_dir(str(tmp_path / "hls"))
    for slot in (*range(30, 37), *range(1, 6)):
        (out / f"v{slot}.ts").write_bytes(b"x")
    feed = Feed(source="", audio=0, out=out, grid=grid, keep=120.0, ahead=7)
    feed.packer = fake_packer(out, first=1, edge=5)  # откатились в начало и пакуем оттуда

    feed.prune(played=20.0)  # показ на 20-й секунде - это второй сегмент

    left = sorted(int(p.name[1:-3]) for p in out.glob("v*.ts"))
    assert left == [1, 2, 3, 4, 5], "место, откуда ушли, вымыто; запас текущего прогона цел"

    for slot in range(6, 13):  # упаковка ушла вперёд, приёмник за ней
        (out / f"v{slot}.ts").write_bytes(b"x")
    feed.packer.edge = 12
    feed.prune(played=60.0)
    left = sorted(int(p.name[1:-3]) for p in out.glob("v*.ts"))
    assert left == list(range(1, 13)), "обычный ход показа уборка вперёд не трогает"


def test_without_packing_nothing_is_swept_from_ahead_of_the_receiver(tmp_path: Path) -> None:
    """Упаковки нет — края нет, и гадать о нём уборка не имеет права.

    Такое бывает ровно на стыке: прогон погашен, новый ещё не поднят. Выбросить в этот
    момент запас впереди позиции значило бы заставить показ паковать его заново.
    """
    out = hls_dir(str(tmp_path / "hls"))
    for slot in range(0, 40):
        (out / f"v{slot}.ts").write_bytes(b"x")
    feed = Feed(source="", audio=0, out=out, grid=Grid.uniform(FILM), keep=120.0)

    feed.prune(played=20.0)

    assert len(list(out.glob("v*.ts"))) == 40, "без упаковки впереди не трогаем ничего"


def test_segments_are_never_cached_by_the_receiver(served: Any) -> None:
    """После перепаковки под теми же именами лежит другое место фильма — кэш соврал бы."""
    session, base = served
    for name in ("index.m3u8", "v0.ts"):
        assert session.get(f"{base}/{name}", timeout=10).headers["Cache-Control"] == "no-store"


def test_cors_is_on_every_answer_including_404_and_preflight(served: Any) -> None:
    """Chromecast без ``Access-Control-Allow-Origin`` молча не играет."""
    session, base = served
    for method, path in (("get", "/index.m3u8"), ("head", "/v0.ts"), ("get", "/нет.ts")):
        response = getattr(session, method)(f"{base}{path}", timeout=10)
        assert response.headers.get("Access-Control-Allow-Origin") == "*", path
    options = session.options(f"{base}/index.m3u8", timeout=10)
    assert options.headers.get("Access-Control-Allow-Origin") == "*"


def test_content_types_are_what_the_receiver_expects(served: Any) -> None:
    session, base = served
    assert session.get(f"{base}/index.m3u8").headers["Content-Type"] == (
        "application/vnd.apple.mpegurl"
    )
    assert session.get(f"{base}/v0.ts").headers["Content-Type"] == "video/mp2t"


def test_segments_answer_range_requests(served: Any) -> None:
    """Q70D переспрашивает куски диапазонами — без 206 он встаёт."""
    session, base = served
    response = session.get(f"{base}/v0.ts", headers={"Range": "bytes=10-19"}, timeout=10)
    assert response.status_code == 206
    assert response.headers["Content-Range"] == "bytes 10-19/1024"
    assert len(response.content) == 10
    tail = session.get(f"{base}/v0.ts", headers={"Range": "bytes=-16"}, timeout=10)
    assert tail.status_code == 206 and len(tail.content) == 16
    bad = session.get(f"{base}/v0.ts", headers={"Range": "bytes=5000-6000"}, timeout=10)
    assert bad.status_code == 416


def test_nothing_but_the_stream_is_reachable(served: Any) -> None:
    """Наружу открыт не каталог, а ровно манифест и сегменты."""
    session, base = served
    for path in ("/", "/../../etc/passwd", "/index.m3u8.tmp", "/config.json", f"/{PACK_DIR}"):
        assert session.get(f"{base}{path}", timeout=10).status_code == 404, path


def test_a_stopped_show_stops_answering_even_on_a_live_connection(tmp_path: Path) -> None:
    """Стык серий: остановленная раздача обязана ЗАМОЛЧАТЬ.

    Приёмник ходит по HTTP/1.1 и держит одно соединение на весь показ, а потоки-обработчики
    демонические — ``server_close`` закрывает слушающий сокет и не трогает их. Пока это было
    так, LOAD следующей серии уходил в keep-alive прошлой, и отвечал на него уже
    остановленный :class:`Feed`: манифест прошлой серии и мгновенный 404 на ``v0.ts``.
    Приёмник на это отвечает ``IDLE/ERROR`` — те самые 15 с пустого экрана на живом Q70D.

    Проверяется ровно это: то же самое соединение, тот же порт, следующая серия — и ни
    одного ответа от прошлой.
    """
    import http.client

    port = free_port()  # порт один на две серии: в этом весь тест
    old_root, old_feed = _stub(tmp_path / "s1e5")
    old = HlsServer(old_root, host="127.0.0.1", port=port, feed=old_feed)
    old.start()
    live = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    live.request("GET", "/index.m3u8")
    assert live.getresponse().read().startswith(b"#EXTM3U"), "показ идёт, соединение живое"

    old_feed.stop()  # ровно то, что делает _play в finally на стыке серий
    old.stop()
    new_root, new_feed = _stub(tmp_path / "s1e6")
    new = HlsServer(new_root, host="127.0.0.1", port=port, feed=new_feed)
    new.start()
    try:
        with pytest.raises((http.client.HTTPException, OSError)):
            live.request("GET", "/index.m3u8")  # приёмник обязан узнать, что соединения нет
            live.getresponse().read()
        fresh = requests.get(f"http://127.0.0.1:{port}/v0.ts", timeout=10)
        assert fresh.status_code == 200, "новое соединение отвечает уже следующая серия"
    finally:
        live.close()
        new.stop()


def test_a_run_we_stopped_ourselves_is_never_reported_as_a_crash(tmp_path: Path) -> None:
    """Собственный ``terminate`` — не авария и не «нет вывода».

    ffmpeg по SIGTERM выходит **кодом 255** (положительным, то есть на «убит сигналом» не
    похоже), а прощаться он умеет только уровнем ``info`` — при ``-loglevel warning``
    stderr остаётся пустым. Ровно так показ и ругался на труп, который сам же и снял.
    """
    out = hls_dir(str(tmp_path / "hls"))
    feed = Feed(source="", audio=0, out=out, grid=Grid.uniform(20.0), wait=0.0)
    packer = fake_packer(out, code=255)
    packer.stopped = "показ окончен"
    feed.packer = packer

    assert packer.why() == "сняли сами: показ окончен"
    assert feed._survive(packer), "снятый нами прогон попытку не тратит"
    assert feed.crashes == 0 and not feed.fatal

    other = fake_packer(out, code=255)
    assert other.why() == "молча, код 255", "чужое молчание врать про себя не даёт"
    text = "#EXTM3U\n#EXTINF:4.000000,\nindex0.ts\n#EXTINF:2.500000,\nindex1.ts\n#EXT-X-ENDLIST\n"
    segments, ended = parse_manifest(text)
    assert segments == [("index0.ts", 4.0), ("index1.ts", 2.5)]
    assert ended
    assert parse_manifest("#EXTM3U\n")[1] is False


def test_acceptance_verdict_needs_no_gaps_no_missing_cors_and_a_full_decode() -> None:
    full = Report(segments=1800, duration=7200.0, decoded=7199.0)
    assert full.ok
    assert not Report(segments=1800, duration=7200.0, decoded=7199.0, gaps=1).ok
    assert not Report(segments=1800, duration=7200.0, decoded=7199.0, no_cors=1).ok
    assert not Report(segments=1800, duration=7200.0, decoded=3000.0).ok, "оборвался посередине"
    assert not Report().ok, "приёмник вообще ничего не увидел"


def test_the_real_video_codec_comes_from_the_stream_not_the_name() -> None:
    """Имя раздачи о кодеке чаще молчит, а видео уходит на ТВ как есть."""
    from torrcast.stream import Media

    assert Media(video="h264").video_warning == ""
    assert "hevc" in Media(video="hevc").video_warning
    assert "mpeg4" in Media(video="mpeg4").video_warning, "XviD/DivX ресивер не возьмёт"
    assert Media().video_warning == ""


def test_ten_bit_h264_is_not_the_same_picture_as_plain_h264() -> None:
    """🔴 Hi10P зовётся ``h264``, а приёмник его не декодирует: паспорт обязан их различать.

    Живой замер (TC-164, «Death Note» BDRip): ``h264`` / ``High 10`` / ``yuv420p10le``
    доигрывал буфер до 70 с и вставал в вечную петлю LOAD/BUFFERING. По имени кодека такой
    файл неотличим от обычного, поэтому решает глубина цвета.
    """
    from torrcast.stream import Media, color_depth

    assert color_depth("yuv420p10le") == 10
    assert color_depth("yuv420p") == 8, "обычная картинка - восемь бит"
    assert color_depth("p010le") == 10, "формат аппаратного декодера - тоже десять"
    assert color_depth("yuv444p12le") == 12
    assert color_depth(None) == 8, "паспорт молчит - решаем как раньше, копией"
    assert color_depth(None, "High 10") == 10, "формата кадра нет - верим профилю"
    assert color_depth("", "Main 10") == 10
    assert color_depth(None, "High 4:4:4 Predictive") == 8, "цифры в имени - не глубина"

    hi10 = Media(video="h264", profile="High 10", pix_fmt="yuv420p10le")
    plain = Media(video="h264", profile="High", pix_fmt="yuv420p")
    assert hi10.depth == 10 and plain.depth == 8
    assert hi10.recoded_whole, "десятибитный H.264 идёт сплошным перекодом, как HEVC"
    assert not plain.recoded_whole, "обычный H.264 как уезжал копией, так и уезжает"
    assert hi10.video_name == "h264 10 бит" and plain.video_name == "h264"
    assert "10 бит" in hi10.video_warning, "молчать о нём нельзя: приёмник на нём встаёт"
    assert plain.video_warning == ""
    assert Media().depth == 0, "видео нет - и глубины нет"


def test_a_passport_from_the_old_shelf_is_not_believed_about_the_picture(tmp_path: Path) -> None:
    """Паспорт прежней версии формата кадра не несёт - и принят быть не может.

    Прими его показ за правду - и десятибитный H.264 снова уехал бы копией: молчание
    старой записи неотличимо от честного «восемь бит».
    """
    import json

    from torrcast.stream import AudioTrack, _keep_media, _read_media
    from torrcast.stream import Media as Passport

    cache = tmp_path / "probe.json"
    fresh = Passport(duration=1366.0, tracks=(AudioTrack(0, "rus"),), video="h264")
    _keep_media(cache, fresh)
    assert _read_media(cache) is not None, "свой же паспорт читается"

    saved = json.loads(cache.read_text("utf-8"))
    del saved["v"]
    cache.write_text(json.dumps(saved), encoding="utf-8")
    assert _read_media(cache) is None, "паспорт прежней версии - как будто его нет"


def test_the_scan_type_is_a_fact_of_the_file_not_of_the_name() -> None:
    """Буква развёртки ставится по потоку: чересстрочный «1080p» внутри - это «1080i».

    Имя раздачи про развёртку молчит или врёт, а гребёнку на экране даёт сам файл.
    Молчание паспорта читается как прогрессив: звать кадр чересстрочным по догадке -
    та же неправда, только в другую сторону.
    """
    from torrcast.stream import Media

    assert Media(height=1080, width=1920, field_order="tb").quality == "1080i"
    assert Media(height=1080, width=1920, field_order="bt").interlaced
    assert Media(height=576, width=720, field_order="bb").quality == "576i", "SD тоже честно"
    assert Media(height=1080, width=1920, field_order="progressive").quality == "1080p"
    assert Media(height=1080, width=1920).quality == "1080p", "паспорт молчит - как раньше"
    assert Media(height=0, field_order="tb").quality == "?", "кадра нет - и развёртки нет"


def test_probe_reads_the_scan_type_from_the_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """``field_order`` берётся тем же одним запросом к ffprobe и переживает полку.

    Проверено на настоящих файлах: x264 с ``tff=1`` ffprobe отвечает ``bt``, mpeg2video
    с ``-top 1`` - ``tb``, прогрессивному - ``progressive``; то есть значение стоит в
    потоке, а не в догадке по кодеку.
    """
    import json

    from torrcast import stream as stream_mod
    from torrcast.stream import probe

    payload = json.dumps(
        {
            "format": {"duration": "3600.0"},
            "streams": [
                {
                    "index": 0,
                    "codec_name": "h264",
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "field_order": "tb",
                },
                {
                    "index": 1,
                    "codec_name": "aac",
                    "codec_type": "audio",
                    "channels": 2,
                    "tags": {"language": "rus"},
                },
            ],
        }
    )
    asked: list[list[str]] = []

    def fake_probe(command: list[str], timeout: float, alive: object) -> str:
        asked.append(command)
        return payload

    monkeypatch.setattr(stream_mod, "_run_ffprobe", fake_probe)
    media = probe("http://torr/stream/hash-1/2")
    assert media.interlaced and media.quality == "1080i"
    assert any("field_order" in flag for flag in asked[0]), "спросили тем же одним запросом"

    def boom(*a: object) -> str:
        raise AssertionError("паспорт обязан прийти с полки, а не от ffprobe")

    monkeypatch.setattr(stream_mod, "_run_ffprobe", boom)
    cached = probe("http://torr/stream/hash-1/2")
    assert cached.interlaced and cached.quality == "1080i", "полка развёртку хранит"


def test_only_what_the_receiver_has_passed_is_swept_out_of_ram(tmp_path: Path) -> None:
    """Фильм целиком в tmpfs не влезает, поэтому позади показа держим окно ``keep``.

    Считать окно в штуках было ловушкой «Моаны 2»: длину сегмента задавал ключевой кадр,
    и «45 штук» оказывались то четырьмя минутами, то сорока секундами. Окно и теперь
    считается секундами, а номер границы берётся у сетки (:meth:`Grid.slot_at`) — то есть
    правило одно и то же и на ровной сетке, и на сетке по опорным кадрам.
    """
    for grid in (Grid.uniform(FILM), Grid.on_keyframes(_keyframes(), 600.0)):
        out = hls_dir(str(tmp_path / "hls"))
        for slot in range(grid.count):
            (out / f"v{slot}.ts").write_bytes(b"x")
        feed = Feed(source="", audio=0, out=out, grid=grid, keep=40.0)

        feed.prune(played=200.0)  # показ на 200-й секунде, окно 40 с - всё до 160-й не нужно
        edge = grid.slot_at(160.0)
        assert edge > 0, "тест бессмыслен, если окно не отрезает ничего"
        left = sorted(int(p.name[1:-3]) for p in out.glob("v*.ts"))
        assert left == list(range(edge, grid.count)), "позади окна убрано, окно и запас целы"

        feed.prune(played=10.0)
        assert len(list(out.glob("v*.ts"))) == grid.count - edge, "в начале ничего не удаляется"


def test_a_long_decision_does_not_hold_up_a_neighbours_ready_segment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пока один поток раздачи решает, второй ждёт свой файл, а не замок.

    Решение о перезапуске упаковки берёт замок и держит его вместе с пробным прогоном -
    до минуты по потолку. Сосед, вставший в очередь за замком, всё это время не смотрел
    бы даже на свой файл: тот появляется, а ответ уходит на минуту позже.
    """
    import threading

    out = hls_dir(str(tmp_path / "hls"))
    grid = Grid.uniform(FILM)
    feed = Feed(source="", audio=0, out=out, grid=grid, wait=10.0)
    holding = threading.Event()

    def slow_steer(self: Feed, slot: int) -> bool:
        holding.set()
        time.sleep(1.0)  # пробный прогон: 0.5-1.7 с обычно, до 60 с по потолку
        return True

    monkeypatch.setattr(Feed, "_steer", slow_steer)
    decider = threading.Thread(target=lambda: feed.segment(0), daemon=True)
    decider.start()
    assert holding.wait(timeout=5), "решение так и не началось - тест бессмыслен"

    ready = out / "v7.ts"
    threading.Timer(0.2, lambda: ready.write_bytes(b"x")).start()
    began = time.monotonic()
    found = feed.segment(7)
    took = time.monotonic() - began
    decider.join(timeout=5)

    assert found == ready, "готовый сегмент обязан вернуться"
    assert took < 0.8, f"сосед ждал замок, а не файл: {took:.2f} с при решении на 1.0 с"


def test_the_lead_over_the_receiver_is_measurable(tmp_path: Path) -> None:
    """Запас показа — измеряемая величина, а не ощущение.

    Запас показа в секундах фильма и вес tmpfs — единственное, чем провал устойчивости
    отличается от «показалось»: приёмник встаёт ровно тогда, когда запас сходит в ноль.
    Считается он по сетке и **от позиции приёмника**, то есть это конец непрерывной
    цепочки готовых кусков перед ним, а не «столько-то кусков по столько-то секунд».
    """
    out = hls_dir(str(tmp_path / "hls"))
    grid = Grid.on_keyframes(_keyframes(), 600.0)
    feed = Feed(source="", audio=0, out=out, grid=grid)
    assert feed.front() == 0.0 and feed.weight() == 0, "упаковки нет - и запаса нет"
    assert feed.drift() == 0.0, "упаковки нет - и расхождению с манифестом взяться неоткуда"

    for slot in range(30, 36):
        (out / f"v{slot}.ts").write_bytes(b"x" * 1000)
    feed.packer = fake_packer(out, first=30)

    where = grid.start(30)
    assert feed.front(where) == grid.end(35), "готовы сегменты 30...35 - запас до конца 35-го"
    assert feed.weight() == 6000


def test_the_lead_is_counted_from_the_receiver_and_breaks_on_a_hole(tmp_path: Path) -> None:
    """Запас — это то, что лежит ПОДРЯД перед приёмником, а не глоб каталога.

    Ровно на этом числе стоит сторож приёмника, и врало оно после каждой перемотки назад:
    в каталоге показа лежат честные куски прошлых прогонов (сетка детерминирована),
    и «докуда упаковано» считалось по ним. Замер на живом Q70D: откат с 31-й
    минуты на 10-ю дал «показ 600 · упаковано 2010 · впереди 1410 с» при пустом месте
    перед приёмником — то есть разрешение сторожу дёргать показ ровно тогда, когда нельзя.
    """
    out = hls_dir(str(tmp_path / "hls"))
    grid = Grid.uniform(600.0, 10.0)
    feed = Feed(source="", audio=0, out=out, grid=grid)
    for slot in (*range(30, 36), 40, 41):  # куски прошлого прогона и дырка перед ними
        (out / f"v{slot}.ts").write_bytes(b"x")
    feed.packer = fake_packer(out, first=30)

    assert feed.front(5.0) == 5.0, "перед приёмником пусто - запаса нет, что бы ни лежало дальше"
    assert feed.front(grid.start(30)) == grid.end(35), "цепочка обрывается на дырке, а не на 41"
    assert feed.front(grid.start(40)) == grid.end(41), "считаем от приёмника, а не от начала"


def test_mock_receiver_closes_its_ffmpeg_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """Журнал ffmpeg - открытый временный файл, и закрывать его обязан сам приёмник.

    Приёмник живёт весь юнит, а сериал зовёт ``play`` на каждую серию: журнал прошлой
    оставался открытым до сборки мусора, и ``stop`` его не закрывал вовсе.
    """
    import subprocess
    import tempfile

    from torrcast import InfraError
    from torrcast.cast import MockReceiver

    # mypy сужает тип receiver._err по присваиванию и не сбрасывает сужение на
    # вызовах методов - смотреть на атрибут через функцию, а не напрямую
    def err_of(r: MockReceiver) -> IO[bytes] | None:
        return r._err

    receiver = MockReceiver()
    first = tempfile.TemporaryFile()  # noqa: SIM115 - закрыть его и есть предмет проверки
    receiver._err = first
    receiver.stop()
    assert first.closed and err_of(receiver) is None, "stop не закрыл журнал"

    receiver._err = second = tempfile.TemporaryFile()  # noqa: SIM115 - то же самое
    monkeypatch.setattr(MockReceiver, "_probe", lambda self, url: None)
    monkeypatch.setattr(subprocess, "Popen", _no_ffmpeg)
    with pytest.raises(InfraError):
        receiver.play("http://127.0.0.1/index.m3u8")
    assert second.closed, "новый показ бросил журнал прошлого открытым"
    assert err_of(receiver) is None, "ffmpeg не запустился - журнал не за кем держать"


def _no_ffmpeg(*args: Any, **kwargs: Any) -> Any:
    raise FileNotFoundError("ffmpeg")


def test_a_real_ca_signed_cert_is_verified_against_the_system_store(
    tls: tuple[str, str], tmp_path: Path
) -> None:
    """Чему доверяет mock: Chromecast требует доверенный HTTPS.

    Self-signed проверять нечем, кроме него самого. А настоящую цепочку LE обязано
    принимать системное хранилище — иначе «проверка» вырождается в пиннинг к
    промежуточному серту из того же файла, и подмена self-signed'ом прошла бы незаметно.
    """
    from torrcast.cast import MockReceiver, make_receiver, trust_anchor

    assert trust_anchor(tls[0]) == tls[0], "self-signed: доверяем ему самому"

    root, intermediate, leaf = _le_shaped_chain(tmp_path)
    chain = tmp_path / "fullchain.pem"
    chain.write_text(leaf + intermediate)  # ровно то, что лежит в acme.json: лист + промежуточный
    assert trust_anchor(str(chain)) == "", "цепочка CA: доверяем системному хранилищу"

    receiver = make_receiver("mock", "", str(chain))
    assert isinstance(receiver, MockReceiver) and receiver.ca == ""

    # Корень, приложенный к файлу явно, остаётся доверенным: так гоняется dev-контур.
    own = tmp_path / "own.pem"
    own.write_text(leaf + root)
    assert trust_anchor(str(own)) == str(own)
    assert trust_anchor(str(tmp_path / "нет-такого.pem")) == str(tmp_path / "нет-такого.pem")


def _le_shaped_chain(tmp_path: Path) -> tuple[str, str, str]:
    """Корень → промежуточный → лист: форма цепочки Let's Encrypt.

    Важна именно она: в `fullchain.pem` от Traefik корня нет, и «доверенным» из файла
    оказался бы промежуточный — то есть проверка выродилась бы в пиннинг к нему.
    """
    import subprocess

    def run(*args: str) -> None:
        subprocess.run(["openssl", *args], check=True, capture_output=True)

    ext = tmp_path / "ca.ext"
    ext.write_text("basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign\n")
    names = ("root", "inter", "leaf")
    key = {n: tmp_path / f"{n}.key" for n in names}
    crt = {n: tmp_path / f"{n}.crt" for n in names}
    csr = {n: tmp_path / f"{n}.csr" for n in names}

    run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "5",
        "-keyout", str(key["root"]), "-out", str(crt["root"]), "-subj", "/CN=torrcast test root",
        "-addext", "basicConstraints=critical,CA:TRUE")  # fmt: skip
    for name, subject, issuer, extra in (
        ("inter", "/CN=torrcast test intermediate", "root", ["-extfile", str(ext)]),
        ("leaf", "/CN=torrcast.example.com", "inter", []),
    ):
        run("req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key[name]),
            "-out", str(csr[name]), "-subj", subject)  # fmt: skip
        run("x509", "-req", "-in", str(csr[name]), "-CA", str(crt[issuer]),
            "-CAkey", str(key[issuer]), "-days", "5", "-out", str(crt[name]), *extra)  # fmt: skip
    return crt["root"].read_text(), crt["inter"].read_text(), crt["leaf"].read_text()


def test_the_position_is_warmed_by_its_byte_offset_not_by_a_proportion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Продолжение с середины греет ровно то место файла, где лежит позиция.

    Смещение берётся из карты опорных кадров — той же, по которой строится сетка. Долей
    «позиция от длительности, умноженная на размер файла» тут обойтись нельзя: битрейт по
    фильму гуляет вдвое, и промах в один процент двухгигабайтного файла — это 20 МБ, то
    есть прогрев чужого места и отобранная у показа полоса.
    """
    from torrcast import stream as stream_module
    from torrcast.stream import HEAD_OPEN, FilmKeys, warm_file

    keys = FilmKeys(600.0, [0.0, 100.0, 200.0, 300.0], [0, 90 << 20, 500 << 20, 505 << 20], "mp4")
    # 200-я секунда - ровно половина фильма, а лежит она на 500 МБ из 505: пропорция
    # показала бы 250 МБ, то есть промахнулась бы на четверть фильма.
    assert keys.byte_at(240.0) == 500 << 20
    assert keys.byte_at(0.0) == 0 and keys.byte_at(-5.0) == 0

    asked: list[tuple[int, int]] = []
    monkeypatch.setattr(stream_module, "film_keys", lambda url: keys)

    def note(url: str, offset: int, upto: int = 0, alive: Any = None) -> int:
        asked.append((offset, upto))
        return 0

    monkeypatch.setattr(stream_module, "warm_at", note)
    warm_file("http://127.0.0.1:1/film.mp4", at=240.0)
    for _ in range(200):
        if len(asked) >= 2:
            break
        time.sleep(0.01)
    assert asked == [(0, HEAD_OPEN["mp4"]), (500 << 20, stream_module.HEAD_WARM)], (
        "с середины греется заголовок файла и место позиции, а не 32 МБ чужого начала"
    )

    asked.clear()
    warm_file("http://127.0.0.1:1/film.mp4")
    for _ in range(200):
        if asked:
            break
        time.sleep(0.01)
    assert asked == [(0, stream_module.HEAD_WARM)], "с нуля греется начало, и только оно"


def test_an_old_key_cache_without_offsets_still_builds_the_grid(tmp_path: Path) -> None:
    """Кэш карты прошлой версии смещений не знает — сетка из него всё равно строится.

    Выбросить такой кэш значило бы заставить первый же показ после обновления заново
    читать индекс у холодного роя. Грелка позиции без смещений просто не работает — это
    дешевле.
    """
    import json

    from torrcast.stream import _read_keys

    cache = tmp_path / "keys.json"
    cache.write_text(json.dumps({"duration": 600.0, "keys": [0.0, 10.0, 20.0]}), "utf-8")
    found = _read_keys(cache)
    assert found is not None and found.at == [0.0, 10.0, 20.0]
    assert found.offset == [] and found.byte_at(15.0) == 0


def test_the_key_lock_stays_alive_while_its_holder_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Замок карты живёт по mtime - значит, пока его держат, mtime обязан идти вперёд.

    Иначе сосед, заглянувший на середине долгого разбора, увидит протухший замок и полезет
    читать тот же хвост вторым потоком: ровно то, ради чего замок и заведён.
    """
    import torrcast.keymap as keymap_module
    from torrcast import stream as stream_module
    from torrcast.stream import _fetching, _keys_cache, film_keys

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(stream_module, "KEYS_LOCK", 0.3)  # 60 с в проде: столько не ждём
    url = "http://127.0.0.1:8090/stream?link=hash&index=1"
    lock = _keys_cache(url).with_suffix(".lock")
    alive: list[bool] = []

    def slow_keyframes(_: str) -> Any:
        for _tick in range(6):  # 0.6 с работы против 0.3 с жизни замка
            time.sleep(0.1)
            alive.append(_fetching(lock))
        return keymap_module.KeyMap(60.0, (keymap_module.Point(0.0, 0, 0),), 0, 0, "mkv")

    monkeypatch.setattr(keymap_module, "keyframes", slow_keyframes)
    film_keys(url)
    assert all(alive), f"замок протух под работающим читателем: {alive}"
    assert not lock.exists(), "замок обязан сниматься после записи кэша"


def test_two_writers_of_one_key_map_do_not_share_a_draft(tmp_path: Path) -> None:
    """Черновик кэша карты - файл на писателя, а не на URL.

    Замок на карту берётся не всегда (протух, каталог только для чтения), и два писателя
    на одно имя пишут вперемешку: наружу уехала бы склейка двух половин.
    """
    import threading

    from torrcast.stream import _keys_draft

    cache = tmp_path / "abcdef0123456789.json"
    drafts: list[Path] = []
    # ⚠️ Писатели обязаны быть живы ОДНОВРЕМЕННО: разойдись они по времени - и номер
    # потока переиспользуется, а вместе с ним и имя. Развести надо ровно тех, кто пишет
    # вперемешку, и барьер держит в тесте именно этот случай.
    gate = threading.Barrier(2)

    def draft() -> None:
        gate.wait(timeout=5)
        drafts.append(_keys_draft(cache))
        gate.wait(timeout=5)

    writers = [threading.Thread(target=draft) for _ in range(2)]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join(timeout=10)

    assert len(set(drafts)) == 2, f"два писателя взяли одно имя: {drafts}"
    for name in [*drafts, _keys_draft(cache)]:
        assert name != cache and name.name.endswith(".tmp")
        assert name.parent == cache.parent, "черновик кладётся рядом: replace атомарен в одной fs"


def test_the_head_warmed_under_the_question_is_sized_by_the_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Голова под «Продолжить?» меряется контейнером, а не запасом под ``moov``.

    У mp4 в голове лежит ``moov`` (у «Моаны 2» от YTS — 5.3 МБ), и без него ffmpeg вход
    не откроет. У mkv там EBML-заголовок, SeekHead, Info и Tracks — килобайты, а восемь
    мегабайт чужого начала на холодном рое съедали весь бюджет раздумья: до места позиции
    дело не доходило вовсе.
    """
    from torrcast import stream as stream_module
    from torrcast.stream import HEAD_OPEN, FilmKeys, head_open, warm_file

    assert head_open("mkv") < head_open("mp4"), "у mkv голова меньше - это и есть правка"
    assert head_open("") == stream_module.HEAD_OPEN_DEFAULT, "контейнер не известен - с запасом"

    asked: list[tuple[int, int]] = []

    def note(url: str, offset: int, upto: int = 0, alive: Any = None) -> int:
        asked.append((offset, upto))
        return 0

    monkeypatch.setattr(stream_module, "warm_at", note)
    for kind in ("mkv", "mp4"):
        asked.clear()
        keys = FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], kind)
        monkeypatch.setattr(stream_module, "film_keys", lambda url, k=keys: k)
        warm_file(f"http://127.0.0.1:1/film.{kind}", at=240.0)
        for _ in range(200):
            if len(asked) >= 2:
                break
            time.sleep(0.01)
        assert asked[0] == (0, HEAD_OPEN[kind]), f"{kind}: голова не по контейнеру"


def test_an_old_key_cache_takes_the_container_from_the_file_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Карта из кэша прошлой версии контейнера не знает — его называет имя файла.

    Без этой подсказки продолжение по уже игранному фильму грело бы восемь мегабайт
    головы вечно: кэш карт живёт долго, а переснимать его ради одного поля незачем.
    """
    from torrcast import stream as stream_module
    from torrcast.stream import HEAD_OPEN, FilmKeys, container_of, warm_file

    assert (container_of("Moana.2.2024.mkv"), container_of("Moana.mp4")) == ("mkv", "mp4")
    assert container_of("Moana.avi") == "" and container_of("Moana") == ""

    asked: list[tuple[int, int]] = []

    def note(url: str, offset: int, upto: int = 0, alive: Any = None) -> int:
        asked.append((offset, upto))
        return 0

    keys = FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], "")  # кэш прошлой версии
    monkeypatch.setattr(stream_module, "warm_at", note)
    monkeypatch.setattr(stream_module, "film_keys", lambda url: keys)
    warm_file("http://127.0.0.1:1/stream?link=hash&index=1", at=240.0, name="Moana.2.2024.mkv")
    for _ in range(200):
        if len(asked) >= 2:
            break
        time.sleep(0.01)
    assert asked[0] == (0, HEAD_OPEN["mkv"]), "имя файла назвало контейнер - греем по нему"


def _desert(mbit: float = 10.0) -> tuple[list[float], list[int], float]:
    """Карта «как у «Тачек 3»»: ровный GOP 10.427 с и одна пустыня без опорных кадров.

    В пустыне (место 3965.670 живого файла) первый опорный кадр не раньше шага лежит через
    18.435 с, а внутри есть кадр на 8.008 с. Прежнее правило берёт первый — и отдаёт
    приёмнику 23 МБ одним куском; ровно этот кусок ловился на живом ТВ.
    Байты кладутся ровным битрейтом: столько же, сколько уезжает на ТВ после перекода.
    """
    gop = 10.427
    keys = [round(k * gop, 3) for k in range(40)]
    desert = keys[20]
    keys = (
        keys[:21]
        + [round(desert + 8.008, 3)]
        + [round(desert + 18.435 + k * gop, 3) for k in range(19)]
    )
    duration = keys[-1]  # хвост прилипает к последнему куску, и на него правило не влияет
    return keys, [int(k * mbit * 1e6 / 8) for k in keys], duration


def test_the_grid_never_hands_the_receiver_a_segment_heavier_than_the_cap() -> None:
    """Потолок веса сегмента — механизм подвиса приёмника, а не украшение сетки.

    Приёмник Q70D срывается в BUFFERING на 4–8 с ровно на границе, за которой лежит
    кусок тяжелее ~19 МБ, и снимается сам, повторно скачав уже полученные сегменты.
    Замерено в обе стороны на живом ТВ: 20.0 с и 14.3 МБ — чисто, 19.9 с и 24.2 МБ —
    потеря сессии; 16.934 с / 18.7 МБ — чисто, 16.892 с / 20.3 МБ — стоп 8 с. Значит
    сетка обязана считать байты, а не только секунды.
    """
    mbit = 10.0
    keys, sizes, duration = _desert(mbit)
    heavy = Grid.on_keyframes(keys, duration, 10.0)
    capped = Grid.on_keyframes(keys, duration, 10.0, sizes=sizes)

    def weigh(grid: Grid, slot: int) -> float:
        return grid.span(slot) * mbit * 1e6 / 8

    assert max(weigh(heavy, k) for k in range(heavy.count)) > MAX_SEGMENT_BYTES, (
        "карта подобрана неверно: прежнее правило обязано давать кусок тяжелее потолка"
    )
    assert all(weigh(capped, k) <= MAX_SEGMENT_BYTES for k in range(capped.count)), (
        "сегмент тяжелее потолка - это и есть подвис приёмника"
    )
    assert capped.bounds != heavy.bounds, "сетка обязана была измениться"
    assert all(b in keys or b == 0.0 for b in capped.bounds), "границы остались на опорных кадрах"
    assert capped.count == heavy.count + 1, "лишний рез ровно один - в пустыне, а не по всему кино"


def test_the_cap_counts_what_leaves_for_the_tv_not_what_lies_in_the_container() -> None:
    """Считать вес по контейнеру — значит считать чужое: у «Моаны 2» десять озвучек.

    На ТВ уезжает видео плюс наш AAC, и тяжёлый кусок ещё и перекодируется, поэтому
    потолок обязан знать поправку «контейнер → ТВ» и потолок перекодирования. Слепое
    правило на том же файле решает, что резать бесполезно (по контейнеру не влезает ни
    один вариант), и отдаёт кусок как есть — то есть ровно тот подвис, ради которого всё
    и делалось.
    """
    keys, sizes, duration = _desert(20.0)  # контейнер: кино плюс восемь озвучек рядом
    plain = Grid.on_keyframes(keys, duration, 10.0)
    blind = Grid.on_keyframes(keys, duration, 10.0, sizes=sizes)
    aware = Grid.on_keyframes(keys, duration, 10.0, sizes=sizes, extra_mbit=12.0)
    recoded = Grid.on_keyframes(keys, duration, 10.0, sizes=sizes, ceiling_mbit=8.0)

    assert blind.bounds == plain.bounds, "по контейнеру не влезает ничего - правило сдаётся"
    assert aware.count == plain.count + 1, "поправка известна - рез ровно один, в пустыне"
    assert recoded.count == plain.count + 1, "перекод сделает кусок легче, и сетка это знает"
    for grid in (aware, recoded):
        heaviest = max(grid.span(k) * 8e6 / 8 for k in range(grid.count))
        assert heaviest <= MAX_SEGMENT_BYTES, "на ТВ всё равно уехал кусок тяжелее потолка"


def test_a_grid_without_a_byte_map_stays_exactly_as_it_was() -> None:
    """Карта прошлой версии смещений не несёт — правило потолка обязано просто молчать.

    Иначе выкатка сломала бы показ по кэшу, снятому вчера: границы уехали бы, а имя
    сегмента у нас значит место в фильме.
    """
    keys, sizes, duration = _desert()
    plain = Grid.on_keyframes(keys, duration, 10.0).bounds
    assert Grid.on_keyframes(keys, duration, 10.0, sizes=()).bounds == plain, (
        "без карты байт сетка обязана остаться прежней"
    )
    assert Grid.on_keyframes(keys, duration, 10.0, sizes=sizes[:-3]).bounds == plain, (
        "карта не той длины - не повод менять нарезку молча"
    )
