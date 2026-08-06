"""Формат потока §3, сетка сегментов §6.1 и раздача HLS: то, на чём ресивер молча ломается.

Проверяется ровно то, что зафиксировано ТЗ и реестром ТВ-рисков §9: TS-сегменты по сетке
:class:`~torrcast.stream.Grid`, один вариант, видео copy, аудио всегда AAC stereo 192k,
VOD-манифест на весь фильм, CORS на всех ответах (включая 404 и preflight) и Range на
сегментах.

Отдельная тема здесь — **абсолютность** сетки. Раньше ffmpeg резал каждые N секунд от
первого пакета своего прогона, то есть имя сегмента значило разное место фильма в
зависимости от того, откуда начали паковать. Теперь граница — это число от нуля фильма, и
почти все тесты ниже про то, что это число одно и то же в манифесте и в команде ffmpeg.

Раздача идёт по http на голом IP (§5 SPEC-v2) — так же, как её видит телевизор.
https проверяется отдельно: это выключенная опция, но она обязана оставаться рабочей.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

import pytest
import requests

from tests.conftest import fake_packer
from torrcast.cast import Report
from torrcast.stream import (
    HLS_SEGMENT_SECONDS,
    MPEGTS_MUX_DELAY,
    PACK_DIR,
    PACK_LIST,
    SPLIT_SLACK,
    Feed,
    Grid,
    HlsServer,
    ffmpeg_pack_command,
    hls_dir,
    parse_manifest,
)

#: Ровная сетка на два часа: столько же, сколько играет фильм на стенде.
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
    server = HlsServer(root, host="127.0.0.1", port=18453, feed=feed)
    server.start()
    try:
        yield requests.Session(), "http://127.0.0.1:18453"
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
    """§5 SPEC-v2: раздача по умолчанию — http, и ни серта, ни имени ей не нужно.

    Сервер поднимается **без единого пути к серту** — то есть выключенный https не
    оставляет по себе обязательного файла, который некому положить.
    """
    from torrcast.state import Config

    assert Config().transport == "http"
    assert Config().hls_base_url == "", "имя в базе URL = DNS в пути показа (§5)"
    assert Config().hls_port == 8080

    root, feed = _stub(tmp_path)
    server = HlsServer(root, host="127.0.0.1", port=18457, feed=feed)
    server.start()
    try:
        answer = requests.get("http://127.0.0.1:18457/index.m3u8", timeout=10)
        assert answer.status_code == 200
        assert answer.headers["Access-Control-Allow-Origin"] == "*"
        assert answer.headers["Content-Type"] == "application/vnd.apple.mpegurl"
    finally:
        server.stop()


def test_https_stays_a_working_but_switched_off_option(
    tls: tuple[str, str], tmp_path: Path
) -> None:
    """Код https никуда не делся (§5): включается флагом и играет как раньше."""
    root, feed = _stub(tmp_path)
    server = HlsServer(root, tls[0], tls[1], host="127.0.0.1", port=18458, tls=True, feed=feed)
    server.start()
    session = requests.Session()
    session.verify = tls[0]  # серт = собственный корень: TLS проверяется по-настоящему
    try:
        answer = session.get("https://127.0.0.1:18458/index.m3u8", timeout=10)
        assert answer.status_code == 200
        assert answer.headers["Access-Control-Allow-Origin"] == "*"
    finally:
        server.stop()


def test_the_playback_address_is_our_own_leg_toward_the_tv(tmp_path: Path) -> None:
    """§5 SPEC-v2: URL собирается из транспорта, нашего адреса со стороны ТВ и порта.

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
    manual = Config(tv="127.0.0.1", hls_base_url="http://192.168.1.62:8080/")
    assert hls_base(manual) == "http://192.168.1.62:8080"
    with pytest.raises(InfraError):
        hls_base(Config())  # адрес ТВ не задан — маршрута нет, и молчать об этом нельзя


def test_a_segment_name_always_means_the_same_place_of_the_film() -> None:
    """§6.1 SPEC-v2: ``slot_at`` обратна ``start`` — на обеих сетках и в любой точке.

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
        assert grid.slot_at(-10.0) == 0, "до начала фильма — первый сегмент, а не отрицательный"
        assert grid.slot_at(grid.duration * 2) == grid.count - 1, "за концом — последний"
        assert grid.end(grid.count - 1) == grid.duration, "последний сегмент кончается фильмом"


def test_the_manifest_promises_the_whole_film_so_the_tv_has_a_timeline() -> None:
    """§2.1 SPEC-v2: длительность в MEDIA_STATUS = сумме ``EXTINF``, значит она обязана
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

    # Ровная сетка на целое число шагов — это ровно столько же сегментов, без хвоста.
    step = float(HLS_SEGMENT_SECONDS)
    whole = Grid.uniform(step * 5)
    assert parse_manifest(whole.manifest())[0] == [(f"v{n}.ts", step) for n in range(5)]
    assert Grid.uniform(5978.5).count == int(5978.5 // step) + 1, "целые куски и хвост"


def test_a_keyframe_grid_never_cuts_a_segment_shorter_than_the_step() -> None:
    """§6.1 SPEC-v2: следующая граница — первый опорный кадр не раньше, чем через шаг.

    Иначе на сцене-вспышке (два десятка опорных кадров за полсекунды) манифест распух бы
    на пустом месте, а приёмник получил бы очередь огрызков вместо сегментов. Хвост —
    единственное исключение: он прилипает к последнему куску, пока короче половины шага,
    поэтому последний сегмент бывает короче остальных, но не короче половины шага.
    """
    step = 10.0
    grid = Grid.on_keyframes(_keyframes(), 600.0, step)

    spans = [grid.span(k) for k in range(grid.count)]
    assert min(spans[:-1]) >= step, "сегмент короче шага — сетка рассыпалась на огрызки"
    assert spans[-1] >= step / 2, "хвост прилипает к последнему куску, а не висит огрызком"
    assert max(spans) < step + 3.0, "GOP около 2 с — длиннее шага плюс GOP сегмента не бывает"

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
        assert grid.target() >= longest, "цель короче куска — приёмник вправе не успеть"
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


def test_stream_format_is_the_one_fixed_by_the_spec() -> None:
    """§3: один вариант, видео copy, звук всегда AAC stereo 192k, куски — MPEG-TS.

    Пишет ffmpeg в каталог прогона (:data:`PACK_DIR`), а не сразу наружу: «файл появился»
    у сегментного муксера не значит «кусок дописан» (:meth:`Packer.publish`).
    """
    grid = Grid.uniform(100.0)
    command = ffmpeg_pack_command("http://ts/stream", 1, "/dev/shm/torrcast/pack", grid, 0, 0.0)
    text = " ".join(command)
    assert "-c:v copy" in text, "видео только copy — перекодировать 1080p нам нечем"
    assert "-c:a aac -ac 2 -b:a 192k" in text, "AC3/DTS passthrough запрещён (§3)"
    assert "-map 0:v:0 -map 0:a:1" in text, "один вариант и выбранная дорожка по индексу"
    assert "-f segment -segment_format mpegts" in text, "сетку задаёт список, а не один шаг"
    assert command[-1] == "/dev/shm/torrcast/pack/v%d.ts", "имя = место в фильме"
    assert f"-segment_list /dev/shm/torrcast/pack/{PACK_LIST}" in text, "чем сверять факт"
    assert "-copyts" in text, "метки времени — абсолютные, иначе позиция считается от куска"


def test_mpegts_muxer_does_not_shove_its_own_delay_into_the_timestamps() -> None:
    """§6.2.2 SPEC-v2: ``-copyts`` без глушения муксера — время фильма плюс 1.4 с.

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


def test_segment_numbers_mean_the_same_place_wherever_the_run_started() -> None:
    """§6.1 SPEC-v2: границы в ``-segment_times`` абсолютные — вот главная проверка.

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
    assert _flag(exact, "-segment_start_number") == "5", "встали на границу — докатки нет"
    assert _flag(exact, "-ss") == "50.000" and exact.index("-ss") < exact.index("-i")

    near = ffmpeg_pack_command("u", 0, "/run", grid, 5, grid.start(5) - SPLIT_SLACK / 2)
    assert _flag(near, "-segment_start_number") == "5", "полкадра — это та же граница"

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


def test_readrate_paces_packing_and_can_be_switched_off() -> None:
    grid = Grid.uniform(100.0)
    assert "-readrate" in ffmpeg_pack_command("u", 0, "/run", grid, 0, 0.0, readrate=1.0)
    assert "-readrate" not in ffmpeg_pack_command("u", 0, "/run", grid, 0, 0.0, readrate=0.0)


def test_the_initial_burst_replaces_pausing_the_packer() -> None:
    """§6 SPEC-v2: запас впереди приёмника даёт burst, а не пауза процесса.

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

    # В доках про SIGSTOP написано — важно, чтобы его не осталось в КОДЕ показа.
    for module in (stream_module, cli_module, cast_module):
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        assert "send_signal" not in source, f"{module.__name__}: показ шлёт сигналы упаковке"


def test_an_unreadable_keyframe_map_falls_back_to_a_flat_grid_out_loud() -> None:
    """Карту опорных кадров снять не вышло — берём ровную сетку и говорим об этом.

    Молчаливая подмена нарезки — ровно то, из-за чего §6 SPEC-v2 расследовали двое суток:
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
    assert (packer.run / "v2.ts").exists(), "последний кусок ещё пишется — наружу ему рано"

    # Код 0: ffmpeg дошёл до конца входа сам — значит дописан и последний кусок.
    packer.proc.code = 0  # type: ignore[attr-defined]
    packer.publish()
    assert sorted(p.name for p in out.glob("v*.ts")) == ["v0.ts", "v1.ts", "v2.ts"]
    assert not list(packer.run.glob("v*.ts")), "в каталоге прогона ничего не осталось"


def test_a_run_in_is_thrown_away_and_never_overwrites_an_honest_segment(
    tmp_path: Path,
) -> None:
    """Регресс §6.1: докатка не имеет права затереть готовый сегмент прошлого прогона.

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
    assert not (packer.run / "v4.ts").exists(), "докатка не выброшена — прогон копит мусор"
    assert (out / "v5.ts").read_bytes() == b"honest v5"
    assert not (out / "v6.ts").exists(), "последний кусок ещё пишется"


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
    assert packer.drift(grid) == pytest.approx(1.5), "кусок уехал на 1.5 с — так и скажем"

    fresh = fake_packer(hls_dir(str(tmp_path / "fresh")))
    assert fresh.cuts() == [] and fresh.drift(grid) == 0.0, "списка нет — не выдумываем"


def test_a_request_for_an_unpacked_place_repacks_instead_of_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§2.1 SPEC-v2: приёмник мотает сам, а упаковка идёт за ним.

    Запрос сегмента, которого нет, — это и есть перемотка, и единственный правильный
    ответ на неё — начать паковать оттуда. 404 тут запрещён: ресивер, поймавший его,
    отказывается брать LOAD ещё пару минут (замерено 05-08-2026).
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

    assert started == [50], "остальные пять — префетч того же места, а не пять перемоток"


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
    assert started == [], "семь сегментов впереди края — обычный ход показа, ждём упаковку"

    feed.segment(4 + feed.ahead + 1)
    assert started == [12], "восьмой — уже перемотка, и паковать надо оттуда"


def test_a_seek_back_behind_the_run_repacks_instead_of_waiting_out_the_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 §7.4 SPEC-v2: перемотка назад глубже окна при упаковке ОТ НУЛЯ.

    Так это выглядело: упаковка идёт с сегмента 0, показ ушёл на 6-ю минуту, окно
    вымело начало фильма из tmpfs — и владелец мотает в самое начало. Сегмента нет,
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
    assert answer == out / "v1.ts", "None здесь — это 404, после которого ТВ молчит минутами"
    assert time.monotonic() - began < 2.0, "две минуты тишины до 404 — тот самый 🔴"


def test_pieces_of_past_runs_never_move_the_edge_of_the_current_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Край упаковки — то, что выложил ЭТОТ прогон, а не то, что лежит в каталоге.

    Каталог показа общий на весь фильм, и в нём честно живут куски прошлых прогонов:
    сетка одна и детерминированная, под именем ``vN`` и до, и после перезапуска лежит
    одно и то же место фильма — такой кусок и отдаётся приёмнику без разговоров. Но к
    вопросу «докуда дошла упаковка» он отношения не имеет, и обе наивные починки §7.4
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
    assert started == [], "девятый — в семи сегментах за краем, это обычный ход показа"

    feed.segment(11)
    assert started == [11], "одиннадцатый — за краем дальше `ahead`, и чужой v900 тут не судья"

    started.clear()
    assert feed.segment(900) == out / "v900.ts", "кусок прошлого прогона честен: сетка одна"
    assert started == [], "и перепаковывать место, которое уже лежит в tmpfs, незачем"


def test_a_piece_finished_by_this_very_poll_is_not_mistaken_for_a_seek_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Приёмник, идущий вплотную за упаковкой, просит кусок за мгновение до его закрытия.

    Показ выкладывает готовое (:meth:`Packer.publish`) ровно там же, где решает, что
    делать с упаковкой, — и кусок, которого секунду назад не было, появляется прямо
    внутри этого решения. Считать его «ниже края, а файла нет», то есть перемоткой
    назад, нельзя: замер на стенде 06-08-2026 давал перезапуск упаковки на каждом
    четвёртом сегменте ровного показа.
    """
    out = hls_dir(str(tmp_path / "hls"))
    started: list[int] = []
    monkeypatch.setattr(Feed, "restart", lambda self, slot: started.append(slot))
    feed = Feed(source="", audio=0, out=out, grid=Grid.uniform(FILM), wait=0.0)
    feed.packer = fake_packer(out, first=0, edge=4)
    feed.packer.run.mkdir(parents=True)
    (feed.packer.run / "v5.ts").write_bytes(b"done")  # закрыт: за ним открыт следующий
    (feed.packer.run / "v6.ts").write_bytes(b"half")  # ещё пишется

    assert feed.segment(5) == out / "v5.ts", "кусок допакован — его и отдаём"
    assert started == [], "и это ровный ход показа, а не перемотка назад"
    assert feed.packer.edge == 5, "край прогона подвинулся ровно на выложенное"


def test_segments_left_ahead_after_a_rollback_do_not_pile_up_in_tmpfs(tmp_path: Path) -> None:
    """🟡 §7.4 SPEC-v2: уборка смотрела только назад, и откаты копили tmpfs.

    После перемотки назад глубже окна упаковка идёт с нового места, а сегменты той
    минуты, откуда владелец ушёл, остаются в памяти навсегда: окно позади до них не
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

    feed.prune(played=20.0)  # показ на 20-й секунде — это второй сегмент

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
    """Chromecast без ``Access-Control-Allow-Origin`` молча не играет (§9)."""
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
    """Q70D переспрашивает куски диапазонами — без 206 он встаёт (грабли kinocast)."""
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
    """🔴 §7.4 SPEC-v2, стык серий: остановленная раздача обязана ЗАМОЛЧАТЬ.

    Приёмник ходит по HTTP/1.1 и держит одно соединение на весь показ, а потоки-обработчики
    демонические — ``server_close`` закрывает слушающий сокет и не трогает их. Пока это было
    так, LOAD следующей серии уходил в keep-alive прошлой, и отвечал на него уже
    остановленный :class:`Feed`: манифест прошлой серии и мгновенный 404 на ``v0.ts``.
    Приёмник на это отвечает ``IDLE/ERROR`` — те самые 15 с пустого экрана на живом Q70D.

    Проверяется ровно это: то же самое соединение, тот же порт, следующая серия — и ни
    одного ответа от прошлой.
    """
    import http.client

    port = 18461
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
    """🔴 §7.4 SPEC-v2: собственный ``terminate`` — не авария и не «нет вывода».

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
    """Имя раздачи о кодеке чаще молчит, а видео уходит на ТВ как есть (§9)."""
    from torrcast.stream import Media

    assert Media(video="h264").video_warning == ""
    assert "hevc" in Media(video="hevc").video_warning
    assert "mpeg4" in Media(video="mpeg4").video_warning, "XviD/DivX ресивер не возьмёт"
    assert Media().video_warning == ""


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

        feed.prune(played=200.0)  # показ на 200-й секунде, окно 40 с — всё до 160-й не нужно
        edge = grid.slot_at(160.0)
        assert edge > 0, "тест бессмыслен, если окно не отрезает ничего"
        left = sorted(int(p.name[1:-3]) for p in out.glob("v*.ts"))
        assert left == list(range(edge, grid.count)), "позади окна убрано, окно и запас целы"

        feed.prune(played=10.0)
        assert len(list(out.glob("v*.ts"))) == grid.count - edge, "в начале ничего не удаляется"


def test_the_lead_over_the_receiver_is_measurable(tmp_path: Path) -> None:
    """§6 SPEC-v2: запас показа — измеряемая величина, а не ощущение.

    Запас показа в секундах фильма и вес tmpfs — единственное, чем провал устойчивости
    отличается от «показалось»: приёмник встаёт ровно тогда, когда запас сходит в ноль.
    Считается он по сетке и **от позиции приёмника**, то есть это конец непрерывной
    цепочки готовых кусков перед ним, а не «столько-то кусков по столько-то секунд».
    """
    out = hls_dir(str(tmp_path / "hls"))
    grid = Grid.on_keyframes(_keyframes(), 600.0)
    feed = Feed(source="", audio=0, out=out, grid=grid)
    assert feed.front() == 0.0 and feed.weight() == 0, "упаковки нет — и запаса нет"
    assert feed.drift() == 0.0, "упаковки нет — и расхождению с манифестом взяться неоткуда"

    for slot in range(30, 36):
        (out / f"v{slot}.ts").write_bytes(b"x" * 1000)
    feed.packer = fake_packer(out, first=30)

    where = grid.start(30)
    assert feed.front(where) == grid.end(35), "готовы сегменты 30…35 — запас до конца 35-го"
    assert feed.weight() == 6000


def test_the_lead_is_counted_from_the_receiver_and_breaks_on_a_hole(tmp_path: Path) -> None:
    """§7.4-2: запас — это то, что лежит ПОДРЯД перед приёмником, а не глоб каталога.

    Ровно на этом числе стоит сторож приёмника, и врало оно после каждой перемотки назад:
    в каталоге показа лежат честные куски прошлых прогонов (сетка детерминирована, §6.0),
    и «докуда упаковано» считалось по ним. Замер на живом Q70D 06-08-2026: откат с 31-й
    минуты на 10-ю дал «показ 600 · упаковано 2010 · впереди 1410 с» при пустом месте
    перед приёмником — то есть разрешение сторожу дёргать показ ровно тогда, когда нельзя.
    """
    out = hls_dir(str(tmp_path / "hls"))
    grid = Grid.uniform(600.0, 10.0)
    feed = Feed(source="", audio=0, out=out, grid=grid)
    for slot in (*range(30, 36), 40, 41):  # куски прошлого прогона и дырка перед ними
        (out / f"v{slot}.ts").write_bytes(b"x")
    feed.packer = fake_packer(out, first=30)

    assert feed.front(5.0) == 5.0, "перед приёмником пусто — запаса нет, что бы ни лежало дальше"
    assert feed.front(grid.start(30)) == grid.end(35), "цепочка обрывается на дырке, а не на 41"
    assert feed.front(grid.start(40)) == grid.end(41), "считаем от приёмника, а не от начала"


def test_a_real_ca_signed_cert_is_verified_against_the_system_store(
    tls: tuple[str, str], tmp_path: Path
) -> None:
    """Чему доверяет mock: §9 «Chromecast требует доверенный HTTPS».

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
        ("leaf", "/CN=torrcast.anysda.space", "inter", []),
    ):
        run("req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key[name]),
            "-out", str(csr[name]), "-subj", subject)  # fmt: skip
        run("x509", "-req", "-in", str(csr[name]), "-CA", str(crt[issuer]),
            "-CAkey", str(key[issuer]), "-days", "5", "-out", str(crt[name]), *extra)  # fmt: skip
    return crt["root"].read_text(), crt["inter"].read_text(), crt["leaf"].read_text()


def test_the_position_is_warmed_by_its_byte_offset_not_by_a_proportion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Продолжение с середины греет ровно то место файла, где лежит позиция (§7.2 SPEC-v2).

    Смещение берётся из карты опорных кадров — той же, по которой строится сетка. Долей
    «позиция от длительности, умноженная на размер файла» тут обойтись нельзя: битрейт по
    фильму гуляет вдвое, и промах в один процент двухгигабайтного файла — это 20 МБ, то
    есть прогрев чужого места и отобранная у показа полоса.
    """
    from torrcast import stream as stream_module
    from torrcast.stream import HEAD_OPEN, FilmKeys, warm_file

    keys = FilmKeys(600.0, [0.0, 100.0, 200.0, 300.0], [0, 90 << 20, 500 << 20, 505 << 20], "mp4")
    # 200-я секунда — ровно половина фильма, а лежит она на 500 МБ из 505: пропорция
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


def test_the_head_warmed_under_the_question_is_sized_by_the_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Голова под «Продолжить?» меряется контейнером, а не запасом под ``moov`` (§7.3).

    У mp4 в голове лежит ``moov`` (у «Моаны 2» от YTS — 5.3 МБ), и без него ffmpeg вход
    не откроет. У mkv там EBML-заголовок, SeekHead, Info и Tracks — килобайты, а восемь
    мегабайт чужого начала на холодном рое съедали весь бюджет раздумья: до места позиции
    дело не доходило вовсе.
    """
    from torrcast import stream as stream_module
    from torrcast.stream import HEAD_OPEN, FilmKeys, head_open, warm_file

    assert head_open("mkv") < head_open("mp4"), "у mkv голова меньше — это и есть правка"
    assert head_open("") == stream_module.HEAD_OPEN_DEFAULT, "контейнер не известен — с запасом"

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
    assert asked[0] == (0, HEAD_OPEN["mkv"]), "имя файла назвало контейнер — греем по нему"
