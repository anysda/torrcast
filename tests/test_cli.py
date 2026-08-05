"""Меню §2.1: порядок релизов, дефолт по Enter и рендер таблицы."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, cast

import pytest

from torrcast import InfraError, NotFoundError, cli
from torrcast.cli import TABLE_LIMIT, is_candidate, is_disc, rank_releases, render_table, warned
from torrcast.console import Progress
from torrcast.parse import Release
from torrcast.state import load_config
from torrcast.stream import RUNTIME_GUESS, Media, TorrFile

RUNTIME = RUNTIME_GUESS["movie"]
GB = 1024**3


def rel(
    name: str = "Кино / Movie (1999) BDRip 1080p",
    *,
    codec: str | None = "H.264",
    quality: str | None = "1080p",
    size_gb: float = 8.0,
    seeders: int = 100,
    voices: tuple[str, ...] = ("Дубляж",),
) -> Release:
    return Release(
        raw_name=name,
        title="Кино",
        year=1999,
        quality=quality,
        codec=codec,
        voices=voices,
        size=int(size_gb * GB),
        seeders=seeders,
        # Свой magnet на релиз: без него раздачи неразличимы, а подготовка их греет
        # параллельно — и тест не может сказать, про какую именно раздача ffprobe.
        magnet=f"magnet:?xt=urn:btih:{abs(hash(name)):x}",
    )


def test_hevc_is_marked_and_h264_is_not() -> None:
    assert warned(rel(codec="HEVC", size_gb=4), RUNTIME, 20.0) == "не берём"
    assert warned(rel(codec="H.264", size_gb=4), RUNTIME, 20.0) == ""


def test_fat_bitrate_is_marked_even_for_h264() -> None:
    """~28 ГБ на два часа — это 33 Мбит/с, потолок декодера Q70D ~20 (§3)."""
    assert warned(rel(size_gb=28), RUNTIME, 20.0) == "тяжёлый"
    assert warned(rel(codec="HEVC", size_gb=28), RUNTIME, 20.0) == "не берём, тяжёлый"


def test_default_is_the_most_seeded_candidate() -> None:
    """Enter = самый обсиженный кандидат; HEVC кандидатом не бывает никогда (§2.1, §3)."""
    top = rel(name="top", seeders=900)
    hevc = rel(name="hevc", codec="HEVC", seeders=800)
    good = rel(name="good", seeders=200)
    meh = rel(name="meh", seeders=10)
    order = [r.raw_name for r in rank_releases([hevc, meh, top, good], RUNTIME, 20.0)]
    assert order == ["top", "good", "meh", "hevc"]


def test_hd_source_without_codec_is_a_candidate() -> None:
    """Кодек в имени раздачи чаще молчит: WEB-DL и BDRip засчитываются кандидатами,
    DVDRip и CAM — нет (правка дефолта, docs/stage2.md §открытые вопросы 2).
    """
    web = Release(raw_name="WEB-DL", title="Кино", source="WEB-DL", size=4 * GB, seeders=10)
    dvd = Release(raw_name="DVDRip", title="Кино", source="DVDRip", size=1 * GB, seeders=900)
    assert is_candidate(web, RUNTIME, 20.0) and not is_candidate(dvd, RUNTIME, 20.0)
    assert rank_releases([dvd, web], RUNTIME, 20.0)[0].raw_name == "WEB-DL"


def test_seeded_dvdrip_does_not_beat_a_live_1080p() -> None:
    """Ни кодека, ни качества в имени — не кандидат, и толпа сидов дефолта не даёт."""
    dvd = rel(name="DVDRip", codec=None, quality=None, size_gb=1.4, seeders=800)
    hd = rel(name="1080p", seeders=40)
    assert rank_releases([dvd, hd], RUNTIME, 20.0)[0].raw_name == "1080p"
    # Живого 1080p нет вовсе — берём просто самый обсиженный, DVDRip годится.
    sd = rel(name="ещё DVDRip", codec=None, quality=None, size_gb=1.4, seeders=5)
    assert rank_releases([sd, dvd], RUNTIME, 20.0)[0].raw_name == "DVDRip"


def test_fat_release_stays_in_the_table_but_never_becomes_the_default() -> None:
    """Больше ~20 Мбит/с ресивер не тянет: релиз в таблице есть, но помечен и не дефолт."""
    fat = rel(name="remux", size_gb=28, seeders=900)
    thin = rel(name="1080p", size_gb=8, seeders=30)
    assert not is_candidate(fat, RUNTIME, 20.0) and is_candidate(thin, RUNTIME, 20.0)
    ranked = rank_releases([fat, thin], RUNTIME, 20.0)
    assert ranked[0].raw_name == "1080p"
    assert "remux" in [r.raw_name for r in ranked]
    assert warned(fat, RUNTIME, 20.0) == "тяжёлый"


def test_disc_images_never_become_the_default() -> None:
    """В VIDEO_TS/BDMV нет цельного файла — стримить нечего, дефолтом быть не может."""
    disc = rel(name="Тачки / Cars (2006) DVD-Video", seeders=500)
    plain = rel(name="Тачки / Cars (2006) BDRip 1080p", seeders=5)
    assert is_disc(disc) and not is_disc(plain)
    assert rank_releases([disc, plain], RUNTIME, 20.0)[0].raw_name.endswith("BDRip 1080p")


def test_ordinary_release_is_not_mistaken_for_a_disc() -> None:
    assert not is_disc(rel(name="Кино (1999) BDRip 1080p x264 от Мутный"))
    assert is_disc(rel(name="Кино (1999) Blu-Ray Disc 1080p"))


def test_table_has_all_columns_of_the_spec() -> None:
    text = render_table([rel(seeders=214, voices=("Дубляж",))], RUNTIME, 20.0)
    lines = text.splitlines()
    assert lines[0] == "Релизы:"
    assert lines[1].split() == ["№", "Качество", "Размер", "Сиды", "Озвучка", "Кодек"]
    assert lines[2].split() == ["1", "1080p", "8.0", "ГБ", "214", "Дубляж", "H.264"]


def test_table_marks_hevc_row() -> None:
    text = render_table([rel(codec="HEVC", size_gb=28, seeders=45)], RUNTIME, 20.0)
    assert text.splitlines()[2].endswith("HEVC не берём, тяжёлый")


def test_table_columns_line_up() -> None:
    releases = [
        rel(seeders=1, voices=("Дубляж",)),
        rel(seeders=1000, voices=("Дубляж", "Original")),
    ]
    rows = render_table(releases, RUNTIME, 20.0).splitlines()[1:]
    assert len({len(row.rstrip()) - len(row.rstrip().rsplit("  ", 1)[-1]) for row in rows}) == 1


def test_table_shows_only_the_head_of_a_long_list() -> None:
    releases = [rel(name=f"r{i}", seeders=100 - i) for i in range(TABLE_LIMIT + 7)]
    text = render_table(releases, RUNTIME, 20.0)
    assert len(text.splitlines()) == TABLE_LIMIT + 3  # заголовок, шапка, строки, хвост
    assert "и ещё 7 с меньшим числом сидов" in text


def test_missing_values_are_shown_as_dashes() -> None:
    text = render_table([rel(codec=None, quality=None, size_gb=0, voices=())], RUNTIME, 20.0)
    row = text.splitlines()[2]
    assert "—" in row and "?" in row


@pytest.mark.parametrize("size_gb,expected", [(4.0, ""), (28.0, "тяжёлый")])
def test_bitrate_threshold_is_configurable(size_gb: float, expected: str) -> None:
    assert warned(rel(size_gb=size_gb), RUNTIME, 20.0) == expected


class _FakeTorrServer:
    """TorrServer ровно в том объёме, в каком его дёргает подготовка релиза."""

    def __init__(self, files: list[TorrFile] | None = None, dead: set[str] | None = None) -> None:
        self.dropped: list[str] = []
        self.files = files if files is not None else [TorrFile(0, "movie.mkv", 4 * GB)]
        self.dead = dead or set()

    def add(self, magnet: str) -> str:
        return f"hash-{magnet}"

    def wait_files(self, torrent_hash: str, timeout: float = 60.0) -> list[TorrFile]:
        if torrent_hash in self.dead:  # раздача с мёртвым роем: пиров нет и не будет
            raise InfraError(f"раздача не отдала метаданные за {timeout:.0f} с — нет пиров")
        return self.files

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"http://ts/{torrent_hash}/{index}"

    def drop(self, torrent_hash: str) -> None:
        self.dropped.append(torrent_hash)


def _probes(monkeypatch: pytest.MonkeyPatch, releases: list[Release], *codecs: str) -> None:
    """Подсунуть ffprobe: по кодеку на релиз, считая от лучшего.

    ⚠️ Раздавать кодеки по порядку ВЫЗОВОВ нельзя: прогрев греет запасной релиз
    параллельно с основным, и кто из потоков дошёл до ffprobe первым — дело случая.
    Поймано 06-08-2026: тест «три негодных подряд» развалился от того, что в подготовке
    появился лишний вызов перед probe. Поэтому кодек привязан к самой раздаче: её magnet
    виден в адресе потока, а место в очереди известно заранее.
    """

    def read(url: str, timeout: float = 90.0) -> Media:
        for number, release in enumerate(releases):
            if f"hash-{release.magnet}/" in url and number < len(codecs):
                return Media(3600.0, (), codecs[number])
        return Media(3600.0, (), "h264")

    monkeypatch.setattr(cli, "probe", read)


def _plan(ranked: list[Release]) -> Any:
    from torrcast.parse import Picture

    picture = Picture(title="Кино", year=1999, releases=ranked)
    return cli._Plan(picture=picture, ranked=ranked, runtime=RUNTIME, warn_mbit=20.0)


def _resolve(bench: Any, ranked: list[Release], **flags: Any) -> Any:
    args = cli.Args(query=["кино"], **flags)
    with Progress(out=io.StringIO()) as progress:
        return bench.resolve(_plan(ranked), args, progress)


def test_a_release_that_turns_out_not_to_be_h264_is_swapped_out_loudly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Имя раздачи о кодеке молчит, а видео мы отдаём copy: настоящий кодек решает.
    Не h264 — честная строка и следующий кандидат, молчаливых подмен не бывает (§1).
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "hevc", "h264")
    torrserver = _FakeTorrServer()
    prep = _resolve(cli._Bench(cast(Any, torrserver)), ranked)

    assert (prep.number, prep.found.video) == (2, "h264")
    assert prep.want.name == "movie.mkv"
    assert "релиз №1 не годится (hevc) — беру №2" in capsys.readouterr().out
    assert torrserver.dropped, "неподошедшая раздача из TorrServer убирается"


def test_a_dead_swarm_is_not_a_hang_but_the_next_release(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Дефект №1 владельца (§1 SPEC-v2): «Дорожки: читаю поток…» и тишина навсегда.

    Раздача с мёртвым роем обязана стоить одной строки и перехода к следующему релизу,
    а не молчаливого зависания без прогресса и без таймаута.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "h264")
    torrserver = _FakeTorrServer(dead={"hash-magnet-r0"})
    monkeypatch.setattr(Release, "magnet", property(lambda self: f"magnet-{self.raw_name}"))

    prep = _resolve(cli._Bench(cast(Any, torrserver)), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 2, "мёртвая раздача не останавливает показ"
    assert "релиз №1 не годится (раздача не отдала метаданные" in printed
    assert "беру №2" in printed


def test_an_explicitly_named_release_is_played_as_asked_with_a_loud_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--release N` неприкосновенен: проверка кодека его не подменяет. Не h264 — громкое
    предупреждение и показ того, что просили (решение оркестратора, stage3 вопрос 1).
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "hevc")
    torrserver = _FakeTorrServer()

    prep = _resolve(cli._Bench(cast(Any, torrserver)), ranked, release=1)

    printed = capsys.readouterr().out
    assert (prep.number, prep.found.video) == (1, "hevc"), "названный релиз не подменяется"
    assert "внимание: видео hevc" in printed and "беру №" not in printed
    assert not torrserver.dropped, "раздача остаётся: её и просили"


def test_three_failed_probes_end_with_an_honest_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Три попытки подряд не дали H.264 — код 1 с объяснением, а не четвёртая попытка."""
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(5)]
    _probes(monkeypatch, ranked, "hevc", "av1", "vc1")
    with pytest.raises(NotFoundError) as caught:
        _resolve(cli._Bench(cast(Any, _FakeTorrServer())), ranked)
    assert "годного релиза нет" in str(caught.value)
    assert "№1 — hevc" in str(caught.value) and "№3 — vc1" in str(caught.value)
    assert capsys.readouterr().out.count("беру №") == 2  # не больше MAX_TRIES попыток


def test_tv_mock_switches_the_receiver_and_leaves_no_tv_address(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`cast --tv mock` — третья команда установки на стенде (§7.5).

    Она обязана переключить приёмник, иначе стенд полез бы кастить на Chromecast.
    И обратно тоже: адрес ТВ возвращает штатный приёмник (§9 — до этапа 6 адреса в
    конфиге нет физически).
    """
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))

    assert cli.main(["--tv", "mock"]) == 0
    config = load_config()
    assert (config.tv, config.receiver) == ("mock", "mock")
    assert "192.168.100" not in (tmp_path / "config.json").read_text()
    assert "headless" in capsys.readouterr().out

    assert cli.main(["--tv", "192.168.100.102"]) == 0
    assert (load_config().tv, load_config().receiver) == ("192.168.100.102", "chromecast")


def test_warmup_leaves_in_torrserver_only_what_we_play(monkeypatch: pytest.MonkeyPatch) -> None:
    """Прогрев греет лишнее по определению — лишнее убирается до старта показа (§4).

    Иначе две-три чужие раздачи продолжали бы качаться в RAM-кэш TorrServer рядом с
    показом и отъедать у него полосу.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "h264")
    monkeypatch.setattr(Release, "magnet", property(lambda self: f"magnet-{self.raw_name}"))
    torrserver = _FakeTorrServer()
    bench = cli._Bench(cast(Any, torrserver))

    prep = _resolve(bench, ranked)
    bench.keep_only(prep)

    assert len(bench.preps) > 1, "запасной релиз греется заранее"
    assert len(torrserver.dropped) == len(bench.preps) - 1
    assert prep.torrent_hash not in torrserver.dropped


def test_a_seeded_avi_no_longer_wins_the_top() -> None:
    """Живая «Моана 2» (выдача 06-08-2026): 221 сид против 140 — и всё равно не дефолт.

    Первым стоял ``Моана 2 … WEB-DL] Dub (MovieDalen)``, 1.46 ГБ: в заголовке ни кодека,
    ни разрешения, а внутри ``Moana.2.2024.WEB-DLRip.ELEKTRI4KA.avi`` — mpeg4, который
    ffprobe закономерно отбраковывал, потратив 2–5 с живого старта.
    """
    avi = rel(
        name="Моана 2 / Moana 2 [2024, США, Канада, мультфильм, приключения,WEB-DL] Dub",
        codec=None,
        quality=None,
        size_gb=1.46,
        seeders=221,
    )
    avc = rel(
        name="Моана 2 / Moana 2 [2024, США, Канада, мультфильм, WEB-DL-AVC] 2x Dub",
        size_gb=3.14,
        seeders=140,
    )
    ranked = rank_releases([avi, avc], RUNTIME, 20.0)
    assert ranked[0] is avc, "верх — годный WEB-DL-AVC"
    assert ranked[1] is avi, "и всё же не выкинут: судья по-прежнему ffprobe"
    assert cli.is_dated(avi, RUNTIME) and not cli.is_dated(avc, RUNTIME)


def test_a_small_release_that_names_its_codec_is_not_old_junk() -> None:
    """1.46 ГБ — ещё не приговор: у rutracker такой же бюджет у AVC-раздач.

    «Моана» 2016 ``BDRip-AVC`` весит те же 1.46 ГБ и те же 1.7 Мбит/с, что и .avi
    рядом. Разделяет их одно: назван кодек или нет.
    """
    named = rel(name="BDRip-AVC", quality=None, size_gb=1.46, seeders=131)
    assert not cli.is_dated(named, RUNTIME)


def test_a_series_pack_is_never_judged_by_its_bitrate() -> None:
    """У сериала в раздаче лежит сезон целиком — «мало мегабит» про него ничего не значит."""
    pack = Release(
        raw_name="Сериал / Series [S01E1-8 of 8, WEB-DL]",
        title="Сериал",
        source="WEB-DL",
        kind="tv",
        size=int(6 * GB),
        seeders=110,
    )
    assert not cli.is_dated(pack, RUNTIME)


def test_dated_sinks_below_candidates_but_above_hevc() -> None:
    """Ступень «старьё» вклинена МЕЖДУ годностью и сидами, группы местами не меняются.

    Случай живой: «Матрица: Перезагрузка» 06-08-2026 — ``DVDRip-AVC`` на 47 сидов
    стоял первым и обгонял HDTV-мастер на 30. Кодек назван, значит релиз годный и из
    очереди не выпадает; но верхом ему быть больше не с чего.
    """
    dated = Release(
        raw_name="DVDRip-AVC", title="Кино", codec="H.264", source="DVDRip",
        size=3 * GB, seeders=900,
    )  # fmt: skip
    good = rel(name="web-dl", seeders=10)
    hevc = rel(name="hevc", codec="HEVC", seeders=800)
    disc = rel(name="Кино (1999) DVD-Video", seeders=999)
    order = [r.raw_name for r in rank_releases([disc, dated, hevc, good], RUNTIME, 20.0)]
    assert order == ["web-dl", "DVDRip-AVC", "hevc", "Кино (1999) DVD-Video"]
    assert is_candidate(dated, RUNTIME, 20.0), "старьё остаётся годным — судит ffprobe"


def _franchise_plan(title: str, year: int, releases: list[Release]) -> Any:
    from torrcast.parse import Picture

    return cli._Plan(
        picture=Picture(title=title, year=year, releases=releases),
        ranked=rank_releases(releases, RUNTIME, 20.0),
        runtime=RUNTIME,
        warn_mbit=20.0,
    )


def _moana_franchise() -> list[Any]:
    """Франшиза «моана» из живой выдачи 06-08-2026, сведённая к верху отбора каждой картины."""
    return [
        _franchise_plan(
            "Моана: романтика золотого века",
            1926,
            [rel(name="vhs", codec=None, quality=None, size_gb=0.71, seeders=5)],
        ),
        _franchise_plan("Моана", 2016, [rel(name="web-dl 1080p", size_gb=4.17, seeders=222)]),
        _franchise_plan(
            "Моана 2", 2024, [rel(name="web-dl-avc", quality=None, size_gb=3.14, seeders=140)]
        ),
    ]


def test_menu_default_points_at_the_liveliest_picture() -> None:
    """Живая «моана» 06-08-2026: список хронологический, а дефолт — вторым пунктом.

    Первым в хронологии стоит «Моана: романтика золотого века» (1926) — немое
    документальное кино, один VHS-рип на 5 сидов. Enter на ней не давал ничего.
    """
    plans = _moana_franchise()
    assert [cli.liveliness(p) for p in plans] == [0, 222, 140]
    assert cli.liveliest(plans) == 2


def test_a_picture_with_nothing_playable_weighs_nothing() -> None:
    """«Тачки» 2006 в живой выдаче — 41 ГБ 4K-ремукса (49.9 Мбит/с) и образы DVD.

    Играть нечего, сколько бы сидов ни было: дефолт обязан уйти на картину, которая
    реально запустится.
    """
    fat = _franchise_plan("Тачки", 2006, [rel(name="uhd bdremux", size_gb=41.8, seeders=106)])
    live = _franchise_plan("Тачки 3", 2017, [rel(name="web-dl 1080p", size_gb=4.59, seeders=121)])
    assert cli.liveliness(fat) == 0
    assert cli.liveliest([fat, live]) == 2


def test_an_equal_race_is_won_by_chronology() -> None:
    """Ничья по сидам — берём раннюю картину: список и так хронологический."""
    first = _franchise_plan("Кино", 2001, [rel(name="a", seeders=100)])
    second = _franchise_plan("Кино 2", 2005, [rel(name="b", seeders=100)])
    assert cli.liveliest([first, second]) == 1


def test_prewarm_starts_with_the_default_not_with_the_earliest() -> None:
    """Греем то, во что попадёт Enter: иначе прогрев под меню греет чужую картину.

    У «моаны» дефолт — вторая картина из четырёх, у «аватара» — девятая из десяти,
    а под меню греются только первые :data:`~torrcast.cli.PREWARM`.
    """
    plans = _moana_franchise()
    assert [p.picture.year for p in cli.warm_order(plans)] == [2016, 1926, 2024]
