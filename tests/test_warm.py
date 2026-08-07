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

from tests.conftest import CLIP_SECONDS
from torrcast.cli import Watch as _Watch
from torrcast.cli import _Clock, _play
from torrcast.state import Config, Entry, State
from torrcast.stream import Feed, Grid, Packer, hls_dir, segment_name
from torrcast.warm import FREE_FLOOR, META, Vault, Warmer, warm_key


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
    warmer = Warmer(source=clip, audio=0, grid=grid, vault=vault, rate=0.0, log=said.append)
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
        hls_port=18471,
        hls_readrate=0.0,
        hls_keyframes=False,
        warm=True,
    )
    watch = _Watch(key=key, entry=entry, every=0.0)
    assert _play(config, clip, 0, "тест", _Clock(), watch=watch) == 0

    assert watch.done, "ролик не досмотрен — проверять уборку не на чем"
    assert not any(warm.rglob("v*.ts")), "прогретое пережило досмотренный показ"
    saved = State.load().get(key)
    assert saved is not None and saved.warm >= 0.0, "прогрев не виден состоянию"
