"""Прогрев показа на диск (:mod:`torrcast.warm`): что греется, как это читает показ,
как убирается и почему обрыв связи перестал быть смертью.

Живьём это проверяется на телевизоре с реально выключенным интернетом; здесь — регрессия
на синтетическом ролике и на арифметике бюджета, которая укладывается в секунды.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from tests.conftest import CLIP_SECONDS, free_port
from torrcast.cli import Watch as _Watch
from torrcast.cli import _Clock, _play
from torrcast.state import Config, Entry, State
from torrcast.stream import Feed, Grid, Packer, ffmpeg_pack_command, hls_dir, segment_name
from torrcast.warm import (
    FREE_FLOOR,
    GUARD_HIGH,
    GUARD_LOW,
    META,
    STARVE_GRACE,
    Vault,
    Warmer,
    warm_key,
)


def _vault(tmp_path: Path, key: str = "k", budget: int = 1 << 30, floor: int = 0) -> Vault:
    vault = Vault(root=tmp_path / "warm", key=key, budget=budget, floor=floor)
    vault.open()
    return vault


def _lay(vault: Vault, slot: int, size: int = 1024) -> Path:
    path = vault.path(slot)
    path.write_bytes(b"x" * size)
    return path


def _grid() -> Grid:
    return Grid.uniform(float(CLIP_SECONDS))


def test_the_key_changes_with_everything_that_changes_the_bytes() -> None:
    """Ключ каталога обязан меняться от всего, от чего меняется содержимое куска.

    Иначе прогретое прошлого прогона подсунется под чужими именами: та же ``v7.ts``, но
    другая дорожка или другой битрейт перекода — и показ отдаст приёмнику не то кино.
    """
    from torrcast.recode import Encode

    grid = _grid()
    base = warm_key("http://ts/stream?link=abc&index=1", 0, grid)
    assert base == warm_key("http://ts/stream?link=abc&index=1", 0, grid), "ключ нестабилен"
    assert base != warm_key("http://ts/stream?link=abc&index=2", 0, grid), "другой файл"
    assert base != warm_key("http://ts/stream?link=abc&index=1", 1, grid), "другая дорожка"
    assert base != warm_key("http://ts/stream?link=abc&index=1", 0, Grid.uniform(120.0)), "сетка"
    assert base != warm_key(
        "http://ts/stream?link=abc&index=1", 0, grid, Encode(preset="ultrafast", mbit=9.0)
    ), "перекод даёт другие байты под тем же именем"


def test_the_show_reads_the_warmed_piece_without_touching_the_packer(tmp_path: Path) -> None:
    """Прогретый кусок отдаётся сразу и не поднимает ни одного ffmpeg.

    Это и есть обещание прогрева: перемотка в прогретую зону не ждёт ни упаковки, ни сети.
    """
    vault = _vault(tmp_path)
    warmed = _lay(vault, 3)
    out = hls_dir(str(tmp_path / "hls"))
    feed = Feed(source="нет", audio=0, out=out, grid=_grid(), vault=vault)

    assert feed.segment(3) == warmed, "прогретое не прочиталось"
    assert feed.packer is None, "ради прогретого куска поднялась упаковка"
    assert feed.have(3) and not feed.have(4)


def test_the_warmed_tail_counts_as_the_show_reserve(tmp_path: Path) -> None:
    """Запас показа считается и по прогретому: иначе сторож приёмника решил бы, что
    впереди пусто, и дёргал бы нуджем работающий показ (:meth:`Feed.front`)."""
    vault = _vault(tmp_path)
    grid = _grid()
    for slot in range(grid.count):
        _lay(vault, slot)
    out = hls_dir(str(tmp_path / "hls"))
    feed = Feed(source="нет", audio=0, out=out, grid=grid, vault=vault)

    assert feed.front(0.0) == pytest.approx(grid.duration), "прогретое не считается запасом"


def test_a_dead_source_stops_being_death_when_the_film_is_on_disk(tmp_path: Path) -> None:
    """Обрыв длиннее терпения: без прогретого это честная ошибка, с прогретым — честная
    строка и ожидание сети. Молчаливой смерти нет ни в том, ни в другом случае.
    """
    said: list[str] = []
    out = hls_dir(str(tmp_path / "hls"))
    naked = Feed(source="нет", audio=0, out=out, grid=_grid(), log=said.append)
    for _ in range(naked.limit + 1):
        packer = _corpse(tmp_path)
        assert naked._survive(packer) is (not naked.fatal)
    assert naked.fatal, "без прогретого показ обязан кончиться честной ошибкой"

    vault = _vault(tmp_path)
    _lay(vault, 0)
    warmed = Feed(source="нет", audio=0, out=out, grid=_grid(), vault=vault, log=said.append)
    for _ in range(2 * (warmed.limit + 1)):
        assert warmed._survive(_corpse(tmp_path)) is True, "показ умер, имея фильм на диске"
    assert not warmed.fatal and warmed.offline, "обрыв не отмечен вовсе"
    assert any("жду возврата сети" in line for line in said), "обрыв прошёл молча"


def _corpse(tmp_path: Path) -> Packer:
    """Труп прогона упаковки: процесс, который уже умер не по нашей воле."""
    proc = subprocess.Popen(["false"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.wait(timeout=10)
    return Packer(proc=proc, out=tmp_path, run=tmp_path / "run")


def test_the_budget_evicts_other_shows_by_age_and_never_the_own(tmp_path: Path) -> None:
    """Бюджет один на всё прогретое: новый показ вытесняет самый давний чужой, а свой
    каталог не трогает никогда — иначе прогрев ел бы сам себя.
    """
    root = tmp_path / "warm"
    for name, age in (("старый", 3000.0), ("свежий", 100.0)):
        other = Vault(root=root, key=name, floor=0)
        other.open()
        _lay(other, 0, size=400)
        os.utime(other.dir / META, (time.time() - age, time.time() - age))
    mine = Vault(root=root, key="мой", budget=1000, floor=0)
    mine.open()
    _lay(mine, 0, size=400)

    assert mine.fit(100) == "", "место обязано найтись за счёт чужого"
    assert not (root / "старый").exists(), "давний чужой каталог не вытеснен"
    assert (root / "свежий").exists() and mine.have(0), "вытеснено лишнее"
    assert "бюджет" in mine.fit(1 << 40), "бюджет не удержан"


def test_the_budget_leaves_the_disk_room_to_breathe(tmp_path: Path) -> None:
    """Диску не дают лопнуть: даже пустой бюджет не разрешает залезть в последние
    гигабайты раздела — рядом живут и state, и раздача, и система."""
    vault = _vault(tmp_path, budget=1 << 62, floor=FREE_FLOOR)
    assert "запас" in vault.fit(vault.free() - FREE_FLOOR // 2), "прогрев готов забить раздел"


def test_warming_lays_the_whole_clip_on_disk_and_reports_it(clip: str, tmp_path: Path) -> None:
    """Главное обещание: фоном на диск ложится ВЕСЬ ролик, теми же именами той же сетки,
    и прогрев сам говорит, докуда дошёл.
    """
    grid = _grid()
    vault = _vault(tmp_path)
    said: list[str] = []
    # Запас показа тут никто не меряет: прогрев проверяется сам по себе, без живой
    # упаковки рядом, - поэтому сразу отдаём ему «запас есть» (:meth:`Warmer._wait_for_picture`).
    warmer = Warmer(
        source=clip, audio=0, grid=grid, vault=vault, rate=0.0, slack=1e6, log=said.append
    )
    warmer.start()
    deadline = time.monotonic() + 120
    while not warmer.done and time.monotonic() < deadline:
        time.sleep(0.5)
    warmer.stop()

    assert warmer.done, f"прогрев не дошёл до конца: {warmer.line()}"
    assert warmer.warmed == pytest.approx(grid.duration), "прогрето меньше, чем сказано"
    assert "прогрето" in warmer.line() and "интернет больше не нужен" in warmer.line()
    for slot in range(grid.count):
        assert vault.path(slot).stat().st_size > 0, f"кусок {segment_name(slot)} пуст"
    assert not (vault.dir / "run").exists(), "каталог прогона остался мусором"


def test_the_show_end_takes_the_warmed_film_off_the_disk(
    clip: str, tls: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Досмотрено — прогретое стирается. Держать на диске фильм, который уже посмотрели,
    незачем ни минуты: это те же гигабайты, что и у следующего.
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    warm = tmp_path / "warm"
    monkeypatch.setenv("TORRCAST_WARM", str(warm))
    length = float(CLIP_SECONDS)
    key = "movie:ролик:2026"
    entry = Entry(title="ролик", magnet="magnet:?xt=1", dur=length)
    state = State()
    state.put(key, entry)
    state.save()

    config = Config(
        receiver="mock",
        tv="127.0.0.1",
        hls_dir=str(tmp_path / "hls"),
        hls_cert=tls[0],
        hls_key=tls[1],
        hls_port=free_port(),
        hls_readrate=0.0,
        hls_keyframes=False,
        warm=True,
    )
    watch = _Watch(key=key, entry=entry, every=0.0)
    assert _play(config, clip, 0, "тест", _Clock(), watch=watch) == 0

    assert watch.done, "ролик не досмотрен - проверять уборку не на чем"
    assert not any(warm.rglob("v*.ts")), "прогретое пережило досмотренный показ"
    saved = State.load().get(key)
    assert saved is not None and saved.warm >= 0.0, "прогрев не виден состоянию"


def test_the_next_episode_starts_warming_only_when_this_one_is_on_disk(tmp_path: Path) -> None:
    """Серия прогрета целиком - прогрев берётся за следующую, и ровно за одну.

    Раньше этого момента следующая серия не имеет права ни на байт раздачи: обрыв бьёт по
    тому, что смотрят прямо сейчас. А после - обязана, иначе автопереход на стыке серий
    упрётся в мёртвую раздачу при полном диске кино рядом.
    """
    grid = _grid()
    mine = _vault(tmp_path, key="эта")
    for slot in range(grid.count):
        _lay(mine, slot)
    calls: list[int] = []
    nxt = Warmer(source="s2", audio=0, grid=grid, vault=_vault(tmp_path, key="следующая"))

    def follow() -> Warmer:
        calls.append(1)
        return nxt

    warmer = Warmer(source="s1", audio=0, grid=grid, vault=mine, follow=follow, slack=999.0)
    warmer._work()

    assert warmer.done and warmer.after is nxt, "следующая серия не взята в работу"
    assert nxt.thread is not None and calls == [1], "фабрика зовётся не один раз"
    assert mine.key in nxt.vault.keep, "текущая серия не защищена от бюджета следующей"
    warmer.stop()
    assert nxt.stopped, "снятие показа обязано снимать и прогрев следующей серии"


def test_the_next_episode_is_not_warmed_while_this_one_is_not_done(tmp_path: Path) -> None:
    """Недогретая серия ни при каких условиях не уступает место следующей."""
    grid = _grid()
    warmer = Warmer(
        source="s1",
        audio=0,
        grid=grid,
        vault=_vault(tmp_path, key="эта", budget=1),
        follow=lambda: pytest.fail("прогрев следующей серии полез раньше времени"),
        slack=999.0,
    )
    warmer._work()
    assert warmer.trouble and warmer.after is None, "следующая серия взята при недогретой текущей"


def test_the_budget_never_evicts_the_episode_being_watched(tmp_path: Path) -> None:
    """Прогрев следующей серии не имеет права выесть ту, которую смотрят.

    Соседняя серия - формально чужой каталог, и он же самый давний: без защиты бюджет
    сносил бы именно её, то есть ровно то, ради чего прогрев и заведён.
    """
    root = tmp_path / "warm"
    for name, age in (("текущая", 3000.0), ("чужая", 2000.0)):
        other = Vault(root=root, key=name, floor=0)
        other.open()
        _lay(other, 0, size=400)
        os.utime(other.dir / META, (time.time() - age, time.time() - age))
    nxt = Vault(root=root, key="следующая", budget=1000, floor=0, keep=frozenset({"текущая"}))
    nxt.open()

    assert nxt.fit(300) == "", "место обязано найтись за счёт по-настоящему чужого"
    assert (root / "текущая").exists(), "выедена серия, которую смотрят прямо сейчас"
    assert not (root / "чужая").exists(), "давний чужой каталог не вытеснен"


class _FakeProc:
    """Процесс-заглушка: копит сигналы, которыми его придерживают и отпускают."""

    def __init__(self) -> None:
        self.signals: list[int] = []

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)


class _FakePacker:
    def __init__(self) -> None:
        self.proc = _FakeProc()


def _warmer(tmp_path: Path) -> Warmer:
    return Warmer(source="s", audio=0, grid=_grid(), vault=_vault(tmp_path))


def test_a_tight_but_healthy_show_wakes_warming_before_guard_high(tmp_path: Path) -> None:
    """Показ вплотную за упаковкой держит запас между порогами и до GUARD_HIGH не дотягивает.

    Раньше замерший прогрев в этой полосе стоял вечно, «прогрета целиком» не наступало, и
    следующая серия так и не бралась в работу. Теперь выдержка над GUARD_LOW оживляет его.
    Одного касания над порогом мало - показ должен подтвердить, что запас держится.
    """
    warmer = _warmer(tmp_path)
    warmer.idle = True
    warmer.slack = (GUARD_LOW + GUARD_HIGH) / 2
    assert warmer._may_resume() is False, "прогрев ожил от одного касания над порогом"
    assert warmer.healthy_since > 0.0, "выдержка здоровья не пошла"

    warmer.healthy_since = time.monotonic() - STARVE_GRACE - 1.0
    assert warmer._may_resume() is True, "здоровый, но тесный показ не оживил прогрев - голодание"


def test_a_really_low_reserve_keeps_warming_stopped_no_matter_how_long(tmp_path: Path) -> None:
    """Реально просевший запас держит прогрев замершим сколько угодно долго: живой показ
    важнее, и никакая выдержка не оживляет прогрев ниже GUARD_LOW."""
    warmer = _warmer(tmp_path)
    warmer.idle = True
    warmer.slack = GUARD_LOW - 5.0
    warmer.healthy_since = time.monotonic() - STARVE_GRACE - 100.0
    assert warmer._may_resume() is False, "прогрев ожил под реально просевшим запасом"
    assert warmer.healthy_since == 0.0, "просадка не обнулила выдержку - здоровье зачлось ложно"


def test_a_far_ahead_show_wakes_warming_at_once(tmp_path: Path) -> None:
    """Классический выход из простоя цел: запас за GUARD_HIGH оживляет прогрев сразу."""
    warmer = _warmer(tmp_path)
    warmer.idle = True
    warmer.slack = GUARD_HIGH + 1.0
    assert warmer._may_resume() is True, "запас за GUARD_HIGH не оживил прогрев"


def test_throttle_stops_on_drop_then_wakes_on_sustained_health(tmp_path: Path) -> None:
    """Сквозь ``_throttle``: просадка замораживает, тесное здоровье со временем размораживает,
    и вечного голодания в полосе между порогами больше нет."""
    import signal

    warmer = _warmer(tmp_path)
    packer = _FakePacker()

    warmer.slack = GUARD_LOW - 1.0
    warmer._throttle(packer)
    assert packer.proc.signals == [signal.SIGSTOP], "просадка не заморозила прогрев"

    warmer.slack = (GUARD_LOW + GUARD_HIGH) / 2
    warmer._throttle(packer)  # первое касание - только пошла выдержка
    assert signal.SIGCONT not in packer.proc.signals, "ожил раньше выдержки"

    warmer.healthy_since = time.monotonic() - STARVE_GRACE - 1.0
    warmer._throttle(packer)
    assert packer.proc.signals[-1] == signal.SIGCONT, "выдержка не разморозила прогрев"


def test_the_show_reserve_reaches_both_warmers(tmp_path: Path) -> None:
    """Просевший запас показа обязан ронять всю цепочку прогрева, а не только голову:
    и та и другая серия тянут из одной раздачи и жгут один процессор."""
    grid = _grid()
    nxt = Warmer(source="s2", audio=0, grid=grid, vault=_vault(tmp_path, key="следующая"))
    warmer = Warmer(source="s1", audio=0, grid=grid, vault=_vault(tmp_path, key="эта"), after=nxt)

    warmer.feed(12.0)
    assert (warmer.slack, nxt.slack) == (12.0, 12.0), "запас показа не дошёл до следующей серии"
    assert "следующая" in warmer.line() or not warmer.done, "строка прогрева врёт о цепочке"


# ------------------------------------------------- прогрев уступает живому перекоду


class _Rival:
    """Кодировщик живых кусков в двух состояниях: работает заход или нет."""

    def __init__(self, working: bool = False) -> None:
        self.working = working


def test_warming_freezes_while_the_live_recoder_has_a_run_in_flight(tmp_path: Path) -> None:
    """Замер: живой перекод под работающим прогревом теряет 30 % скорости (2.62x против
    1.84x), и ``nice 19`` этого не лечит - прогрев всё равно держит 128 % из 400 %.
    Процессор возвращает только пауза, поэтому заход кодировщика замораживает прогрев
    независимо от запаса показа - даже когда запас прекрасен.
    """
    import signal

    warmer = _warmer(tmp_path)
    packer = _FakePacker()
    warmer.rival = _Rival(working=True)
    warmer.slack = GUARD_HIGH + 100.0  # запас отличный: по старому правилу греть можно

    warmer._throttle(packer)
    assert packer.proc.signals == [signal.SIGSTOP], "прогрев не уступил живому перекоду"
    assert warmer.idle is True, "прогрев не отметил, что замер"
    assert "уступил перекоду" in warmer.line(), "строка прогрева не называет причину паузы"

    warmer.rival.working = False
    warmer._throttle(packer)
    assert packer.proc.signals[-1] == signal.SIGCONT, "заход кончился, а прогрев не ожил"


def test_a_freeze_for_the_recoder_outlives_a_healthy_reserve(tmp_path: Path) -> None:
    """Пока заход идёт, ничто не оживляет прогрев: ни запас за GUARD_HIGH, ни выдержка
    здоровья. Иначе первый же опрос вернул бы соседа кодировщику обратно."""
    import signal

    warmer = _warmer(tmp_path)
    packer = _FakePacker()
    warmer.rival = _Rival(working=True)
    warmer.slack = GUARD_HIGH + 100.0
    warmer.healthy_since = time.monotonic() - STARVE_GRACE - 100.0

    warmer._throttle(packer)
    warmer._throttle(packer)
    assert signal.SIGCONT not in packer.proc.signals, "прогрев ожил посреди чужого захода"


def test_warming_without_a_recoder_behaves_exactly_as_before(tmp_path: Path) -> None:
    """Фильм без тяжёлых кусков живёт без кодировщика вовсе, и правило про соседа не имеет
    права ни замораживать такой прогрев, ни держать его замершим."""
    import signal

    warmer = _warmer(tmp_path)
    packer = _FakePacker()
    warmer.slack = GUARD_HIGH + 1.0

    warmer._throttle(packer)
    assert packer.proc.signals == [], "прогрев замер без всякой причины"

    warmer.idle = True
    warmer._throttle(packer)
    assert packer.proc.signals == [signal.SIGCONT], "прогрев не ожил при отличном запасе"


def test_the_recoder_reaches_the_next_episode_warmer_too(tmp_path: Path) -> None:
    """Кодировщик у показа один, и уступать ему обязана вся цепочка прогрева: прогрев
    следующей серии жжёт тот же процессор, что и прогрев этой."""
    grid = _grid()
    rival = _Rival()
    nxt = Warmer(source="s2", audio=0, grid=grid, vault=_vault(tmp_path, key="следующая"))
    warmer = Warmer(source="s1", audio=0, grid=grid, vault=_vault(tmp_path, key="эта"), rival=rival)
    warmer.follow = lambda: nxt
    for slot in range(grid.count):
        _lay(warmer.vault, slot)

    warmer._chain()
    nxt.stop()
    assert nxt.rival is rival, "прогрев следующей серии не знает про кодировщика"


# --- TC-106: прогретый кусок и живой обязаны быть однородны ---------------------
# Куски одного показа приходят приёмнику из двух мест - из окна живой упаковки и с диска
# (:meth:`torrcast.stream.Feed.segment`), - и для приёмника это ОДНА лента. Если два
# производителя решают про кодирование по-разному, на стыке меняется SPS: другой профиль,
# другая энтропийная кодировка, другая глубина буфера кадров. Тесты ниже проверяют не
# аргументы ffmpeg, а выданные байты.


def _sps(path: Path) -> bytes:
    """Первый SPS (nal_unit_type 7) из готового куска - именно тот, что читает приёмник.

    Достаётся не через ``ffprobe -show_entries stream=profile``: паспорт печатает разбор,
    а сравнивать надо байты. Видеодорожка выкладывается как есть в Annex-B, и SPS в ней
    лежит целиком.
    """
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-map", "0:v:0", "-c", "copy", "-f", "h264", "-"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip
    starts = [i for i in range(len(raw) - 4) if raw[i : i + 3] == b"\x00\x00\x01"]
    for begin, end in zip(starts, [*starts[1:], len(raw)], strict=False):
        head = raw[begin + 3]
        if head & 0x1F == 7:
            return bytes(raw[begin + 3 : end]).rstrip(b"\x00")
    raise AssertionError(f"в {path.name} нет SPS - сравнивать нечего")


def test_a_light_film_is_warmed_by_the_very_copy_the_live_packing_gives(tmp_path: Path) -> None:
    """Один тяжёлый кусок не имеет права переводить ВЕСЬ прогрев на перекод.

    Улика, ради которой тест написан: на лёгком материале (5 тяжёлых кусков из 525) живая
    упаковка отдавала копию релиза, а прогрев клал на диск сплошной ``ultrafast`` - другой
    профиль, другая энтропийная кодировка. Решение обязано быть одно на обоих.
    """
    from torrcast.cli import _warmer
    from torrcast.recode import Encode

    class _Heavy:
        targets = (1, 4)
        encode = Encode(preset="veryfast", mbit=9.0)

    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    warmer = _warmer(config, "http://ts/stream?link=abc&index=1", 0, _grid(), 0.0, "кино",
                     recoder=_Heavy())  # fmt: skip

    assert warmer is not None
    assert warmer.encode is None, "прогрев ушёл в сплошной перекод там, где показ отдаёт копию"
    assert warmer.spots == (1, 4), "тяжёлые куски прогреву не названы"
    assert warmer.spot_encode is _Heavy.encode, "тяжёлое греется не тем, чем его отдаёт показ"


def test_an_undecodable_codec_still_recodes_both_the_show_and_the_warming(tmp_path: Path) -> None:
    """Обратная сторона того же правила: показ идёт сплошным перекодом - и прогрев тоже."""
    from torrcast.cli import _warmer
    from torrcast.recode import Encode

    whole = Encode(preset="ultrafast", mbit=6.0)
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    warmer = _warmer(config, "http://ts/stream?link=abc&index=1", 0, _grid(), 0.0, "кино",
                     whole=whole)  # fmt: skip

    assert warmer is not None and warmer.encode is whole, "прогрев разошёлся с показом"
    assert warmer.spots == (), "поверх сплошного перекода точечный перекод не нужен"


def test_the_warmed_film_is_homogeneous_and_its_heavy_piece_is_recoded(
    clip: str, tmp_path: Path
) -> None:
    """Настоящий прогон: SPS прогретых кусков совпадает с SPS копии ПОБАЙТОВО.

    Копия - это исходник как есть, поэтому сравнение идёт с куском, упакованным тем же
    ``-c:v copy``, каким его кладёт живая упаковка. Тяжёлый кусок - единственное место,
    где SPS меняется, и меняется он ровно там же и в живом показе.
    """
    from torrcast.recode import Encode

    grid = _grid()
    vault = _vault(tmp_path)
    spot = 1
    warmer = Warmer(
        source=clip, audio=0, grid=grid, vault=vault, rate=0.0, slack=1e6,
        spots=(spot,), spot_encode=Encode(preset="ultrafast", mbit=1.0),
    )  # fmt: skip
    warmer.start()
    deadline = time.monotonic() + 180
    while not warmer.done and time.monotonic() < deadline:
        time.sleep(0.5)
    warmer.stop()
    assert warmer.done, f"прогрев не дошёл до конца: {warmer.line()}"
    assert vault.spot(spot).exists(), "тяжёлый кусок так и остался копией"

    # Эталон - кусок живой упаковки того же места, снятый тем же кодом.
    live = tmp_path / "live"
    packer = Packer.start(
        ffmpeg_pack_command(clip, 0, str(live / "run"), grid, 0, grid.start(0), until=0),
        live, live / "run", 0, last=0,
    )  # fmt: skip
    deadline = time.monotonic() + 60
    while packer.edge < 0 and time.monotonic() < deadline:
        packer.publish()
        time.sleep(0.2)
    packer.stop(keep_files=True, reason="эталон снят")
    copied = _sps(live / segment_name(0))

    plain = [s for s in range(grid.count) if s != spot]
    for slot in plain:
        assert _sps(vault.path(slot)) == copied, (
            f"прогретый {segment_name(slot)} закодирован не так, как его кладёт упаковка"
        )
    assert _sps(vault.path(spot)) != copied, "тяжёлый кусок не перекодирован"
