"""Формат потока §3 и раздача HLS: то, на чём ресивер молча ломается.

Проверяется ровно то, что зафиксировано ТЗ и реестром ТВ-рисков §9: TS-сегменты по 4 с,
один вариант, видео copy, аудио всегда AAC stereo 192k, EVENT-манифест, CORS на всех
ответах (включая 404 и preflight) и Range на сегментах.

Раздача идёт по http на голом IP (§5 SPEC-v2) — так же, как её видит телевизор.
https проверяется отдельно: это выключенная опция, но она обязана оставаться рабочей.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from torrcast.cast import Report
from torrcast.stream import (
    Feed,
    HlsServer,
    ffmpeg_hls_command,
    hls_dir,
    parse_manifest,
    vod_manifest,
)


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
    return root, Feed(source="", audio=0, out=root, duration=8.0)


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


def test_stream_format_is_the_one_fixed_by_the_spec() -> None:
    command = ffmpeg_hls_command("http://ts/stream", audio_index=1, out_dir="/dev/shm/torrcast")
    text = " ".join(command)
    assert "-c:v copy" in text, "видео только copy — перекодировать 1080p нам нечем"
    assert "-c:a aac -ac 2 -b:a 192k" in text, "AC3/DTS passthrough запрещён (§3)"
    assert "-map 0:v:0 -map 0:a:1" in text, "один вариант и выбранная дорожка по индексу"
    assert "-hls_time 4" in text and "-hls_segment_type mpegts" in text
    assert "-hls_segment_filename /dev/shm/torrcast/v%d.ts" in text, "имя = место в фильме"


def test_segments_are_cut_by_the_clock_and_keep_the_original_timestamps() -> None:
    """§2.1 SPEC-v2: сетка манифеста держится на двух флагах, и оба обязательны.

    ``split_by_time`` — резать ровно по 4 с, а не по ключевым кадрам: иначе сегменты
    «сколько дал GOP» (на «Моане 2» от 1.0 до 11.5 с) разъезжаются с манифестом тем
    сильнее, чем дальше от начала, и seek попадает мимо. ``-copyts`` — оставить исходные
    метки времени: без него ffmpeg сбрасывает их в ноль на каждом ``-ss``, и приёмник
    считал бы позицию от начала куска, а не от начала фильма.

    ``independent_segments`` при этом стоять НЕ должен: сегмент больше не начинается с
    ключевого кадра, и обещать приёмнику обратное — врать.
    """
    text = " ".join(ffmpeg_hls_command("http://ts/stream", 0, "/tmp/x"))
    assert "split_by_time" in text and "temp_file" in text
    assert "independent_segments" not in text
    assert "-copyts" in text


def test_packing_starts_at_the_requested_slot_and_names_files_by_place() -> None:
    """Упаковка с середины (перемотка, resume): ``-ss`` на входе, номера файлов — с места.

    Без ``-start_number`` ffmpeg считал бы сегменты с нуля, и место в фильме перестало бы
    читаться по имени файла — а именно на этом держится манифест на всю длительность.
    """
    command = ffmpeg_hls_command("http://ts/stream", 0, "/tmp/x", start_slot=300)
    assert command[command.index("-ss") + 1] == "1200.000", "сегмент 300 = 1200-я секунда"
    assert command.index("-ss") < command.index("-i")
    assert command[command.index("-start_number") + 1] == "300"
    assert "-ss" not in ffmpeg_hls_command("http://ts/stream", 0, "/tmp/x")


def test_the_manifest_promises_the_whole_film_so_the_tv_has_a_timeline() -> None:
    """§2.1 SPEC-v2: длительность в MEDIA_STATUS = сумме ``EXTINF``, значит она обязана
    быть длиной фильма, а не длиной упакованного.

    Хвост короче сегмента идёт отдельной строкой: без него манифест врал бы о конце
    фильма на эти секунды, а с ``ENDLIST`` приёмник считает манифест VOD — со шкалой,
    общим временем и перемоткой в любую точку (проверено на живом Q70D).
    """
    text = vod_manifest(5978.5)
    segments, ended = parse_manifest(text)
    assert ended, "без ENDLIST для приёмника это эфир: ни шкалы, ни перемотки"
    assert "#EXT-X-PLAYLIST-TYPE:VOD" in text
    assert abs(sum(seconds for _, seconds in segments) - 5978.5) < 0.001
    assert len(segments) == 1495  # 1494 целых сегмента и хвост 2.5 с
    assert segments[0][0] == "v0.ts" and segments[-1][0] == "v1494.ts"
    assert parse_manifest(vod_manifest(20.0))[0] == [(f"v{n}.ts", 4.0) for n in range(5)]


def test_readrate_paces_packing_and_can_be_switched_off() -> None:
    assert "-readrate" in ffmpeg_hls_command("u", 0, "/tmp/x", readrate=1.0)
    assert "-readrate" not in ffmpeg_hls_command("u", 0, "/tmp/x", readrate=0.0)


def test_the_initial_burst_replaces_pausing_the_packer(tmp_path: Path) -> None:
    """§6 SPEC-v2: запас впереди приёмника даёт burst, а не пауза процесса.

    Проверяем и то, и другое: флаг ``-readrate_initial_burst`` (ffmpeg ≥ 6.1) на месте и
    стоит до ``-i``, а сигналов остановки в коде показа не осталось вовсе — именно под
    SIGSTOP'ом приёмник намертво вис в BUFFERING при живых сегментах на диске.
    """
    from torrcast import cast as cast_module
    from torrcast import cli as cli_module
    from torrcast import stream as stream_module

    command = ffmpeg_hls_command("u", 0, "/tmp/x", readrate=1.0, burst=60.0)
    assert "-readrate 1 -readrate_initial_burst 60" in " ".join(command)
    assert command.index("-readrate_initial_burst") < command.index("-i")
    assert "-readrate_initial_burst" not in ffmpeg_hls_command("u", 0, "/tmp/x", readrate=0.0)

    # В доках про SIGSTOP написано — важно, чтобы его не осталось в КОДЕ показа.
    for module in (stream_module, cli_module, cast_module):
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        assert "send_signal" not in source, f"{module.__name__}: показ шлёт сигналы упаковке"


def test_a_request_for_an_unpacked_place_repacks_instead_of_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§2.1 SPEC-v2: приёмник мотает сам, а упаковка идёт за ним.

    Запрос сегмента, которого нет, — это и есть перемотка, и единственный правильный
    ответ на неё — начать паковать оттуда. 404 тут запрещён: ресивер, поймавший его,
    отказывается брать LOAD ещё пару минут (замерено 05-08-2026).
    """
    from torrcast.stream import Feed

    root = hls_dir(str(tmp_path / "hls"))
    started: list[int] = []
    monkeypatch.setattr(Feed, "restart", lambda self, slot: started.append(slot))
    feed = Feed(source="", audio=0, out=root, duration=7200.0, wait=0.0)

    assert feed.segment(900) is None, "файла нет и упаковка мгновенной не бывает"
    assert started == [900], "перемотка на 3600-ю секунду = упаковка с сегмента 900"

    (root / "v900.ts").write_bytes(b"x")
    assert feed.segment(900) == root / "v900.ts", "готовый кусок отдаём не думая"


def test_a_burst_of_requests_after_a_seek_restarts_packing_only_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Живой Q70D после ``seek`` просит шесть сегментов за одну секунду (замерено: v50…v55).

    Перезапустить упаковку обязан ровно первый из них: шесть ffmpeg'ов подряд на одном
    месте — это шесть заходов в рой и потерянные секунды на каждом.
    """
    from torrcast.stream import Feed

    root = hls_dir(str(tmp_path / "hls"))
    started: list[int] = []
    monkeypatch.setattr(Feed, "restart", lambda self, slot: started.append(slot))
    feed = Feed(source="", audio=0, out=root, duration=7200.0, wait=0.0)

    for slot in range(50, 56):
        feed.segment(slot)

    assert started == [50], "остальные пять — префетч того же места, а не пять перемоток"


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
    for path in ("/", "/../../etc/passwd", "/index.m3u8.tmp", "/config.json"):
        assert session.get(f"{base}{path}", timeout=10).status_code == 404, path


def test_manifest_is_parsed_into_segments_and_the_end_marker() -> None:
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
    и «45 штук» оказывались то четырьмя минутами, то сорока секундами. Теперь сегмент
    ровно 4 с и его номер — это его место в фильме, так что окно считается арифметикой.
    """
    from torrcast.stream import Feed

    out = hls_dir(str(tmp_path / "hls"))
    for slot in range(0, 60):
        (out / f"v{slot}.ts").write_bytes(b"x")
    feed = Feed(source="", audio=0, out=out, duration=7200.0, keep=40.0)

    feed.prune(played=200.0)  # показ на 200-й секунде, окно 40 с — всё до 160-й не нужно
    left = sorted(int(p.name[1:-3]) for p in out.glob("v*.ts"))
    assert left == list(range(40, 60)), "сегменты позади окна убраны, окно и запас целы"

    feed.prune(played=10.0)
    assert len(list(out.glob("v*.ts"))) == 20, "в начале показа не удаляется ничего"


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
