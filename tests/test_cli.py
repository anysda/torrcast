"""Меню релизов: порядок кандидатов, дефолт по Enter и рендер таблицы."""

from __future__ import annotations

import io
import re
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from torrcast import InfraError, NotFoundError, cli, console, scan
from torrcast.cli import TABLE_LIMIT, is_candidate, is_disc, rank_releases, render_table, warned
from torrcast.console import Progress
from torrcast.parse import Kind, Release, parse_release_name
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
        # параллельно - и тест не может сказать, про какую именно раздача ffprobe.
        magnet=f"magnet:?xt=urn:btih:{abs(hash(name)):x}",
    )


def test_hevc_is_marked_and_h264_is_not() -> None:
    assert warned(rel(codec="HEVC", size_gb=4), RUNTIME, 20.0) == "не берём"
    assert warned(rel(codec="H.264", size_gb=4), RUNTIME, 20.0) == ""


def test_the_table_promises_to_recode_hevc_instead_of_refusing_it() -> None:
    """Перекодирование включено — HEVC играет, и таблица обязана говорить то же самое.

    «Не берём» рядом с релизом, который на самом деле возьмётся и поедет на ТВ, — это
    та же молчаливая подмена, только наоборот: человек выберет другой релиз зря.
    """
    hevc = rel(codec="HEVC", size_gb=4)
    assert warned(hevc, RUNTIME, 20.0, recode_at=10.0) == "перекодирую целиком"
    assert warned(hevc, RUNTIME, 20.0) == "не берём", "без перекодирования отказ честен"


def test_fat_bitrate_is_marked_even_for_h264() -> None:
    """~28 ГБ на два часа — это 33 Мбит/с, а потолок декодера Q70D около 20."""
    assert warned(rel(size_gb=28), RUNTIME, 20.0) == "тяжёлый"
    assert warned(rel(codec="HEVC", size_gb=28), RUNTIME, 20.0) == "не берём, тяжёлый"


def test_default_is_the_most_seeded_candidate() -> None:
    """Enter = самый обсиженный кандидат; HEVC кандидатом не бывает никогда."""
    top = rel(name="top", seeders=900)
    hevc = rel(name="hevc", codec="HEVC", seeders=800)
    good = rel(name="good", seeders=200)
    meh = rel(name="meh", seeders=10)
    order = [r.raw_name for r in rank_releases([hevc, meh, top, good], RUNTIME, 20.0)]
    assert order == ["top", "good", "meh", "hevc"]


def test_hd_source_without_codec_is_a_candidate() -> None:
    """Кодек в имени раздачи чаще молчит: WEB-DL и BDRip засчитываются кандидатами,
    DVDRip и CAM — нет.
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
    # Живого 1080p нет вовсе - берём просто самый обсиженный, DVDRip годится.
    sd = rel(name="ещё DVDRip", codec=None, quality=None, size_gb=1.4, seeders=5)
    assert rank_releases([sd, dvd], RUNTIME, 20.0)[0].raw_name == "DVDRip"


def test_fat_release_stays_in_the_table_but_never_becomes_the_default() -> None:
    """Тяжелее потолка отбора (тут он задан 20 Мбит/с) - релиз в таблице есть, но помечен
    и не дефолт.

    ⚠️ Число тут аргумент теста, а не свойство приёмника: рабочий потолок битрейта
    Samsung Q70D - ~10 Мбит/с (замер; «~20» было легендой), и живёт он в его профиле
    (:attr:`torrcast.profile.Profile.recode_at_mbit`).
    """
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


def test_table_has_all_the_columns() -> None:
    text = render_table([rel(seeders=214, voices=("Дубляж",))], RUNTIME, 20.0)
    lines = text.splitlines()
    assert lines[0] == "Релизы:"
    assert lines[1].split() == ["N", "Качество", "Размер", "Сиды", "Озвучка", "Кодек"]
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
    assert "-" in row and "?" in row


@pytest.mark.parametrize("size_gb,expected", [(4.0, ""), (28.0, "тяжёлый")])
def test_bitrate_threshold_is_configurable(size_gb: float, expected: str) -> None:
    assert warned(rel(size_gb=size_gb), RUNTIME, 20.0) == expected


def test_the_ceiling_is_sixteen_because_the_tv_rebuffers_at_eighteen() -> None:
    """Потолок битрейта опущен по живому замеру на Q70D.

    17.8 Мбит/с телевизор играет с ребуфером раз в 30–60 с, и каждый подвис
    стоит 8 с пропущенного фильма. Поэтому дефолт опущен 20 → 16: смотрибельность важнее
    пиковой чёткости. Руками (``--release N``) тяжёлый релиз берётся по-прежнему, и
    молчком это не делается — в таблице он помечен «тяжёлый».
    """
    from torrcast.state import Config

    assert Config().bitrate_warn_mbit == 16.0
    fat = rel(size_gb=17.8 * RUNTIME / 8 / 1024**3 * 1e6)  # ровно 17.8 Мбит/с
    assert not is_candidate(fat, RUNTIME, Config().bitrate_warn_mbit), "Enter его не возьмёт"
    assert warned(fat, RUNTIME, Config().bitrate_warn_mbit) == "тяжёлый", "но и не спрячет"
    assert is_candidate(rel(size_gb=13.0), RUNTIME, Config().bitrate_warn_mbit), "15.5 Мбит/с ок"


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
            raise InfraError(f"раздача не отдала метаданные за {timeout:.0f} с - нет пиров")
        return self.files

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"http://ts/{torrent_hash}/{index}"

    def drop(self, torrent_hash: str) -> None:
        self.dropped.append(torrent_hash)


def _probes(monkeypatch: pytest.MonkeyPatch, releases: list[Release], *codecs: str) -> None:
    """Подсунуть ffprobe: по кодеку на релиз, считая от лучшего.

    ⚠️ Раздавать кодеки по порядку ВЫЗОВОВ нельзя: прогрев греет запасной релиз
    параллельно с основным, и кто из потоков дошёл до ffprobe первым — дело случая.
    Так уже ловилось: тест «три негодных подряд» развалился от того, что в подготовке
    появился лишний вызов перед probe. Поэтому кодек привязан к самой раздаче: её magnet
    виден в адресе потока, а место в очереди известно заранее.
    """

    def read(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        for number, release in enumerate(releases):
            if f"hash-{release.magnet}/" in url and number < len(codecs):
                return Media(3600.0, (), codecs[number])
        return Media(3600.0, (), "h264")

    monkeypatch.setattr(cli, "probe", read)


def _plan(ranked: list[Release], recode_at: float = 10.0) -> Any:
    from torrcast.parse import Picture

    picture = Picture(title="Кино", year=1999, releases=ranked)
    # ``recode_at`` не украшение: в бою перекодирование включено (:class:`Config`), и
    # именно от него зависит, отказ HEVC или сплошной перекод. Ноль - «перекодирование
    # выключено», и тогда поведение обязано остаться прежним.
    return cli._Plan(
        picture=picture, ranked=ranked, runtime=RUNTIME, warn_mbit=20.0, recode_at=recode_at
    )


def _resolve(bench: Any, ranked: list[Release], recode_at: float = 10.0, **flags: Any) -> Any:
    args = cli.Args(query=["кино"], **flags)
    with Progress(out=io.StringIO()) as progress:
        return bench.resolve(_plan(ranked, recode_at), args, progress)


def test_a_release_that_turns_out_not_to_be_h264_is_swapped_out_loudly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Имя раздачи о кодеке молчит, а видео мы отдаём copy: настоящий кодек решает.
    Не h264 — честная строка и следующий кандидат, молчаливых подмен не бывает.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "av1", "h264")
    torrserver = _FakeTorrServer()
    prep = _resolve(cli._Bench(cast(Any, torrserver)), ranked)

    assert (prep.number, prep.found.video) == (2, "h264")
    assert prep.want.name == "movie.mkv"
    assert "релиз 1 не годится (av1) - беру 2" in capsys.readouterr().out
    assert torrserver.dropped, "неподошедшая раздача из TorrServer убирается"


def test_hevc_release_plays_and_says_so_instead_of_being_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """HEVC — не отказ, а сплошной перекод: аниме иначе не играет вовсе.

    До этого верх отбора с HEVC внутри стоил строки «релиз 1 не годится (hevc)», и на
    Nyaa, где HEVC бывает всем, что нашлось, показ кончался «годного релиза нет».
    Теперь такой релиз играет, перекодированный целиком, и об этом говорится вслух.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "hevc", "h264")
    torrserver = _FakeTorrServer()

    prep = _resolve(cli._Bench(cast(Any, torrserver)), ranked)

    printed = capsys.readouterr().out
    assert (prep.number, prep.found.video) == (1, "hevc"), "HEVC-релиз играет, а не отказывает"
    assert "видео hevc - перекодирую на ходу целиком" in printed
    assert "не годится" not in printed and not re.search(r"беру \d", printed)


def test_hevc_is_still_refused_when_recoding_is_switched_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Перекодирование выключено — играть HEVC нечем, и отказ остаётся честным.

    Обратная сторона того же решения: сплошной перекод и есть единственный способ
    показать HEVC на этом приёмнике, поэтому без него релиз годным не становится.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "hevc", "h264")

    prep = _resolve(cli._Bench(cast(Any, _FakeTorrServer())), ranked, recode_at=0.0)

    assert prep.number == 2, "без перекодирования HEVC остаётся отказом"
    assert "релиз 1 не годится (hevc) - беру 2" in capsys.readouterr().out


def test_a_dead_swarm_is_not_a_hang_but_the_next_release(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Так выглядел худший из багов: «Дорожки: читаю поток…» и тишина навсегда.

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
    assert "релиз 1 не годится (раздача не отдала метаданные" in printed
    assert "беру 2" in printed


def test_silent_swarms_do_not_burn_the_tries_meant_for_verdicts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """«Нет пиров» четыре раза подряд — это не повод сдаться: живые ждут ниже в очереди.

    Главная причина 🟡 в замере на тысяче запросов: отбор пробовал ровно три раздачи и
    заканчивал словами «годного релиза нет», хотя рядом в очереди стояли играбельные.
    Перепроверка тех же картин в один поток оживляла шесть из восьми («Кавказская
    пленница», «Зона интересов», «Бесконечная история»).

    Разница между двумя осечками принципиальная: приговор ffprobe («это av1») про релиз
    рассказал всё, а молчание роя — ничего, кроме того, что раздача не отозвалась.
    Попытку жжёт только первое.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(6)]
    _probes(monkeypatch, ranked, "h264")
    monkeypatch.setattr(Release, "magnet", property(lambda self: f"magnet-{self.raw_name}"))
    torrserver = _FakeTorrServer(dead={f"hash-magnet-r{i}" for i in range(4)})

    prep = _resolve(cli._Bench(cast(Any, torrserver)), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 5, "четыре молчаливых роя подряд - и всё же дошли до живого"
    assert printed.count("нет пиров") == 4, "каждая осечка стоит строки, молчаливых нет"
    assert "беру 5" in printed


def test_the_walk_down_the_queue_stops_when_the_start_budget_is_out(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Упорство упорством, а человек сидит у консоли: бюджет фазы отбора конечен.

    Потолок тот же, что был у трёх попыток по полному бюджету раздачи
    (:data:`~torrcast.cli.PICK_BUDGET`), и кончиться он обязан честной строкой, а не
    новым походом в рой.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(6)]
    _probes(monkeypatch, ranked, "h264")
    monkeypatch.setattr(Release, "magnet", property(lambda self: f"magnet-{self.raw_name}"))
    monkeypatch.setattr(cli, "PICK_BUDGET", 0.0)
    torrserver = _FakeTorrServer(dead={f"hash-magnet-r{i}" for i in range(4)})

    with pytest.raises(NotFoundError) as caught:
        _resolve(cli._Bench(cast(Any, torrserver)), ranked)

    assert "годного релиза нет" in str(caught.value) and "нет пиров" in str(caught.value)
    assert "рой у них мёртв" not in str(caught.value), "встали по бюджету - ниже могли быть живые"
    assert capsys.readouterr().out.count("нет пиров") == 1, "бюджет вышел - второго похода нет"


def test_a_fully_walked_queue_of_dead_swarms_is_an_honest_dead_swarm(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Очередь пройдена до конца, а ни одна раздача не отозвалась - это не «годного нет».

    Отказы разные, и человеку с ними разное. «Годного релиза нет» зовёт выбрать руками, но
    выбирать не из чего: раздачи есть и по именам годны, только рой у всех до одной молчит -
    ни метаданных, ни потока. Это не выбор качества, это отсутствие показа, и говорить о нём
    надо прямо. Отличие от :func:`test_the_walk_down_the_queue_stops...`: там встали по
    бюджету и ниже могли лежать живые, а тут очередь именно кончилась.

    «Пиров нет» тут при этом не говорится: сиды у раздач как раз числятся - сотня, - и
    молчание роя с пустой выдачей путать нельзя (:func:`~torrcast.cli.silent_swarm`).
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "h264")
    monkeypatch.setattr(Release, "magnet", property(lambda self: f"magnet-{self.raw_name}"))
    torrserver = _FakeTorrServer(dead={f"hash-magnet-r{i}" for i in range(3)})

    with pytest.raises(NotFoundError) as caught:
        _resolve(cli._Bench(cast(Any, torrserver)), ranked)

    msg = str(caught.value)
    assert "раздач в выдаче 3, потрогали 3 (все)" in msg and "ни одна не отозвалась" in msg
    assert "до 100" in msg, "сиды называются как обещание индексера, а не как факт"
    assert "пиров нет" not in msg, "пиры числятся - врать про пустую выдачу нельзя"
    assert "годного релиза нет" not in msg
    assert capsys.readouterr().out.count("нет пиров") == 3, "каждая раздача стоит строки"


def test_an_explicitly_named_release_is_played_as_asked_with_a_loud_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--release N` неприкосновенен: проверка кодека его не подменяет. Не h264 — громкая
    строка и показ того, что просили.

    🔴 Строка изменилась вместе с решением: раньше тут печаталось «внимание: видео av1 -
    ресивер может не взять, а мы не перекодируем», и это было ровно то враньё, из-за
    которого AV1 и VP9 уезжали на приёмник копией в mpegts. Копией их не отдаём вовсе
    (:meth:`torrcast.profile.Profile.verdict`): раз человек назвал релиз руками, он идёт
    сплошным перекодом, и об этом сказано вслух.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "av1")
    torrserver = _FakeTorrServer()

    prep = _resolve(cli._Bench(cast(Any, torrserver)), ranked, release=1)

    printed = capsys.readouterr().out
    assert (prep.number, prep.found.video) == (1, "av1"), "названный релиз не подменяется"
    assert "видео av1 - перекодирую на ходу целиком" in printed
    assert "не перекодируем" not in printed and not re.search(r"беру \d", printed)
    assert not torrserver.dropped, "раздача остаётся: её и просили"


def test_a_named_hevc_release_is_not_a_warning_but_a_promise_to_recode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--release N` с HEVC внутри: обещание перекода, а не «мы не перекодируем».

    Ровно тут и жила латентная петля: строка про «не перекодируем» врала наполовину —
    показ шёл, тяжёлые куски перекодировались, лёгкие уезжали HEVC как есть, и приёмник
    вставал намертво на границе первого такого куска.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "hevc")

    prep = _resolve(cli._Bench(cast(Any, _FakeTorrServer())), ranked, release=1)

    printed = capsys.readouterr().out
    assert prep.number == 1
    assert "видео hevc - перекодирую на ходу целиком" in printed
    assert "не перекодируем" not in printed


def test_three_failed_probes_end_with_an_honest_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Три попытки подряд не дали играбельного видео — код 1 с объяснением.

    Кодеки тут те, которых мы не берём на себя: перекод целиком замерен для HEVC
    (:data:`torrcast.stream.RECODE_CODECS`), а av1/vc1 остаются честным отказом.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(5)]
    _probes(monkeypatch, ranked, "av1", "mpeg2video", "vc1")
    with pytest.raises(NotFoundError) as caught:
        _resolve(cli._Bench(cast(Any, _FakeTorrServer())), ranked)
    assert "годного релиза нет" in str(caught.value)
    assert "1 - av1" in str(caught.value) and "3 - vc1" in str(caught.value)
    assert len(re.findall(r"беру \d", capsys.readouterr().out)) == 2  # не больше MAX_TRIES


def test_vp9_is_refused_at_the_pick_like_av1_and_never_reaches_the_packer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 VP9 - честный отказ отбора, а не молчаливая копия в mpegts.

    До этого VP9 не спасало ничто: в наборе кодеков на сплошной перекод стоял один
    ``hevc``, белого списка копии упаковка не спрашивала вовсе, и раздача уезжала на
    приёмник как есть - ``LOAD`` не взят, ``IDLE/ERROR``, чёрный экран.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "vp9", "h264")

    prep = _resolve(cli._Bench(cast(Any, _FakeTorrServer())), ranked)

    assert (prep.number, prep.found.video) == (2, "h264"), "берём тот, про который знаем всё"
    assert "релиз 1 не годится (vp9) - беру 2" in capsys.readouterr().out


def test_tv_mock_switches_the_receiver_and_leaves_no_tv_address(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`cast --tv mock` — команда установки на машине без телевизора.

    Она обязана переключить приёмник, иначе такая машина полезла бы кастить на Chromecast.
    И обратно тоже: адрес ТВ возвращает штатный приёмник, а от прежнего значения в
    конфиге не остаётся и следа.
    """
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))

    assert cli.main(["--tv", "mock"]) == 0
    config = load_config()
    assert (config.tv, config.receiver) == ("mock", "mock")
    assert "10.0.0." not in (tmp_path / "config.json").read_text()
    assert "headless" in capsys.readouterr().out

    assert cli.main(["--tv", "10.0.0.50"]) == 0
    assert (load_config().tv, load_config().receiver) == ("10.0.0.50", "chromecast")


def test_tv_without_an_address_offers_the_receivers_it_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`cast --tv` без адреса - финал установки: список приёмников и ответ номером.

    Адрес телевизора человеку взять негде: в меню ТВ он спрятан через три экрана, а в
    роутер пускают не всех. Поэтому спрашиваем не адрес, а «какой из этих телевизоров
    твой», и в состояние уезжает ровно то же поле, что и при заданном руками адресе.
    """
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setattr(
        scan,
        "find",
        lambda: scan.Found(
            devices=[
                scan.Device("10.0.0.50", name="Samsung Q70D", how="mdns"),
                scan.Device("10.0.0.60", model="Chromecast", how="скан"),
            ]
        ),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    assert cli.main(["--tv"]) == 0

    out = capsys.readouterr().out
    assert "  1. Samsung Q70D - 10.0.0.50" in out
    assert "  2. Chromecast - 10.0.0.60" in out
    assert (load_config().tv, load_config().receiver) == ("10.0.0.60", "chromecast")


def test_the_only_receiver_found_is_taken_by_enter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Нашёлся один - вопрос остаётся, но отвечается пустым Enter: номер тут не нужен."""
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setattr(
        scan,
        "find",
        lambda: scan.Found(devices=[scan.Device("10.0.0.50", name="Samsung Q70D", how="mdns")]),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    assert cli.main(["--tv"]) == 0
    assert load_config().tv == "10.0.0.50"
    assert "ТВ: Samsung Q70D - 10.0.0.50" in capsys.readouterr().out


def test_finding_nobody_says_why_and_keeps_the_manual_way(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Пустой список - не «ошибка сети», а причина и выход: ТВ выключен либо не в той сети.

    Заодно вслух говорится о подсети, которую мы не обходили: умолчать о ней - значит
    оставить человека гадать, почему его телевизор не нашёлся.
    """
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setattr(
        scan, "find", lambda: scan.Found(notes=["подсеть 10.5.0.0/16 на 65534 адресов"])
    )

    assert cli.main(["--tv"]) == 1

    done = capsys.readouterr()
    assert "10.5.0.0/16" in done.out
    assert "включён" in done.err and "той же сети" in done.err
    assert "cast --tv <ip>" in done.err
    assert not (tmp_path / "config.json").exists(), "неудачный поиск конфиг не трогает"


def test_several_receivers_without_a_terminal_are_not_picked_blindly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Спросить некого, а найдено несколько - молча записать первый попавшийся нельзя.

    Это ровно тот же отказ, что и в меню картин: любой дефолт тут означает чужое
    устройство в конфиге, а не оттенок выбора.
    """
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setattr(console, "stdin_is_tty", lambda: False)
    monkeypatch.setattr(
        scan,
        "find",
        lambda: scan.Found(
            devices=[scan.Device("10.0.0.50"), scan.Device("10.0.0.60", name="Гостиная")]
        ),
    )

    assert cli.main(["--tv"]) == 1
    assert not (tmp_path / "config.json").exists()


def test_warmup_leaves_in_torrserver_only_what_we_play(monkeypatch: pytest.MonkeyPatch) -> None:
    """Прогрев греет лишнее по определению — лишнее убирается до старта показа.

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
    """Живая выдача по «Моане 2»: 221 сид против 140 — и всё равно не дефолт.

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
    assert ranked[0] is avc, "верх - годный WEB-DL-AVC"
    assert ranked[1] is avi, "и всё же не выкинут: судья по-прежнему ffprobe"
    assert cli.is_dated(avi, RUNTIME) and not cli.is_dated(avc, RUNTIME)


def test_a_named_codec_no_longer_hides_an_sd_rip() -> None:
    """``BDRip-AVC`` на 1.46 ГБ — это 720×304, и названный кодек его больше не выгораживает.

    Замер по живой выдаче: ровно такие раздачи стояли верхом у «Тёмного рыцаря:
    Возрождение легенды» (58 сидов), «Форреста Гампа» (105) и «Зелёной мили» (64) —
    и у каждой рядом лежал названный 1080p. Про разрешение кодек не говорит ничего.
    """
    named = rel(name="BDRip-AVC", quality=None, size_gb=1.46, seeders=131)
    assert cli.is_dated(named, RUNTIME)


def test_a_named_resolution_is_never_argued_with_by_size() -> None:
    """Разрешение в имени эвристику отключает: спорить с ним — работа ffprobe, не размера.

    Скромный битрейт при названном 720p — это законный компактный рип, а не старьё;
    а если имя всё-таки соврало, подмену сделает :func:`understated` по факту кадра.
    """
    named = rel(name="BDRip-AVC 720p", quality="720p", size_gb=1.46, seeders=131)
    assert not cli.is_dated(named, RUNTIME)


def test_a_series_pack_is_judged_by_the_size_of_one_episode() -> None:
    """У сериала в раздаче лежит сезон целиком — делить надо на серии, а не на фильм.

    Пока делили целиком, .avi-эвристика для сериалов не работала вовсе: «6 ГБ» на восемь
    серий это 1.7 Мбит/с на серию, а как один фильм — 6.6, то есть выше порога SD, и
    старьё спокойно стояло верхом отбора. Счёт серий берётся из имени раздачи.
    """
    runtime = RUNTIME_GUESS["tv"]
    old = parse_release_name("Сериал / Series [01-08 of 8] (2001) SATRip")
    good = parse_release_name("Сериал / Series [01-08 of 8] (2001) WEB-DL")
    fat = parse_release_name("Сериал / Series [01-08 of 8] (2001) WEB-DL")
    fat = replace(fat, size=int(80 * GB), seeders=5)
    old, good = replace(old, size=int(2 * GB), seeders=900), replace(good, size=int(60 * GB))

    assert old.episode_count == 8 and good.episode_count == 8
    assert cli.bitrate_of(good, runtime) == pytest.approx(
        cli.bitrate_of(fat, runtime) * 0.75, rel=0.01
    ), "битрейт считается на серию: 60 ГБ на восьмерых против 80 ГБ на восьмерых"
    assert cli.is_dated(old, runtime), "0.25 ГБ на серию - это SD, сколько бы сидов ни было"
    assert not cli.is_dated(good, runtime)
    assert rank_releases([old, good], runtime, 40.0)[0] is good


def test_a_series_pack_that_does_not_count_its_episodes_is_left_to_ffprobe() -> None:
    """Имя не считает серии — делить не на что, и оценки не будет: врать себе хуже.

    Такую раздачу («Локи [S01] WEB-DL», сколько внутри серий — знают только файлы)
    по-прежнему судит ffprobe уже после выбора, с отбраковкой и переходом к следующей.
    """
    silent = replace(
        parse_release_name("Локи / Loki [S01] (2021) WEB-DL"), size=int(8 * GB), seeders=24
    )
    assert silent.kind == "tv" and silent.episode_count == 0
    assert cli.bitrate_of(silent, RUNTIME_GUESS["tv"]) == 0.0
    assert not cli.is_dated(silent, RUNTIME_GUESS["tv"])


def test_dated_sinks_below_candidates_but_above_hevc() -> None:
    """Ступень «старьё» вклинена МЕЖДУ годностью и сидами, группы местами не меняются.

    Случай живой: у «Матрицы: Перезагрузка» ``DVDRip-AVC`` на 47 сидов
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
    assert is_candidate(dated, RUNTIME, 20.0), "старьё остаётся годным - судит ffprobe"


def test_a_name_that_admits_sd_sinks_below_any_hd() -> None:
    """«480p» в имени — не повод для спора: раздача сама сказала, что она не HD.

    SD играется, только если HD в каталоге нет вовсе; сиды этого не отменяют.
    """
    sd = rel(name="WEB-DL 480p", codec=None, quality="480p", size_gb=1.2, seeders=400)
    hd = rel(name="WEB-DL 720p", codec=None, quality="720p", size_gb=4.0, seeders=12)
    assert cli.is_dated(sd, RUNTIME) and not cli.is_dated(hd, RUNTIME)
    assert rank_releases([sd, hd], RUNTIME, 25.0)[0] is hd
    assert rank_releases([sd], RUNTIME, 25.0)[0] is sd, "другого нет - играем что есть"


def test_an_sd_rip_no_longer_outseeds_the_honest_1080p() -> None:
    """Живая выдача «Тёмного рыцаря»: 58 сидов на 1.47 ГБ против 14 на честном 1080p.

    Ровно этот случай и давал SD-фолбэк: в порядке участвовали одни сиды, а про
    разрешение никто не спрашивал.
    """
    sd = rel(name="BDRip-AVC", quality=None, size_gb=1.47, seeders=58)
    full = rel(name="BDRip 1080p", codec=None, size_gb=7.76, seeders=14)
    assert [r.raw_name for r in rank_releases([sd, full], RUNTIME, 25.0)] == [
        "BDRip 1080p",
        "BDRip-AVC",
    ]


def test_a_live_1080p_beats_a_more_seeded_720p() -> None:
    """«Мастер и Маргарита»: ``WEB-DL 720p`` со 146 сидами уступает ``WEB-DL 1080p`` с 59."""
    hd = rel(name="WEB-DL 720p", codec=None, quality="720p", size_gb=3.43, seeders=146)
    full = rel(name="WEB-DL 1080p", codec=None, size_gb=7.14, seeders=59)
    assert rank_releases([hd, full], RUNTIME, 25.0)[0] is full
    assert cli.is_full_hd(full, alive=146) and not cli.is_full_hd(hd, alive=146)


def test_a_dead_1080p_does_not_buy_a_step_with_rebuffering() -> None:
    """«Форрест Гамп»: 15 ГБ на двух сидах против 720p на сорока одном — ступень не стоит того.

    Плавность выше пиковой чёткости: поднять такой 1080p значило бы поменять
    разрешение на подгрузы.
    """
    hd = rel(name="BDRip 720p", codec=None, quality="720p", size_gb=14.88, seeders=41)
    full = rel(name="BDRip 1080p", codec=None, size_gb=15.18, seeders=2)
    assert rank_releases([hd, full], RUNTIME, 25.0)[0] is hd
    assert not cli.is_full_hd(full, alive=41)


def test_a_lying_1080p_is_still_swapped_by_ffprobe() -> None:
    """Ступень поднимает ОБЕЩАНИЕ, а судит по-прежнему кадр: 1080p в имени, 574p внутри."""
    liar = rel(name="BDRip 1080p", codec=None, size_gb=7.0, seeders=100)
    assert cli.is_full_hd(liar, alive=100)
    assert cli.understated(liar, Media(height=574, width=1150)) == "назван 1080p, на деле 574p"


def test_the_ceiling_is_checked_again_by_the_file_not_by_the_torrent_size() -> None:
    """Потолок 16 Мбит/с ловит «Моану 2» только после ffprobe — до него ловить нечем.

    Прикидка при выборе дефолта делит 13.3 ГБ на типовые два часа и даёт 14.8 Мбит/с,
    то есть релиз проходит как кандидат. А внутри фильм на 1:39:37 — честные
    17.8 Мбит/с, на которых Q70D встаёт в ребуфер. Названный руками
    (``--release N``) берётся по-прежнему: там человек выбрал сам.
    """
    from torrcast.stream import Media, TorrFile

    heavy = rel(size_gb=13.3 * 1e9 / GB)  # 13.3 ГБ по-магазинному, как их считает трекер
    assert is_candidate(heavy, RUNTIME, 16.0), "прикидка по раздаче потолок не превышает"

    bench = cli._Bench(cast(Any, _FakeTorrServer()))
    prep = cli._Prep(number=1, release=heavy)
    prep.video = TorrFile(0, "moana2.mkv", 13_300_000_000)
    prep.media = Media(duration=5977.0, video="h264")

    assert (
        bench._trouble(prep, pinned=False, warn_mbit=16.0)
        == "слишком тяжёлый для приёмника, ~18 Мбит/с"
    )
    assert bench._trouble(prep, pinned=True, warn_mbit=16.0) == "", "руками - берём"
    assert bench._trouble(prep, pinned=False, warn_mbit=20.0) == "", "прежний потолок брал"


def test_the_ceiling_weighs_the_video_track_not_the_ten_dubs_around_it() -> None:
    """Отбраковка считает от паспорта (``Entry.vbps``), а не от размера файла.

    Потолок спрашивает «сколько придётся перекодировать непрерывно», а перекодировать
    придётся картинку: десять озвучек и двенадцать субтитров на ТВ не уезжают вовсе.
    Числа живые: у «Моаны 2» контейнер 19.2 Мбит/с, а видеодорожка — 14.3.
    Паспорт молчит — считаем по размеру, как раньше, иначе 4K-ремукс проедет насквозь.
    """
    from torrcast.stream import Media, TorrFile

    bench = cli._Bench(cast(Any, _FakeTorrServer()))
    prep = cli._Prep(number=1, release=rel(size_gb=13.3 * 1e9 / GB))
    prep.video = TorrFile(0, "moana2.mkv", 13_300_000_000)
    prep.media = Media(duration=5977.0, video="h264", video_bps=14_333_000.0)
    assert bench._trouble(prep, pinned=False, warn_mbit=16.0) == "", "видео 14.3 - годится"

    prep.media = Media(duration=5977.0, video="h264", video_bps=49_900_000.0)
    assert (
        bench._trouble(prep, pinned=False, warn_mbit=25.0)
        == "слишком тяжёлый для приёмника, ~50 Мбит/с"
    )

    prep.media = Media(duration=5977.0, video="h264")  # паспорт молчит - по размеру
    assert (
        bench._trouble(prep, pinned=False, warn_mbit=16.0)
        == "слишком тяжёлый для приёмника, ~18 Мбит/с"
    )


def _franchise_plan(title: str, year: int, releases: list[Release]) -> Any:
    from torrcast.parse import Picture

    return cli._Plan(
        picture=Picture(title=title, year=year, releases=releases),
        ranked=rank_releases(releases, RUNTIME, 20.0),
        runtime=RUNTIME,
        warn_mbit=20.0,
    )


def _moana_franchise() -> list[Any]:
    """Франшиза «моана» из живой выдачи, сведённая к верху отбора каждой картины."""
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


def _cars_franchise() -> list[Any]:
    """Франшиза «тачки» из живой выдачи: у каждой картины верх её отбора.

    «Тачки 2» стоят тут четырьмя релизами не для красоты: обсиженный BD-ремукс на
    38.4 ГБ выше потолка отбора, и годным верхом у картины остаётся 0.4-гигабайтный
    HDRip «фильм о фильме» с одним сидом. Ровно этот случай порог живости и обязан
    отбросить, хотя формально «кандидат есть».
    """
    return [
        _franchise_plan(
            "Тачки", 2006, [rel(name="Cars 2006 BluRay 1080p x264", size_gb=7.06, seeders=66)]
        ),
        _franchise_plan(
            "Тачки: Мультачки. Байки Мэтра",
            2008,
            [rel(name="Cars Toon [DVD9]", codec=None, quality=None, size_gb=5.41, seeders=5)],
        ),
        _franchise_plan(
            "Тачки 2",
            2011,
            [
                rel(name="Cars 2 [HDRip] фильм о фильме", quality=None, size_gb=0.40, seeders=1),
                rel(name="Cars 2 [BDRemux 2160p]", quality="2160p", size_gb=38.4, seeders=126),
            ],
        ),
        _franchise_plan(
            "Тачки 3", 2017, [rel(name="Cars 3 WEB-DL 1080p", size_gb=4.59, seeders=121)]
        ),
    ]


def test_menu_default_is_the_first_living_picture_of_the_franchise() -> None:
    """Живая выдача по «тачкам»: смотреть начинают с первой части, и она жива.

    Прежний дефолт «самая живая» печатал `[4]` — «Тачки 3» с 121 сидом. Первая часть
    при этом вполне играбельна: 1080p BluRay на 66 сидов, 0.55 от лидера франшизы.
    """
    plans = _cars_franchise()
    assert [cli.liveliness(p) for p in plans] == [66, 0, 1, 121]
    assert cli.liveliest(plans) == 4, "прежнее правило и правда уводило на третью часть"
    assert cli.first_alive(plans) == 1


def test_menu_default_steps_over_a_dead_first_picture() -> None:
    """Живая выдача по «моане»: список хронологический, а дефолт — вторым пунктом.

    Первым в хронологии стоит «Моана: романтика золотого века» (1926) — немое
    документальное кино, один VHS-рип на 5 сидов. Enter на ней не давал ничего.
    """
    plans = _moana_franchise()
    assert [cli.liveliness(p) for p in plans] == [0, 222, 140]
    assert cli.liveliest(plans) == 2
    assert cli.first_alive(plans) == 2


def test_a_faint_swarm_does_not_count_as_alive() -> None:
    """Один сид - это не «живая часть», а её отсутствие.

    Порог - свой рой картины (:data:`~torrcast.cli.ALIVE_SEEDERS`). Без него дефолт
    уходил бы на первую попавшуюся картину с хоть каким-то кандидатом.
    """
    plans = _cars_franchise()
    assert cli.first_alive(plans[1:]) == 3, "«Мультачки» и «Тачки 2» мертвы, жива третья"


def _parts(*parts: tuple[str, int, int]) -> list[Any]:
    """Франшиза из троек «название, год, сиды лучшей ГОДНОЙ раздачи картины».

    Раздача у каждой части одна и заведомо играбельная (WEB-DL 1080p, 4.2 ГБ): вопрос
    теста - только про порядок частей и про живость, а не про отбор внутри картины.
    """
    return [
        _franchise_plan(
            title, year, [rel(name=f"{title} {year} WEB-DL 1080p", size_gb=4.2, seeders=seeders)]
        )
        for title, year, seeders in parts
    ]


#: Франшизы, на которых дефолт садился не на ту картину (карточка TC-196): свежая часть
#: с большим роем перевешивала классику, и та объявлялась мёртвой долей от лидера. Числа -
#: форма той поломки (сотни сидов у новинки против живых десятков у первой части), а не
#: расшифровка конкретного прогона; ожидание - номер пункта, который обязан стать дефолтом.
_FRANCHISES: list[tuple[str, list[Any], int]] = [
    (
        "мумия",
        _parts(
            ("Мумия", 1999, 47),
            ("Мумия возвращается", 2001, 33),
            ("Мумия: Гробница Императора Драконов", 2008, 21),
            ("Мумия", 2017, 58),
            ("Мумия", 2026, 604),
        ),
        1,
    ),
    (
        "хищник",
        _parts(
            ("Хищник", 1987, 39),
            ("Хищник 2", 1990, 24),
            ("Хищники", 2010, 31),
            ("Хищник", 2018, 44),
            ("Хищник: Добыча", 2022, 96),
            ("Хищник: Планета смерти", 2025, 488),
        ),
        1,
    ),
    (
        "голодные игры",
        _parts(
            ("Голодные игры", 2012, 52),
            ("Голодные игры: И вспыхнет пламя", 2013, 41),
            ("Голодные игры: Сойка-пересмешница. Часть I", 2014, 28),
            ("Голодные игры: Баллада о певчих птицах и змеях", 2023, 317),
        ),
        1,
    ),
    (
        "дюна",
        _parts(("Дюна", 1984, 26), ("Дюна", 2021, 190), ("Дюна: Часть вторая", 2024, 402)),
        1,
    ),
    (
        "безумный макс",
        _parts(
            ("Безумный Макс", 1979, 18),
            ("Безумный Макс 2: Воин дороги", 1981, 22),
            ("Безумный Макс 3: Под куполом грома", 1985, 15),
            ("Безумный Макс: Дорога ярости", 2015, 356),
        ),
        1,
    ),
    (
        "джуманджи",
        _parts(
            ("Джуманджи", 1995, 63),
            ("Джуманджи: Зов джунглей", 2017, 274),
            ("Джуманджи: Новый уровень", 2019, 198),
        ),
        1,
    ),
    ("тачки", _cars_franchise(), 1),
    ("моана", _moana_franchise(), 2),
]


@pytest.mark.parametrize(
    ("asked", "plans", "expected"), _FRANCHISES, ids=[f[0] for f in _FRANCHISES]
)
def test_the_franchise_default_is_the_first_playable_part(
    asked: str, plans: list[Any], expected: int
) -> None:
    """🔴 TC-196: на голое имя франшизы дефолтом встаёт ПЕРВАЯ ЖИВАЯ часть.

    «Живая» - это «есть чем играть» (свой рой картины), а не «раздаётся лучше всех».
    Прежний порог был долей от самой живой части франшизы, и один свежий релиз с большим
    роем выбивал из живых всю классику: «мумия» давала дефолтом картину 2026 года десять
    прогонов из десяти, «хищник» - «Планету смерти», «дюна» - «Часть вторую».
    """
    picked = cli.first_alive(plans)
    assert picked == expected, f"«{asked}»: дефолт обязан быть [{expected}], а не [{picked}]"
    assert cli.liveliness(plans[picked - 1]) >= cli.ALIVE_SEEDERS or all(
        cli.liveliness(p) < cli.ALIVE_SEEDERS for p in plans
    ), "дефолт стоит на картине, которой нечем играть"


@pytest.mark.parametrize(
    ("asked", "plans", "expected"), _FRANCHISES, ids=[f[0] for f in _FRANCHISES]
)
def test_the_old_share_of_the_liveliest_would_have_missed_the_first_part(
    asked: str, plans: list[Any], expected: int
) -> None:
    """Тот же список под ОТКАЧЕННЫМ правилом: доля от лидера ошибается или совпадает.

    Тест не про будущее поведение, а про то, что фикстуры действительно воспроизводят
    поломку: у шести франшиз карточки первая часть не дотягивала до 0.25 от самой живой
    и дефолт уезжал, у «тачек» и «моаны» доля отвечала верно - их правка и не трогает.
    """
    best = max(cli.liveliness(p) for p in plans)
    survivors = [
        n for n, p in enumerate(plans, start=1) if cli.liveliness(p) >= best * cli.FULL_HD_LIVENESS
    ]
    was_wrong = expected not in survivors
    assert was_wrong == (asked not in {"тачки", "моана"}), (
        f"«{asked}»: доля от лидера оставляла живыми {survivors}"
    )


def test_a_franchise_with_no_life_still_points_somewhere() -> None:
    """Живого нет вовсе — цифра в скобках всё равно обязана на что-то указывать."""
    dead = [
        _franchise_plan("Кино", 2001, [rel(name="dvd9 [DVD9]", quality=None, seeders=2)]),
        _franchise_plan("Кино 2", 2005, [rel(name="dvd5 [DVD5]", quality=None, seeders=1)]),
    ]
    assert [cli.liveliness(p) for p in dead] == [0, 0]
    assert cli.first_alive(dead) == 1


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


def test_a_half_walked_queue_is_not_a_dead_swarm() -> None:
    """Отказ обязан различать «пиров правда нет» и «перебрали три раздачи из пятнадцати».

    Прежняя строка была одна на все случаи - «рой у них мёртв, пиров нет». В замере
    каталога её получили 18 запросов из 225, и у девяти рой был живой: очередь отбора
    просто кончилась раньше выдачи. Числа в строке теперь всегда два.
    """
    pool = [rel(name=f"r{n}", seeders=7 * n) for n in range(15)]
    plan = _plan(pool)
    half = cli.silent_swarm(plan, 3, "1 - тишина")
    assert "раздач в выдаче 15, потрогали 3" in half
    assert "мёртв" not in half, "живой рой мёртвым не называем"
    assert "до 98 сид" in half and "cast releases" in half

    whole = cli.silent_swarm(plan, 15, "1 - тишина")
    assert "раздач в выдаче 15, потрогали 15 (все)" in whole
    assert "ни одна не отозвалась" in whole and "числятся" in whole


def test_a_pool_without_a_single_peer_says_so_plainly() -> None:
    """Сидов не числится ни у одной раздачи - вот тут «пиров нет» и есть правда.

    Эталонная пара из живой выдачи: у «Зелёной границы» две раздачи и ноль сид, у
    «Двенадцати обезьян» тридцать раздач и до 105 сид. Формулировки обязаны отличаться.
    """
    border = _plan([rel(name=f"r{n}", seeders=0) for n in range(2)])
    monkeys = _plan([rel(name=f"r{n}", seeders=3 + n) for n in range(30)])
    dead = cli.silent_swarm(border, 2, "1 - тишина")
    live = cli.silent_swarm(monkeys, 3, "1 - тишина")
    assert dead == (
        "раздач в выдаче 2, потрогали 2 - пиров нет ни у одной, показывать нечего (1 - тишина)"
    )
    assert "пиров нет" not in live
    assert dead != live


def _series_plan(title: str, year: int, kind: Kind, releases: list[Release]) -> Any:
    """План картины, у которой запрос назвал серию: тип сказан вслух (``s1e1``)."""
    from torrcast.parse import Picture

    return cli._Plan(
        picture=Picture(title=title, year=year, kind=kind, releases=releases),
        ranked=rank_releases(releases, RUNTIME, 20.0),
        runtime=RUNTIME,
        warn_mbit=20.0,
        asked_series=True,
    )


def test_liveliness_counts_the_best_playable_release_not_the_queue_top() -> None:
    """«Мальтийский сокол» 1941 из живой выдачи: наверху очереди не самая живая раздача.

    Очередь сортируется не сидами одними: 1080p и русская дорожка стоят выше. Наверху
    у картины оказался релиз на 5 сидов, а годный сосед ниже держал 28 - и картина с
    двадцатью двумя раздачами весила меньше однораздачной тёзки 1931 года на 16 сид.
    """
    falcon = _franchise_plan(
        "Мальтийский сокол",
        1941,
        [
            rel(name="Мальтийский сокол BDRip 1080p Дубляж", size_gb=8.0, seeders=5),
            rel(name="The Maltese Falcon BDRip 720p", quality="720p", size_gb=4.0, seeders=28),
        ],
    )
    assert falcon.ranked[0].seeders == 5, "наверху очереди - то, что лучше смотреть"
    assert cli.liveliness(falcon) == 28, "а весит картина по лучшей ГОДНОЙ раздаче"


def test_default_steps_over_a_picture_backed_by_a_single_release() -> None:
    """Живая выдача по «мальтийскому соколу»: дефолт садился на 1931 год одной раздачей.

    Порог живости она проходила честно - 16 сид против 28 у лучшей годной раздачи
    соседки, - но играть ею нечего: одно обещание индексера и никакой очереди за ним.
    Рядом стоит картина 1941 года с двадцатью двумя раздачами.
    """
    thin = _franchise_plan(
        "Мальтийский сокол", 1931, [rel(name="Мальтийский сокол 1931 BDRip", seeders=16)]
    )
    deep = _franchise_plan(
        "Мальтийский сокол",
        1941,
        [
            rel(name="Мальтийский сокол BDRip 1080p Дубляж", size_gb=8.0, seeders=5),
            rel(name="The Maltese Falcon BDRip 720p", quality="720p", size_gb=4.0, seeders=28),
        ],
    )
    assert cli.alive_numbers([thin, deep], [1, 2]) == [1, 2], "по сидам живы обе"
    assert cli.first_alive([thin, deep]) == 2
    assert "всего одна раздача" in cli.default_note([thin, deep])


def _asked_parts(*parts: tuple[str, int, Kind, int]) -> list[Any]:
    """Франшиза, у которой запрос назвал серию: тип сказан вслух (``s2e7``)."""
    return [
        _series_plan(
            title,
            year,
            kind,
            [rel(name=f"{title} {year} WEB-DL 1080p", size_gb=4.2, seeders=seeders)],
        )
        for title, year, kind, seeders in parts
    ]


#: Спорные запросы из замера каталога (карточка TC-198), где картина менялась молча.
#: Расклад каждого - ФОРМА его смены (тёзка по году / мёртвая первая часть / гейт типа),
#: а не расшифровка прогона: живой выдачи у теста нет. Третий элемент - слова, без которых
#: строка не сказала бы, ЧТО именно поменяли.
_SWAPS: list[tuple[str, list[Any], list[str]]] = [
    (
        "мумия",
        _parts(
            ("Мумия", 1999, 47),
            ("Мумия возвращается", 2001, 33),
            ("Мумия", 2017, 58),
            ("Мумия", 2026, 604),
        ),
        ["Мумия (1999)", "Мумия (2026)"],
    ),
    (
        "хищник",
        _parts(("Хищник", 1987, 39), ("Хищник", 2018, 44), ("Хищник: Планета смерти", 2025, 488)),
        ["Хищник (1987)", "Хищник (2018)"],
    ),
    (
        "дюна",
        _parts(("Дюна", 1984, 26), ("Дюна", 2021, 190), ("Дюна: Часть вторая", 2024, 402)),
        ["Дюна (1984)", "Дюна (2021)"],
    ),
    ("оно", _parts(("Оно", 1990, 37), ("Оно", 2017, 214)), ["Оно (1990)", "Оно (2017)"]),
    (
        "москва слезам не верит",
        _parts(("Москва слезам не верит", 1979, 88), ("Москва слезам не верит", 2019, 12)),
        ["Москва слезам не верит (1979)", "Москва слезам не верит (2019)"],
    ),
    (
        "гарри поттер",
        _parts(
            ("Гарри Поттер и философский камень", 2001, 2),
            ("Гарри Поттер и Тайная комната", 2002, 61),
        ),
        ["Гарри Поттер и Тайная комната (2002)", "Гарри Поттер и философский камень (2001)"],
    ),
    (
        "медведь s2e7",
        _asked_parts(("Медведь", 1938, "movie", 22), ("Медведь", 2022, "tv", 95)),
        ["Медведь (2022, сериал)", "Медведь (1938)", "спросили серию"],
    ),
    (
        "доктор кто s5e10",
        _asked_parts(("Доктор Кто", 1963, "tv", 14), ("Доктор Кто", 2005, "tv", 268)),
        ["Доктор Кто (1963, сериал)", "Доктор Кто (2005, сериал)"],
    ),
]


@pytest.mark.parametrize(("asked", "plans", "words"), _SWAPS, ids=[s[0] for s in _SWAPS])
def test_a_swapped_picture_is_said_out_loud_in_one_line(
    asked: str, plans: list[Any], words: list[str]
) -> None:
    """🔴 TC-198: взяли не то, что назвали, - одна честная строка «спросили X - беру Y».

    В замере каталога десять спорных запросов из четырнадцати сменили картину МОЛЧА, а
    ещё у четырёх строка была не про то: у «гарри поттера» человек читал про оригинальное
    имя и добор сезона, пока менялась часть франшизы.
    """
    note = cli.default_note(plans, asked)
    assert note, f"«{asked}»: смена картины прошла молча"
    assert "\n" not in note, "строка одна"
    assert note.startswith(f"спросили «{asked}» - беру "), note
    for word in words:
        assert word in note, f"«{asked}»: строка не говорит про «{word}» - {note}"


@pytest.mark.parametrize(
    ("asked", "plans"),
    [
        ("голодные игры", _FRANCHISES[2][1]),
        ("безумный макс", _FRANCHISES[4][1]),
        ("джуманджи", _FRANCHISES[5][1]),
        ("тачки", _cars_franchise()),
    ],
)
def test_taking_exactly_what_was_asked_is_not_worth_a_line(asked: str, plans: list[Any]) -> None:
    """Взято ровно запрошенное - строки нет: счастливый путь остаётся без лишних слов.

    Три из четырнадцати спорных запросов после TC-196 перестают быть сменой вовсе:
    дефолтом встаёт первая часть, то есть та самая картина, чьё имя человек и назвал.
    Говорить о решении, которого не принимали, - такой же шум, как молчать о принятом.
    """
    assert cli.default_note(plans, asked) == ""


def test_the_line_belongs_to_the_default_not_to_the_human_choice() -> None:
    """Человек ответил на меню сам - подмены не было, и говорить ему «беру не то» нельзя."""
    plans = _parts(("Оно", 1990, 37), ("Оно", 2017, 214))
    assert cli.swap_note(plans, plans[0], "оно"), "дефолт - строка есть"
    assert cli.swap_note(plans, plans[1], "оно") == "", "выбрал человек - строки нет"
    assert cli.swap_note(plans[:1], plans[0], "оно") == "", "картина одна - выбора не было"


def test_a_lone_release_still_wins_when_the_whole_franchise_is_lone() -> None:
    """Все живые картины об одной раздаче - список остаётся как был.

    Ступень отбрасывает однораздачные, только пока в живых есть кто-то ещё: иначе она
    молчаливо превращала бы «живую» картину в мёртвую, а выбирать всё равно не из чего.
    Здесь же и защита от «дефолт = самая раздаваемая»: первая часть франшизы остаётся
    дефолтом, даже когда у сиквела раздач больше.
    """
    first = _franchise_plan("Кино", 2001, [rel(name="a", seeders=100)])
    second = _franchise_plan("Кино 2", 2005, [rel(name="b", seeders=90), rel(name="c", seeders=80)])
    assert cli.first_alive([first, second]) == 1
    assert cli.default_note([first, second]) == "", "решения не принимали - и строки нет"


def test_asked_series_outweighs_a_namesake_film() -> None:
    """«хорошая жена s1e1» - просьба про сериал, а дефолтом вставал фильм 1987 года.

    У фильма три раздачи и ни одной живой, у сериала 2015 года - тридцать раздач и 18
    сид. Тип, названный запросом, весит больше одноимённого соседа другого типа.
    """
    film = _series_plan(
        "Хорошая жена",
        1987,
        "movie",
        [rel(name="film", seeders=6), rel(name="film dvd", quality="720p", seeders=4)],
    )
    show = _series_plan(
        "Хорошая жена",
        2015,
        "tv",
        [rel(name="s01", seeders=12), rel(name="s01 web", quality="720p", seeders=18)],
    )
    assert cli.first_alive([film, show]) == 2
    note = cli.default_note([film, show])
    assert "спросили серию" in note and "2015" in note and "1987" in note


def test_a_film_only_catalogue_keeps_the_default_where_it_was() -> None:
    """Сериалов в выдаче нет вовсе - гейт типа молчит: он не судья тому, чего не видел."""
    first = _series_plan("Кино", 2001, "movie", [rel(name="a", seeders=100)])
    second = _series_plan("Кино 2", 2005, "movie", [rel(name="b", seeders=100)])
    assert cli.asked_kind([first, second]) == [1, 2]
    assert cli.first_alive([first, second]) == 1
    assert cli.default_note([first, second]) == ""


def test_the_default_names_itself_for_a_menu_that_does_not_fit_the_screen() -> None:
    """🔴 TC-204. «Ван Пис»: дефолт стоял строкой 33 из 35, а человек видел только `[33]`.

    Порядок меню хронологический и таким остаётся - меняется показ дефолта, а не порядок:
    список по-прежнему начинается с самой ранней картины, а что случится по Enter,
    сказано словами - названием и годом, а не одной цифрой.
    """
    plans = [
        _franchise_plan("Ван Пис", 1990 + n, [rel(name=f"rip {n}", seeders=0 if n < 33 else 20)])
        for n in range(1, 36)
    ]
    default = cli.first_alive(plans)

    assert default == 33, "живой в этой выдаче стала только тридцать третья картина"
    assert cli.default_line(plans, default) == "Enter - «Ван Пис (2023)», пункт 33 из 35"
    assert cli.menu_lines(plans, width=80).splitlines()[0].startswith("  1. Ван Пис (1991)"), (
        "список не переупорядочивается: хронология - осознанное решение"
    )


def test_prewarm_starts_with_the_default_not_with_the_earliest() -> None:
    """Греем то, во что попадёт Enter: иначе прогрев под меню греет чужую картину.

    У «моаны» дефолт — вторая картина, а под меню греются только первые
    :data:`~torrcast.cli.PREWARM`.
    """
    plans = _moana_franchise()
    assert [p.picture.year for p in cli.warm_order(plans)] == [2016, 1926, 2024]


def test_the_spare_release_goes_up_next_to_the_first_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Запасной релиз выбранной картины греется вместе с верхом, а не после его брака.

    Номер у него ровно тот же, который возьмёт :meth:`~torrcast.cli._Bench.resolve`, -
    следующий в очереди (:meth:`~torrcast.cli._Plan.candidates`). Отличается только время:
    раньше он поднимался в отборе, теперь - пока на экране висит меню.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "h264")
    bench = cli._Bench(cast(Any, _FakeTorrServer()))
    plan = _plan(ranked)

    bench.start(plan, plan.first)
    spare = bench.spare(plan, cli.Args(query=["кино"]))

    assert [prep.number for prep in spare] == [plan.candidates(cli.Args(query=["кино"]))[1]]
    assert sorted(number for _, number in bench.preps) == [1, 2]


def test_a_release_named_by_hand_has_no_spare(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--release N`` - выбор человека: подменять нечем, и лишней раздачи не поднимаем."""
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    _probes(monkeypatch, ranked, "h264")
    torrserver = _FakeTorrServer()
    bench = cli._Bench(cast(Any, torrserver))

    assert bench.spare(_plan(ranked), cli.Args(query=["кино"], release=2)) == []
    assert not bench.preps


# --- Честное качество: заявка имени против того, что прочитал ffprobe -----------------


def _reads(monkeypatch: pytest.MonkeyPatch, releases: list[Release], *media: Media) -> None:
    """Подсунуть ffprobe: по :class:`Media` на релиз, считая от лучшего.

    То же, что :func:`_probes`, только с высотой кадра: тут проверяется не кодек, а
    разрыв между тем, что раздача обещает именем, и тем, что лежит внутри.
    """

    def read(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        for number, release in enumerate(releases):
            if f"hash-{release.magnet}/" in url and number < len(media):
                return media[number]
        return Media(3600.0, (), "h264", 1080, 1920)

    monkeypatch.setattr(cli, "probe", read)


def test_launch_line_shows_the_confirmed_resolution_not_the_claim() -> None:
    """«Моана 2»: имя обещает 1080p, ffprobe читает 1150×574 — печатаем факт."""
    assert cli.quality_text(rel(quality="1080p"), Media(5977.0, (), "h264", 574, 1150)) == "574p"
    assert cli.quality_text(rel(quality="1080p"), Media(5977.0, (), "h264", 1080, 1920)) == "1080p"
    # ffprobe высоту не отдал - врать нечем, остаётся заявка имени и честный «?».
    assert cli.quality_text(rel(quality="720p"), Media(5977.0, (), "h264", 0)) == "720p"
    assert cli.quality_text(rel(quality=None), Media(5977.0, (), "h264", 0)) == "?"


def test_cropped_widescreen_is_not_a_liar() -> None:
    """1080p с обрезанными чёрными полями — это 800 строк при 1920 в ширину, и релиз
    честен: судить по одной высоте нельзя, иначе каждый скоуп-фильм объявляется враньём.
    """
    scope = Media(5977.0, (), "h264", 800, 1920)
    assert scope.quality == "1080p" and cli.understated(rel(quality="1080p"), scope) == ""
    liar = Media(5977.0, (), "h264", 574, 1150)  # живая «Моана 2», верх выдачи
    assert liar.quality == "574p" and cli.understated(rel(quality="1080p"), liar) != ""
    # Имя не назвало ничего, а внутри HD - придираться не к чему.
    assert cli.understated(rel(quality=None), Media(5977.0, (), "h264", 720, 1280)) == ""
    assert cli.understated(rel(quality=None), liar) != ""


def test_a_top_that_turns_out_to_be_sd_gives_way_to_a_confirmed_1080p(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Живая выдача по «Моане 2»: верх ``WEB-DL-AVC`` 3.14 ГБ / 140 сидов — 1150×574,
    а вторым лежит настоящий 1080p 13.3 ГБ со 121 сидом. Играть обязан второй, и вслух.
    """
    ranked = [
        rel(name="Моана 2 [WEB-DL-AVC] 2x Dub", quality=None, size_gb=3.14, seeders=140),
        rel(name="Моана 2 [WEB-DL 1080p] Dub", codec=None, size_gb=13.33, seeders=121),
    ]
    _reads(
        monkeypatch,
        ranked,
        Media(5977.0, (), "h264", 574, 1150),
        Media(5977.0, (), "h264", 1080, 1920),
    )
    torrserver = _FakeTorrServer()

    prep = _resolve(cli._Bench(cast(Any, torrserver)), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 2, "среди честных обсиженность решает, но 574p - не честный 1080p"
    assert "релиз 1 на деле 574p - беру 2 (настоящий 1080p)" in printed
    assert torrserver.dropped, "отвергнутый верх не доедает полосу роя"


def test_an_honest_top_is_played_without_a_word(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Верх подтвердил своё имя — никаких проверок соседей и никаких лишних строк.

    Обсиженность остаётся главным критерием среди честных: 1080p со 140
    сидами не уступает 1080p со 121, сколько бы тот ни весил.
    """
    ranked = [
        rel(name="Кино [WEB-DL 1080p] a", size_gb=3.14, seeders=140),
        rel(name="Кино [BDRemux 1080p] b", size_gb=13.33, seeders=121),
    ]
    _reads(
        monkeypatch,
        ranked,
        Media(5977.0, (), "h264", 1080, 1920),
        Media(5977.0, (), "h264", 1080, 1920),
    )

    prep = _resolve(cli._Bench(cast(Any, _FakeTorrServer())), ranked)

    assert prep.number == 1
    assert not re.search(r"беру \d", capsys.readouterr().out)


def test_when_the_neighbour_lies_too_we_play_the_truth_out_loud(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Сосед обещал 1080p, а внутри такой же SD: подмены нет — но и молчания тоже нет."""
    ranked = [
        rel(name="Кино [WEB-DL] a", quality=None, size_gb=3.14, seeders=140),
        rel(name="Кино [WEB-DL 1080p] b", codec=None, size_gb=3.20, seeders=121),
    ]
    _reads(
        monkeypatch,
        ranked,
        Media(5977.0, (), "h264", 574, 1150),
        Media(5977.0, (), "h264", 576, 1024),
    )

    prep = _resolve(cli._Bench(cast(Any, _FakeTorrServer())), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 1, "лучше 574p рядом нет - играем то, что есть"
    assert "релиз 2 не лучше (576p)" in printed
    assert "релиз 1 на деле 574p - честнее рядом нет, играю его" in printed


def test_a_named_release_is_never_second_guessed_for_quality(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--release N`` неприкосновенен и здесь: человек выбрал сам."""
    ranked = [
        rel(name="Кино [WEB-DL] a", quality=None, size_gb=3.14, seeders=140),
        rel(name="Кино [WEB-DL 1080p] b", codec=None, size_gb=13.33, seeders=121),
    ]
    _reads(
        monkeypatch,
        ranked,
        Media(5977.0, (), "h264", 574, 1150),
        Media(5977.0, (), "h264", 1080, 1920),
    )

    prep = _resolve(cli._Bench(cast(Any, _FakeTorrServer())), ranked, release=1)

    assert prep.number == 1
    assert not re.search(r"беру \d", capsys.readouterr().out)


def test_a_slow_neighbour_does_not_hold_up_the_show(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Честный сосед не ответил за бюджет — играем то, что готово, и говорим об этом.

    Лишние секунды старта хуже, чем 574p, а молчаливо ждать «а вдруг» — это ровно тот
    случай, из-за которого показ когда-то вставал насмерть.
    """
    ranked = [
        rel(name="Кино [WEB-DL] a", quality=None, size_gb=3.14, seeders=140),
        rel(name="Кино [WEB-DL 1080p] b", codec=None, size_gb=13.33, seeders=121),
    ]
    slow = threading.Event()

    def read(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        if f"hash-{ranked[1].magnet}/" in url:  # честный сосед на холодном рое
            slow.wait(5.0)
            return Media(5977.0, (), "h264", 1080, 1920)
        return Media(5977.0, (), "h264", 574, 1150)

    monkeypatch.setattr(cli, "probe", read)
    monkeypatch.setattr(cli, "HONEST_BUDGET", 0.3)

    try:
        prep = _resolve(cli._Bench(cast(Any, _FakeTorrServer())), ranked)
    finally:
        slow.set()  # поток прогрева отпускаем, чтобы не висел до конца прогона

    assert prep.number == 1
    assert "релиз 2 не успел ответить" in capsys.readouterr().out


def test_a_refusal_names_the_living_parts_of_the_franchise(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Годного релиза нет - но соседки по франшизе в каталоге живые, и о них говорят.

    Раньше отказ отправлял человека разбираться руками (`cast releases <запрос>`), молча
    зная, что в той же выдаче лежат другие части с живыми раздачами. Подсказка - строка,
    и только: сама она ничего не запускает, подмена картины была бы обманом.
    """
    from torrcast.parse import Picture

    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(5)]
    _probes(monkeypatch, ranked, "av1", "mpeg2video", "vc1")
    plan = _plan(ranked)
    plan.kin = [
        Picture(title="Тачки 2", year=2011, releases=[rel(name="c2", seeders=30)]),
        Picture(title="Тачки 3", year=2017, releases=[rel(name="c3", seeders=40)]),
    ]
    args = cli.Args(query=["тачки"])
    with pytest.raises(NotFoundError) as caught, Progress(out=io.StringIO()) as progress:
        cli._Bench(cast(Any, _FakeTorrServer())).resolve(plan, args, progress)

    assert "годного релиза нет" in str(caught.value)
    assert "в каталоге есть Тачки 2 (2011), Тачки 3 (2017) - cast тачки 2" in str(caught.value)
    capsys.readouterr()


def test_a_refusal_stays_silent_when_the_franchise_has_no_other_parts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Предлагать нечего - и строки нет: пустой подсказки человек не заслужил."""
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(5)]
    _probes(monkeypatch, ranked, "av1", "mpeg2video", "vc1")
    with pytest.raises(NotFoundError) as caught:
        _resolve(cli._Bench(cast(Any, _FakeTorrServer())), ranked)

    assert "в каталоге есть" not in str(caught.value)
    capsys.readouterr()


def test_only_parts_that_stayed_out_of_the_menu_are_offered() -> None:
    """Подсказка не пересказывает меню: там человек эти картины уже видел.

    А вот часть франшизы, до меню не доехавшая (запрос попал в свою половину двуязычной
    франшизы либо у картины не осталось прошедших отбор релизов), - ровно то новое, что
    отказу есть сказать. Мёртвую, без единой раздачи, не предлагаем и её.
    """
    from torrcast.parse import Picture, cluster

    pictures = cluster(
        [
            _named_release("Тачки", 2006),
            _named_release("Тачки 2", 2011),
            _named_release("Тачки 3", 2017),
        ]
    )
    lead = next(p for p in pictures if p.year == 2006)

    kin = cli._kin(lead, pictures, {lead.key})
    assert [p.title for p in kin] == ["Тачки 2", "Тачки 3"]
    # Показанное в меню не повторяем.
    shown = {p.key for p in pictures if p.year != 2017}
    assert [p.title for p in cli._kin(lead, pictures, shown)] == ["Тачки 3"]
    # Картина без раздач в каталоге не «живая» - о ней молчим.
    assert cli._kin(lead, [*pictures, Picture(title="Тачки 4", year=2029)], {lead.key}) == kin
    assert cli.kin_line([]) == ""


def _named_release(title: str, year: int) -> Release:
    """Раздача с настоящим именем картины: кластеру нужно именно оно, а не «Кино»."""
    from torrcast.parse import parse_release_name

    return parse_release_name(f"{title} ({year}) BDRip 1080p")


# --- Потолок одновременных раздач (TC-145) -------------------------------------------


def test_a_picture_we_did_not_choose_stops_being_warmed_the_moment_we_choose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Картина выбрана - прогревы ОСТАЛЬНЫХ картин убираются сразу, а не после отбора.

    Раньше они доживали до :meth:`~torrcast.cli._Bench.keep_only`, то есть до конца
    отбора: до :data:`~torrcast.cli.PICK_BUDGET` секунд две-три чужие раздачи тянули
    куски у той единственной, которую мы вот-вот покажем.

    Внутри выбранной картины не убирается ничего: запасной релиз греется параллельно
    верху намеренно, и распорядиться им вправе только сам отбор.
    """
    torrserver = _FakeTorrServer()
    bench = cli._Bench(cast(Any, torrserver))
    mine = _franchise_plan("Кино", 1999, [rel(name=f"a{i}", seeders=100 - i) for i in range(3)])
    other = _franchise_plan("Кино 2", 2005, [rel(name=f"b{i}", seeders=100 - i) for i in range(3)])
    bench.start(mine, 1)
    bench.spare(mine, cli.Args(query=["кино"]))
    bench.start(other, 1)
    assert len(bench.live()) == 3

    bench.keep_plan(mine)

    assert sorted(prep.number for prep in bench.live()) == [1, 2], "верх и запасной - живы"
    assert [key[0] for key, _ in bench.preps.items() if not _.dropped] == [
        mine.picture.key,
        mine.picture.key,
    ]
    assert torrserver.dropped, "чужая картина убрана по своему хэшу, а не «всё из списка»"


def test_we_never_hold_more_torrents_at_once_than_the_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Жёсткий потолок: сколько бы ни длился перебор, одновременно держим не больше
    :data:`~torrcast.cli.MAX_LIVE` раздач.

    TorrServer падает по таймеру раз в 15 минут тем вероятнее, чем больше раздач
    он тянет; до потолка очередь перебора поднимала по раздаче за попытку, а убиралось
    всё разом только перед стартом показа.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(12)]
    _probes(monkeypatch, ranked, *(["h264"] * 11), "h264")
    torrserver = _FakeTorrServer()
    bench = cli._Bench(cast(Any, torrserver))
    plan = _plan(ranked)
    peak = 0

    # Прогрев под меню: три картины и запасной - это и есть пик, который потолок терпит.
    for number in range(1, cli.PREWARM + 1):
        bench.start(plan, number)
    bench.spare(plan, cli.Args(query=["кино"]))
    peak = max(peak, len(bench.live()))
    for number in range(cli.PREWARM + 1, len(ranked) + 1):
        bench.needed = {(plan.picture.key, number)}
        bench.start(plan, number)
        peak = max(peak, len(bench.live()))

    assert peak == cli.MAX_LIVE == 4
    assert len(bench.preps) == len(ranked), "греть перестали не потому, что не начинали"


def test_the_ceiling_never_kills_the_warmup_someone_is_waiting_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Потолок убирает самый СТАРЫЙ ненужный прогрев и никогда - нужный.

    Запасной релиз греется параллельно верху намеренно (замеренный выигрыш 5 с), и
    убить его потолком значило бы вернуть человеку полную цену подъёма второй раздачи.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(6)]
    _probes(monkeypatch, ranked, *(["h264"] * 6))
    bench = cli._Bench(cast(Any, _FakeTorrServer()))
    plan = _plan(ranked)
    for number in (1, 2, 3, 4):
        bench.start(plan, number)
    bench.needed = {(plan.picture.key, 1), (plan.picture.key, 2)}

    bench.start(plan, 5)

    live = sorted(prep.number for prep in bench.live())
    assert 1 in live and 2 in live, "тех, чьего ответа ждут, потолок не трогает"
    assert 3 not in live, "самый старый из ненужных и уходит"
    assert 5 in live


def test_a_neighbour_asked_about_honesty_is_dropped_once_it_has_answered(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Проверка «честного HD» спрашивает соседей по одному - и отпускает их сразу.

    До сих пор отвергнутый сосед доживал до старта показа: до трёх лишних раздач
    (:data:`~torrcast.cli.MAX_TRIES`) в тот самый момент, когда полоса роя нужна показу.
    """
    ranked = [
        rel(name="Кино [WEB-DL] a", quality=None, size_gb=3.14, seeders=140),
        rel(name="Кино [WEB-DL 1080p] b", codec=None, size_gb=3.20, seeders=121),
    ]
    _reads(
        monkeypatch,
        ranked,
        Media(5977.0, (), "h264", 574, 1150),
        Media(5977.0, (), "h264", 576, 1024),
    )
    torrserver = _FakeTorrServer()

    prep = _resolve(cli._Bench(cast(Any, torrserver)), ranked)

    assert prep.number == 1, "лучше 574p рядом нет - играем то, что есть"
    assert "не лучше" in capsys.readouterr().out
    assert torrserver.dropped == [f"hash-{ranked[1].magnet}"], "сосед отпущен по своему хэшу"


def test_a_neighbour_that_missed_its_budget_is_let_go_too(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Сосед не успел ответить за свой бюджет - раздача его тоже больше не нужна.

    Ждать перестали - значит, ответ не нужен, а раздача осталась бы висеть до общей
    уборки, доедая полосу роя у того, кого мы прямо сейчас играем. Подъём, который в его
    потоке ещё идёт, убирает себя сам: хэш к тому моменту известен только этому потоку.
    """
    ranked = [
        rel(name="Кино [WEB-DL] a", quality=None, size_gb=3.14, seeders=140),
        rel(name="Кино [WEB-DL 1080p] b", codec=None, size_gb=3.20, seeders=121),
    ]
    slow = f"hash-{ranked[1].magnet}"
    honest = Media(5977.0, (), "h264", 574, 1150)

    def read(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        if f"{slow}/" in url:
            time.sleep(0.6)  # сосед отвечает дольше, чем ему отмерено
            return Media(5977.0, (), "h264", 1080, 1920)
        return honest

    monkeypatch.setattr(cli, "probe", read)
    monkeypatch.setattr(cli, "HONEST_BUDGET", 0.05)
    torrserver = _FakeTorrServer()

    prep = _resolve(cli._Bench(cast(Any, torrserver)), ranked)

    assert prep.number == 1, "ответа не дождались - играем то, что уже прочитано"
    assert "не успел ответить" in capsys.readouterr().out
    deadline = time.monotonic() + 5.0
    while slow not in torrserver.dropped and time.monotonic() < deadline:
        time.sleep(0.05)
    assert torrserver.dropped == [slow], "и его раздача убрана по своему хэшу, а не по списку"


# --- Пак, который считает сезоны, но не серии (TC-139) --------------------------------


def _series_release(name: str, size_gb: float, seeders: int) -> Release:
    """Раздача сериала прямо из живой выдачи «Чёрных парусов» - именем и размером."""
    from torrcast.parse import parse_release_name

    return replace(
        parse_release_name(name), size=int(size_gb * 1e9), seeders=seeders, magnet=f"magnet:{name}"
    )


def test_a_multi_season_pack_that_hides_its_bitrate_stops_outranking_the_live_one() -> None:
    """🟡 «Чёрные паруса»: перебор упирался в старьё, у которого имя молчит обо всём.

    ``[S01-04] (2014-2017) HDTV-AlexFilm`` не называет ни разрешения, ни кодека и серий
    не считает - :func:`~torrcast.cli.bitrate_of` на нём отдаёт ноль, и раздача с ОДНИМ
    сидом вставала в очереди выше сериала на 61 сид. Три таких верха подряд - это три
    приговора ``mpeg4``, весь :data:`~torrcast.cli.MAX_TRIES` и 130 секунд, после которых
    показ говорит «годного релиза нет» при живом каталоге.
    """
    from torrcast.cli import is_dated, pack_mbit

    tv = RUNTIME_GUESS["tv"]
    pda = _series_release(
        "Чёрные паруса / Black Sails [S01-04] (2014-2017) HDRip, WEB-DL, HDTV | КПК", 10.24, 1
    )
    hdtv = _series_release(
        "Чёрные паруса / Black Sails [S01-04] (2014-2017) HDTV-AlexFilm", 27.24, 1
    )
    honest = _series_release(
        "Черные паруса / Black Sails [S01-04] (2014-2017) BDRip 720p-AlexFilm", 114.21, 1
    )

    assert round(pack_mbit(pda, tv), 1) == 1.3
    assert round(pack_mbit(hdtv, tv), 1) == 3.4
    assert round(pack_mbit(honest, tv)) == 14
    assert is_dated(pda, tv) and is_dated(hdtv, tv)
    assert not is_dated(honest, tv), "114 ГБ на четыре сезона - настоящий 720p, не старьё"


def test_the_pack_ceiling_never_judges_a_release_only_orders_it() -> None:
    """Потолок пака - это ПОРЯДОК и только он: ворота отбора считают, как считали.

    Отдельно от :func:`~torrcast.cli.bitrate_of` он живёт нарочно: тот кормит
    :func:`~torrcast.cli.is_candidate`, и потолок в воротах означал бы «слишком тяжёлый»,
    то есть отказ показывать честный 114-гигабайтный пак.
    """
    from torrcast.cli import bitrate_of, is_candidate, pack_mbit

    tv = RUNTIME_GUESS["tv"]
    honest = _series_release(
        "Черные паруса / Black Sails [S01-04] (2014-2017) BDRip 720p-AlexFilm", 114.21, 1
    )
    assert bitrate_of(honest, tv) == 0.0, "серий имя не считает - ворота молчат, как молчали"
    assert is_candidate(honest, tv, 16.0), "и кандидатом он остаётся"
    assert round(pack_mbit(honest, tv)) == 14, "а порядок при этом знает про него больше"

    # Имя, которое серии ПОСЧИТАЛО, потолком не судится вовсе: там есть настоящее число.
    counted = _series_release(
        "Чёрные Паруса / Black Sails / S1E1-8 of 8 (2014) [HDRip] MVO (LostFilm)", 8.91, 9
    )
    assert counted.episode_count == 8
    assert pack_mbit(counted, tv) == 0.0


def test_the_live_series_climbs_over_the_silent_one_seed_packs() -> None:
    """Порядок очереди на живой выдаче «Чёрных парусов»: 61 сид поднимается с 5-го на 3-е.

    Требований это не смягчает ни на знак - mpeg4 как отбраковывался ffprobe, так и
    отбраковывается. Меняется только то, до какого места очереди перебор доходит,
    прежде чем упрётся в бюджет попыток.
    """
    tv = RUNTIME_GUESS["tv"]
    releases = [
        _series_release(
            "Черные паруса / Black Sails [S01-04] (2014-2017) BDRip 720p-AlexFilm", 114.21, 1
        ),
        _series_release("Чёрные паруса / Black Sails [S01-04] (2014-2017) HDTV-AlexFilm", 27.24, 1),
        _series_release("Чёрные Паруса / Black Sails [S01] (2014) HDTV 720p-BaibaKo", 17.32, 1),
        _series_release(
            "Чёрные паруса / Black Sails [S01-04] (2014-2017) HDRip, WEB-DL, HDTV | КПК", 10.24, 1
        ),
        _series_release(
            "Чёрные Паруса / Black Sails / Сезоны: 1-4 / E1-38 of 38 (2014-2017) "
            "[HDRip] MVO (LostFilm)",
            32.53,
            61,
        ),
    ]

    order = [r.size for r in rank_releases(releases, tv, 16.0)]

    assert order.index(int(32.53 * 1e9)) == 2, "живой сериал третий, а не пятый"
    assert order.index(int(27.24 * 1e9)) > 2, "молчаливые односидные паки ушли ниже него"
    assert order.index(int(10.24 * 1e9)) > 2
    assert order[0] == int(114.21 * 1e9), "честный 720p с верха не сходит"
