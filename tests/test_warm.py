"""Прогрев показа на диск (:mod:`torrcast.warm`): что греется, как это читает показ,
как убирается и почему обрыв связи перестал быть смертью.

Живьём это проверяется на телевизоре с реально выключенным интернетом; здесь — регрессия
на синтетическом ролике и на арифметике бюджета, которая укладывается в секунды.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import CLIP_SECONDS, free_port
from torrcast import cli, trace
from torrcast.cast import MockReceiver, Position, trust_anchor
from torrcast.cli import Watch as _Watch
from torrcast.cli import _Clock, _play, _Stopped
from torrcast.state import Config, Entry, State
from torrcast.stream import (
    SPLIT_SLACK,
    Feed,
    Grid,
    Packer,
    ffmpeg_pack_command,
    hls_dir,
    pack_start,
    segment_name,
)
from torrcast.warm import (
    FREE_FLOOR,
    GUARD_HIGH,
    GUARD_LOW,
    HEAD_BYTES,
    META,
    RUN_DIR,
    SKEW_MAX,
    SKEW_TRIES,
    STARVE_GRACE,
    WARM_BUDGET,
    Vault,
    Warmer,
    segment_start,
    warm_key,
    warm_root,
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


def _warm_clip_for_show(clip: str, tmp_path: Path) -> Grid:
    """Прогреть ролик по-настоящему под тем ключом, который показ посчитает себе сам:
    копия, без точечных перекодов - решение лёгкого ролика. Возвращает сетку, по ней
    тест сверяет, что состояние увидело ровно столько, сколько лежит на диске.
    """
    grid = _grid()
    vault = Vault(
        root=warm_root(str(tmp_path / "warm")),
        key=warm_key(clip, 0, grid, None, ()),
        budget=1 << 30,
        floor=0,
        title="тест",
    )
    warmer = Warmer(source=clip, audio=0, grid=grid, vault=vault, rate=0.0, slack=1e6)
    warmer.start()
    deadline = time.monotonic() + 120
    while not warmer.done and time.monotonic() < deadline:
        time.sleep(0.5)
    warmer.stop()
    assert warmer.done, f"прогрев не дошёл до конца: {warmer.line()}"
    return grid


class _TurnedOff(MockReceiver):
    """Приёмник, который «выключили» на N-м опросе позиции - ровно как SIGTERM от
    ``cast stop``, только детерминированно: сигнал по часам проигрывал бы гонку
    заглушке, доигрывающей ролик за секунды."""

    def __init__(self, polls: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._left = polls

    def position(self, front: float = 0.0) -> Position:
        self._left -= 1
        if self._left == 0:
            raise _Stopped
        return super().position(front)


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


def test_a_warmed_copy_heavier_than_the_ceiling_is_not_a_warmed_piece(tmp_path: Path) -> None:
    """Прогретая копия тяжелее потолка приёмника наружу не идёт и запасом не считается.

    Прогрев кладёт фильм на диск копией, а тяжёлые места приводит к перекоду отдельным,
    поздним заходом (:meth:`torrcast.warm.Warmer._spots_left`). До него на месте тяжёлого
    куска лежит копия во весь свой вес, а показ берёт прогретое напрямую с диска - мимо
    обоих мест, где вес зажат потолком (:meth:`torrcast.stream.Packer.publish`,
    :meth:`torrcast.recode.Recoder.holding`).

    Замер на живом Q70D («Тачки» 2006, 1080p, 39% фильма тяжелее потолка): прогрев обгонял
    показ вчетверо, наружу уезжали прогретые копии по 17-44 МБ, и приёмник вставал на
    каждой - 32 ``BUFFERING`` и 20 пинков за 14 минут показа.

    Копию при этом не трогаем: точечный перекод ляжет ровно поверх неё.
    """
    vault = _vault(tmp_path)
    grid = _grid()
    out = hls_dir(str(tmp_path / "hls"))
    feed = Feed(source="нет", audio=0, out=out, grid=grid, vault=vault, cap=4096)
    light, heavy = _lay(vault, 0, size=4096), _lay(vault, 1, size=4097)

    assert feed.segment(0) == light, "лёгкий прогретый кусок не прочитался"
    assert feed._warm(1) is None, "прогретая копия тяжелее потолка уехала на ТВ"
    assert feed.have(0) and not feed.have(1), "тяжёлая копия числится готовым куском"
    assert feed.front(0.0) == pytest.approx(grid.end(0)), "тяжёлая копия зачлась запасом"
    assert heavy.exists(), "тяжёлую копию стёрли - точечному перекоду ложиться не на что"


def test_the_warmed_counter_names_only_what_the_show_can_take(tmp_path: Path) -> None:
    """«Прогрето NN» называет то, что показ возьмёт с диска, а не то, что просто лежит.

    Копия тяжелее потолка приёмника наружу не идёт (:meth:`torrcast.stream.Feed._warm`):
    под таким местом работает живая упаковка, и обрыва связи оно не переживёт. Замер
    («Тачки» 2006, 1080p): тяжелее потолка 38 % кусков - ровно на столько человеку и
    приписывался запас, которого у него нет.

    Заодно сверяется, что честный счёт не сдвинул укладку: прогреву тяжёлое место
    по-прежнему видно уложенным, иначе он перекладывал бы его вечно.
    """
    vault = _vault(tmp_path)
    grid = _grid()
    out = hls_dir(str(tmp_path / "hls"))
    feed = Feed(source="нет", audio=0, out=out, grid=grid, vault=vault, cap=4096)
    warmer = Warmer(source="нет", audio=0, grid=grid, vault=vault, cap=4096)
    _lay(vault, 0, size=4096)
    heavy = _lay(vault, 1, size=4097)

    assert feed._warm(1) is None, "потолок показа изменился - счёт прогрева меряет не то"
    assert warmer.warmed == pytest.approx(grid.span(0)), "тяжёлая копия зачлась прогретой"
    assert f"прогрето {cli._hms(grid.span(0))} из" in warmer.line(), "строка врёт про запас"
    assert vault.slots() == {0, 1}, "укладка потеряла кусок - прогрев переложит его заново"
    assert warmer._missing() == (2, grid.count - 1), "прогрев вернулся за уложенным куском"

    heavy.write_bytes(b"x" * 4096)  # точечный перекод лёг поверх копии
    assert warmer.warmed == pytest.approx(grid.span(0) + grid.span(1)), "перекод не зачёлся"


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


@pytest.mark.parametrize("movie_gb", [20.1, 20.7, 21.3])
def test_the_warm_budget_accepts_the_heavy_movies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, movie_gb: float
) -> None:
    """Три тяжёлых фильма, ради которых поднят бюджет, проходят проверку до записи."""
    vault = Vault(root=tmp_path / "warm", key="тяжёлый", floor=0)
    monkeypatch.setattr(Vault, "free", lambda _self: WARM_BUDGET * 2)
    assert vault.budget == WARM_BUDGET
    assert int(Config().warm_budget_gb * 1e9) == vault.budget, "конфиг разошёлся с хранилищем"
    assert vault.fit(int(movie_gb * 1e9)) == "", f"фильм {movie_gb} ГБ остался без страховки"


def test_the_budget_leaves_the_disk_room_to_breathe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Диску не дают лопнуть: даже пустой бюджет не разрешает залезть в последние
    гигабайты раздела — рядом живут и state, и раздача, и система."""
    vault = _vault(tmp_path, budget=1 << 62, floor=FREE_FLOOR)
    need = 21_300_000_000
    monkeypatch.setattr(Vault, "free", lambda _self: need + FREE_FLOOR - 1)
    refusal = vault.fit(need)
    assert "на разделе свободно" in refusal and "запас" in refusal, (
        "наш бюджет не должен скрывать нехватку чужого места"
    )


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
    """Досмотр под заглушкой доводит показ до конца и берётся за уборку прогретого, не
    падая на ней, а состояние перестаёт утверждать, что на диске что-то есть.

    Фильм прогревается по-настоящему ДО показа (:func:`_warm_clip_for_show`), поэтому
    «ничего не осталось» здесь - настоящее доказательство уборки: стирается реально
    уложенное. Тем же концом проверяется правда состояния наружу (TC-255): прогретое
    досмотренного стёрто, и ``warm`` обязан уйти в ноль - иначе сторонний щуп читал бы
    «фильм целиком на диске» про пустое место.
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    warm = tmp_path / "warm"
    monkeypatch.setenv("TORRCAST_WARM", str(warm))
    _warm_clip_for_show(clip, tmp_path)
    assert any(warm.rglob("v*.ts")), "стирать нечего - прогрев до показа не состоялся"
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

    assert watch.done, "ролик не досмотрен - до вызова уборки показ не дошёл"
    assert not any(warm.rglob("v*.ts")), "прогретое пережило досмотренный показ"
    saved = State.load().get(key)
    assert saved is not None and saved.done, "состояние не отметило досмотр"
    assert saved.warm == 0.0, "состояние врёт про прогретое, которого уже нет на диске"


def test_a_show_stopped_midway_leaves_the_warm_visible_outside(
    clip: str, tls: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Снятый посреди фильма показ оставляет прогрев видимым СНАРУЖИ процесса: щуп
    читает state.json и видит, сколько фильма лежит на диске (TC-255).

    Сценарий инцидента: журнал прогона честно писал «прогрето 0:22:46 из 0:22:46 -
    фильм целиком на диске», а в state.json поле ``warm`` оставалось нулём - снаружи
    прогрев не был виден вовсе. Здесь фильм прогрет по-настоящему до показа, а показ
    снимается до первого показанного кадра - ровно тот случай, где у сторожа не было
    ни одного штатного тика (``see`` не пишет, пока приёмник считает ноль), и спасти
    прогрев может только запись на выходе. Приёмник «выключается» на втором опросе -
    так устроен ``cast stop``, только без гонки с заглушкой, доигрывающей ролик за
    секунды.
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    warm = tmp_path / "warm"
    monkeypatch.setenv("TORRCAST_WARM", str(warm))
    grid = _warm_clip_for_show(clip, tmp_path)
    key = "movie:ролик:2026"
    entry = Entry(title="ролик", magnet="magnet:?xt=1", dur=float(CLIP_SECONDS))
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
    receiver = _TurnedOff(polls=2, ca=trust_anchor(tls[0]))
    monkeypatch.setattr(cli, "make_receiver", lambda *args, **kwargs: receiver)
    watch = _Watch(key=key, entry=entry, every=0.0)
    with pytest.raises(_Stopped):
        _play(config, clip, 0, "тест", _Clock(), watch=watch)

    saved = State.load().get(key)
    assert saved is not None and not saved.done, "показ успел досмотреться - снят не посреди"
    assert saved.warm == pytest.approx(grid.duration), "прогрев не виден снаружи показа"
    assert any(warm.rglob("v*.ts")), "прогретое стёрто с диска недосмотренного показа"


def test_the_vault_clear_wipes_the_warmed_directory(tmp_path: Path) -> None:
    """Уборка прогретого стирает каталог показа ЦЕЛИКОМ - и это сверяется на реально
    уложенных файлах, а не на пустом месте.

    Сквозной прогон (`test_the_show_end_takes_the_warmed_film_off_the_disk`) сверяет
    уборку целиком, но на одном счастливом пути. Здесь - сама :meth:`Vault.clear` и её
    тяжёлые случаи: кладём куски, точечную метку, паспорт и недобитый каталог прогона -
    и требуем, чтобы после уборки не осталось ни файла и ни каталога.
    """
    vault = _vault(tmp_path, key="досмотренный")
    for slot in range(4):
        _lay(vault, slot)
    vault.spot(1).touch()  # метка точечного перекода рядом с куском
    run = vault.dir / RUN_DIR
    run.mkdir()  # недобитый каталог прогона ffmpeg
    (run / "leftover.ts").write_bytes(b"x")
    assert vault.dir.exists() and any(vault.dir.rglob("v*.ts")), "класть было нечего"

    vault.clear()

    assert not vault.dir.exists(), "каталог прогретого пережил уборку"
    assert not any(vault.root.rglob("v*.ts")), "куски прогретого остались на диске"


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


def test_the_done_flag_counts_only_what_the_show_can_take(tmp_path: Path) -> None:
    """«Готово» и счётчик прогретого считают одно и то же - иначе строка врёт дважды.

    Копия тяжелее потолка приёмника показу не по зубам (:meth:`Feed._warm`), а «готово»
    смотрело на весь каталог: строка выходила вида «прогрето 50 мин из 60 - фильм
    целиком на диске, интернет больше не нужен» - два числа в ней противоречили хвосту,
    а хвост был неправдой. Человек выключил бы интернет и упёрся в темноту на первом же
    тяжёлом месте.
    """
    vault = _vault(tmp_path)
    grid = _grid()
    warmer = Warmer(source="s", audio=0, grid=grid, vault=vault, cap=4096)
    for slot in range(grid.count):
        _lay(vault, slot, size=4096)
    _lay(vault, 1, size=4097)

    # Оба состояния снимаем в переменные: сверяются они парой, и читать признак прямо в
    # `assert` нельзя - тайпчекер запомнит первый ответ и второй счёт просто выкинет.
    heavy, said = warmer.done, warmer.line()
    assert warmer.warmed < grid.duration
    assert not heavy, "тяжёлая копия зачлась готовой - строка соврёт про сеть"
    assert "интернет больше не нужен" not in said

    vault.path(1).write_bytes(b"x" * 4096)  # точечный перекод лёг поверх копии
    whole, told = warmer.done, warmer.line()
    assert whole, "перекод лёг поверх тяжёлой копии, а готово не наступило"
    assert "интернет больше не нужен" in told


def test_the_chain_outlives_a_film_whose_heavy_pieces_stay_copies(tmp_path: Path) -> None:
    """Тяжёлые места лежат копией и перекодировать их нечем: строка честная, цепочка живая.

    Это два конца одной правки, и резать их порознь нельзя. Строгое «готово» без
    цепочки давало мёртвую очередь: текущая серия «готовой» не становится никогда, и
    следующая не берётся в работу. Цепочка без строгого «готово» давала ложную строку
    про досмотр без сети.
    """
    grid = _grid()
    mine = _vault(tmp_path, key="эта")
    for slot in range(grid.count):
        _lay(mine, slot, size=4096)
    _lay(mine, 1, size=4097)
    said: list[str] = []
    nxt = Warmer(source="s2", audio=0, grid=grid, vault=_vault(tmp_path, key="следующая"))
    warmer = Warmer(
        source="s1",
        audio=0,
        grid=grid,
        vault=mine,
        cap=4096,
        follow=lambda: nxt,
        slack=999.0,
        log=said.append,
    )
    warmer._work()

    assert not warmer.done, "фильм с тяжёлой копией объявлен прогретым целиком"
    assert all("интернет больше не нужен" not in line for line in said), said
    assert any("потолка приёмника" in line for line in said), "нет честной причины"
    assert warmer.after is nxt, "цепочка встала там, где работа прогрева кончилась"
    warmer.stop()
    assert nxt.stopped, "снятие показа обязано снимать и прогрев следующей серии"


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


# --- TC-468: прикидка веса захода и бюджет по ходу захода ----------------------
# «Каждый кусок равен потолку приёмника» ошибалось в обе стороны на одном и том же
# корпусе из 84 карт опорных кадров (scripts/warmbudget.py): лёгкое кино просило 11.6
# ГБ при факте 8.6 и вытесняло соседей зря, тяжёлое - 9.9 ГБ при факте 21.3, и бюджет
# проверялся на вдвое меньшем числе, чем потом легло. А проверялся он раз на заход,
# хотя заход - это весь остаток фильма.


def test_the_forecast_weighs_pieces_by_the_keyframe_map(tmp_path: Path) -> None:
    """Прикидка веса захода взвешивает каждый кусок по карте опорных кадров - по той же,
    по которой показ строит сетку и профиль тяжести, - а не «кусок равен потолку»."""
    from torrcast.stream import MAX_SEGMENT_BYTES

    keys = [float(k * 2) for k in range(31)]

    def _warmer_on(sizes: list[int], key: str) -> Warmer:
        grid = Grid.on_keyframes(keys, 60.0, 10.0, sizes=sizes, ceiling_mbit=9.0)
        assert grid.weigh is not None, "сетка с картой не несёт предсказателя веса"
        return Warmer(source="нет", audio=0, grid=grid, vault=_vault(tmp_path, key=key))

    def _by_map(warmer: Warmer) -> float:
        grid = warmer.grid
        assert grid.weigh is not None
        return sum(grid.weigh(grid.start(s), grid.end(s)) for s in range(grid.count))

    light = _warmer_on([k * 1_000_000 for k in range(31)], "л")  # копия 4 Мбит/с
    assert light._forecast(0, light.grid.count - 1) == pytest.approx(_by_map(light))
    assert _by_map(light) < light.grid.count * MAX_SEGMENT_BYTES / 2, (
        "лёгкая копия по-прежнему просится по потолку - соседей вытесняет зря"
    )

    heavy = _warmer_on([k * 6_000_000 for k in range(31)], "т")  # копия 24 Мбит/с
    assert heavy._forecast(0, heavy.grid.count - 1) == pytest.approx(_by_map(heavy))
    assert _by_map(heavy) > heavy.grid.count * MAX_SEGMENT_BYTES, (
        "тяжёлая копия по-прежнему недоспросила - бюджет проверен на меньшем числе"
    )


def test_the_forecast_falls_back_to_the_ceiling_without_a_map(tmp_path: Path) -> None:
    """Карты нет - вес куска неизвестен, и прикидка остаётся прежней: по потолку."""
    from torrcast.stream import MAX_SEGMENT_BYTES

    grid = _grid()
    assert grid.weigh is None, "ровная сетка не должна нести предсказателя веса"
    warmer = Warmer(source="нет", audio=0, grid=grid, vault=_vault(tmp_path))
    assert warmer._forecast(0, grid.count - 1) == pytest.approx(grid.count * MAX_SEGMENT_BYTES)

    bare = Grid.on_keyframes([float(k * 2) for k in range(31)], 60.0, 10.0)
    assert bare.weigh is None, "карта без смещений не должна давать предсказателя"


#: Вес куска, который кладёт заглушка: тяжелее потолочной прикидки ровной сетки, чтобы
#: факт укладки догонял бюджет по ходу захода, а не на входе в него.
_PIECE = 20_000_000


class _LayingPacker:
    """Упаковка-заглушка: каждый ``publish`` кладёт очередной кусок и двигает край."""

    def __init__(self, out: Path, first: int, last: int) -> None:
        self.out = out
        self.edge = first - 1
        self.last = last
        self.proc = _FakeProc()

    @classmethod
    def start(
        cls, command: list[str], out: Path, run: Path, first: int, last: int = -1
    ) -> _LayingPacker:
        return cls(out, first, last)

    def publish(self) -> None:
        if self.edge < self.last:
            self.edge += 1
            (self.out / segment_name(self.edge)).write_bytes(b"x" * _PIECE)

    def poll(self) -> int | None:
        return None

    def stop(self, keep_files: bool = True, reason: str = "") -> None:
        return None


def test_the_budget_is_rechecked_as_the_run_lays_pieces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Бюджет перепроверяется по мере укладки, а не раз на входе в заход.

    Заход - это весь остаток фильма, и за него вес каталога вырастает в разы: на входе
    место под заход было (20 + 5x16 = 100 МБ из 105), а после третьего куска прогрев
    обязан встать с честной причиной, а не доложить остаток сверх бюджета.
    """
    from torrcast import stream

    monkeypatch.setattr(stream, "Packer", _LayingPacker)
    monkeypatch.setattr(stream, "pack_start", lambda url, at, timeout=0.0: at)
    grid = _grid()
    said: list[str] = []
    warmer = Warmer(
        source="нет",
        audio=0,
        grid=grid,
        vault=_vault(tmp_path, key="тесный", budget=105_000_000),
        slack=1e6,
        log=said.append,
    )
    warmer._run(0, grid.count - 1)

    assert warmer.trouble.startswith("бюджет"), f"прогрев не встал: {warmer.trouble!r}"
    assert any("прогрев встал" in line for line in said), "остановка прошла молча"
    laid = len(list(warmer.vault.dir.glob("v*.ts")))
    assert 0 < laid < grid.count, f"уложено {laid} из {grid.count} - не похоже на стоп по ходу"

    roomy = Warmer(
        source="нет",
        audio=0,
        grid=grid,
        vault=_vault(tmp_path, key="широкий", budget=1 << 30),
        slack=1e6,
    )
    roomy._run(0, grid.count - 1)
    assert not roomy.trouble and len(list(roomy.vault.dir.glob("v*.ts"))) == grid.count, (
        "здоровый заход остановлен перепроверкой"
    )


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


def test_warming_does_not_even_start_a_run_while_the_recoder_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Уступка начинается раньше первого :meth:`Warmer._throttle`, а не после него.

    Между «пора греть» и первой заморозкой прогрев успевает поднять пробный прогон
    (:meth:`Warmer._run`) - ещё один ffmpeg и ещё один запрос в ту же раздачу. В разборе
    живого показа он встал ровно внутрь чужого захода на 15-й секунде, а сам прогрев
    замер через миллисекунду после старта: весь процессор, который прогрев в ту минуту
    отобрал у показа, был процессором пробного прогона.
    """
    started: list[tuple[int, int]] = []

    def _fake_run(self: Warmer, first: int, last: int, spot: bool = False) -> None:
        started.append((first, last))
        self.stopped = True

    monkeypatch.setattr(Warmer, "_run", _fake_run)
    warmer = _warmer(tmp_path)
    warmer.slack = GUARD_HIGH + 100.0  # запас отличный: ждать картинки нечего
    warmer.rival = _Rival(working=True)
    warmer.start()
    time.sleep(1.5)
    assert started == [], "прогрев поднял прогон посреди чужого захода"

    warmer.rival.working = False
    deadline = time.monotonic() + 10.0
    while not started and time.monotonic() < deadline:
        time.sleep(0.1)
    warmer.stop()
    assert started == [(0, _grid().count - 1)], "заход кончился, а прогрев так и не тронулся"


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


# --- TC-124: прогрев обязан заходить туда же, куда заходит живая упаковка -------
# Резы захода ffmpeg отмеряет от ПЕРВОГО ПАКЕТА прогона, а список ``-segment_times``
# считается от того начала, которое ему назвали. Назвали задуманное сеткой, а встал он
# раньше - и весь заход разъезжается с сеткой на всю докатку. Проверяются, как и выше,
# выданные БАЙТЫ, а не аргументы ffmpeg.


def _offkey_grid() -> Grid:
    """Сетка, чьи границы заведомо не совпадают с опорными кадрами ролика.

    У ролика опорный кадр каждые 2 с (``-g 50`` при 25 к/с), поэтому границы, сдвинутые
    на секунду, гарантируют докатку: ``-ss`` уводит ffmpeg на опорный кадр раньше границы -
    ровно то, что происходит на настоящем релизе.
    """
    return Grid(tuple(float(k * 10 + (1 if k else 0)) for k in range(6)), float(CLIP_SECONDS), True)


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _pack_to_the_end(command: list[str], out: Path, first: int, last: int) -> None:
    """Один прогон упаковки до конца участка - эталон живого показа."""
    packer = Packer.start(command, out, out / "run", first, last=last)
    deadline = time.monotonic() + 180
    while packer.poll() is None and time.monotonic() < deadline:
        packer.publish()
        time.sleep(0.2)
    packer.publish()
    packer.stop(keep_files=True, reason="эталон снят")


def test_warming_enters_the_run_exactly_where_the_live_packing_enters_it(
    clip: str, tmp_path: Path
) -> None:
    """Прогретый кусок побайтово равен живому НА ВСЁМ заходе, а не местами.

    Улика, ради которой тест написан: прогрев называл ffmpeg задуманное сеткой начало
    (``grid.start``), а живая упаковка - измеренное (:func:`torrcast.stream.pack_start`).
    ffmpeg вставал раньше, резы захода уезжали на всю докатку, и первый кусок прогрева
    начинался на 1.7 с раньше своей границы: PCR и метки видео шли НАЗАД на стыке с живым
    куском. Там, где в сдвинутом окне не оказывалось опорного кадра, рез вставал верно и
    кусок совпадал с живым - поэтому сравниваются все куски захода, а не один.
    """
    grid = _offkey_grid()
    first, last = 2, grid.count - 1
    at = pack_start(clip, grid.start(first))
    assert at < grid.start(first) - SPLIT_SLACK, (
        f"ролик не даёт докатки на границе {grid.start(first)} с - тесту нечего ловить"
    )

    live = tmp_path / "live"
    _pack_to_the_end(
        ffmpeg_pack_command(clip, 0, str(live / "run"), grid, first, at, readrate=0.0, until=last),
        live, first, last,
    )  # fmt: skip

    vault = _vault(tmp_path, key="прогрев")
    warmer = Warmer(source=clip, audio=0, grid=grid, vault=vault, rate=0.0, slack=1e6)
    warmer._run(first, last)

    for slot in range(first, grid.count):
        want = live / segment_name(slot)
        assert want.exists(), f"эталон {segment_name(slot)} не снялся - сравнивать не с чем"
        assert vault.path(slot).exists(), f"прогрев не выложил {segment_name(slot)}"
        assert _md5(vault.path(slot)) == _md5(want), (
            f"прогретый {segment_name(slot)} разошёлся с живым по байтам: "
            f"{vault.path(slot).stat().st_size} Б против {want.stat().st_size} Б"
        )


def test_the_recoding_run_of_the_warming_never_asks_the_pilot(
    clip: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """У перекодирующего захода ``-ss`` точен, и пробный прогон ему вреден.

    Измеренное начало увело бы такой заход на сегмент назад: докатки он не делает вовсе
    (:func:`torrcast.stream.ffmpeg_pack_command`). Пробный прогон тут подменён заведомо
    неверным ответом - если прогрев его спросит и послушает, кусок ляжет не на своё место.
    """
    from torrcast import stream
    from torrcast.recode import Encode

    asked: list[float] = []

    def _pilot(url: str, at: float, timeout: float = 0.0) -> float:
        asked.append(at)
        return at - 5.0

    monkeypatch.setattr(stream, "pack_start", _pilot)
    grid = _offkey_grid()
    slot = 2
    vault = _vault(tmp_path, key="точечно")
    warmer = Warmer(
        source=clip, audio=0, grid=grid, vault=vault, rate=0.0, slack=1e6,
        spots=(slot,), spot_encode=Encode(preset="ultrafast", mbit=1.0),
    )  # fmt: skip
    warmer._run(slot, slot, spot=True)

    assert not asked, "перекодирующий заход прогрева спросил пробный прогон"
    assert vault.path(slot).exists(), f"перекодирующий заход не выложил {segment_name(slot)}"


# --- TC-125: сторож границ прогретого ------------------------------------------
# Дефект укладки мимо сетки (выше, TC-124) прожил незамеченным не потому, что был хитрым,
# а потому, что уложенный кусок никто не сверял с сеткой: код верил намерению, а не
# результату. Тесты ниже проверяют не намерение и не аргументы ffmpeg, а НАЧАЛО уже
# лежащего файла - то самое место, где дефект был виден с самого начала.

#: Слот, на котором ставятся опыты сторожа: у :func:`_offkey_grid` его граница (21.0 с)
#: заведомо не совпадает с опорным кадром ролика, то есть докатка гарантирована.
_LAID = 2


@pytest.fixture(scope="module")
def warmed(clip: str, tmp_path_factory: pytest.TempPathFactory) -> tuple[Warmer, Vault]:
    """Настоящий прогретый кусок: тот же ffmpeg, та же сетка, та же укладка.

    Модульная и только на чтение: прогон ffmpeg стоит секунд, а нужен он сразу трём
    опытам. Менять хранилище через неё нельзя - опыты, которым надо кусок испортить или
    выбросить, копируют его себе.
    """
    room = tmp_path_factory.mktemp("прогретое")
    vault = Vault(root=room / "warm", key="здоровый", budget=1 << 30, floor=0)
    vault.open()
    warmer = Warmer(source=clip, audio=0, grid=_offkey_grid(), vault=vault, rate=0.0, slack=1e6)
    warmer._run(_LAID, _LAID)
    return warmer, vault


def test_the_guard_lets_a_healthy_piece_through(warmed: tuple[Warmer, Vault]) -> None:
    """Здоровый заход сторож не трогает: кусок на месте, браковок нет.

    Первый и главный вопрос к любому сторожу - не ловит ли он своих. Кусок тут уложен
    настоящим прогревом от измеренного начала, то есть ровно так, как он ложится в бою.
    """
    warmer, vault = warmed

    assert vault.path(_LAID).exists(), "сторож выбросил здоровый кусок"
    assert warmer.skews == {}, f"здоровый заход записан в промахи: {warmer.skews}"
    assert warmer.misgrid == -1, "здоровый заход оборван сторожем"


def test_the_muxer_preroll_is_not_a_skew(warmed: tuple[Warmer, Vault], tmp_path: Path) -> None:
    """Преролл муксера (-0.04 с) - не расхождение, а секунда назад - расхождение.

    Порог отмерян от кадра, а не от нуля: у mpegts-муксера PCR штатно идёт на сорок
    миллисекунд раньше первой метки видео, и у живой упаковки он ровно такой же. Сторож,
    считающий это браком, выбрасывал бы куски, которые показ и так отдаёт с диска.
    """
    _, source = warmed
    began = segment_start(source.path(_LAID))
    assert not math.isnan(began), "начало уложенного куска не прочиталось - мерить нечем"

    def _guard(edge: float) -> Warmer:
        """Прогрев, чья граница слота стоит на ``edge``; кусок - копия здорового."""
        bounds = list(_offkey_grid().bounds)
        bounds[_LAID] = edge
        vault = _vault(tmp_path, key=f"край{edge:.2f}")
        shutil.copyfile(source.path(_LAID), vault.path(_LAID))
        grid = Grid(tuple(bounds), float(CLIP_SECONDS), True)
        return Warmer(source="нет", audio=0, grid=grid, vault=vault, rate=0.0)

    preroll = _guard(began + 0.04)
    assert preroll._verify(_LAID), f"преролл {0.04:+.2f} с сторож посчитал расхождением"
    assert preroll.vault.path(_LAID).exists(), "здоровый кусок убран из хранилища"

    broken = _guard(began + 1.0)
    assert not broken._verify(_LAID), "кусок на секунду раньше границы сторож пропустил"
    assert not broken.vault.path(_LAID).exists(), "бракованный кусок остался в показе"


def test_the_guard_reads_the_head_of_the_file_and_never_the_source(
    warmed: tuple[Warmer, Vault], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Сверка не ходит в сеть и не поднимает процессов: ей хватает головы файла.

    Место вызова - путь укладки куска, рядом с показом. Запрос к раздаче стоил бы тут
    секунд на кусок и умирал бы ровно тогда, когда прогрев и нужен, - при обрыве связи.
    Поэтому и сеть, и ``ffprobe`` тут не «дорого», а запрещено.
    """
    import socket

    _, vault = warmed
    piece = vault.path(_LAID)
    whole = segment_start(piece)

    def _forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("сверка полезла наружу вместо чтения головы файла")

    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)

    head = tmp_path / "голова.ts"
    head.write_bytes(piece.read_bytes()[:HEAD_BYTES])
    assert segment_start(head) == whole, "ответ зависит от хвоста файла, а не от головы"
    assert piece.stat().st_size > 10 * HEAD_BYTES, "кусок мал - доказывать нечего"


def test_a_piece_laid_off_the_grid_never_reaches_the_show(
    clip: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Кусок, уложенный мимо своей границы, сторож ловит, выбрасывает и говорит об этом.

    Сдвиг тут не подрисован, а сделан настоящим ffmpeg: пробный прогон подменён на тот
    самый ответ, который давал дефект TC-124 (задуманное сеткой начало вместо
    измеренного), и заход честно уезжает на всю докатку. Первый промах - кусок вон и
    заново; второй на том же месте - место честно объявлено непрогретым.
    """
    from torrcast import stream

    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path / "след"))
    monkeypatch.setenv(trace.SID_ENV, "tc-125")
    monkeypatch.setattr(stream, "pack_start", lambda url, at, timeout=0.0: at)
    grid = _offkey_grid()
    vault = _vault(tmp_path, key="кривой")
    said: list[str] = []
    warmer = Warmer(
        source=clip, audio=0, grid=grid, vault=vault, rate=0.0, slack=1e6, log=said.append
    )

    warmer._run(_LAID, _LAID)
    assert not vault.path(_LAID).exists(), "кусок мимо сетки остался лежать в показе"
    assert warmer.skews == {_LAID: 1}, f"промах не посчитан: {warmer.skews}"
    assert warmer.misgrid == _LAID, "заход, промахнувшийся мимо сетки, не оборван"
    assert warmer.trouble == "", "первый промах обязан кончаться перекладкой, а не дырой"
    assert any("перекладываю" in line for line in said), f"о промахе не сказано: {said}"

    warmer._run(_LAID, _LAID)
    assert warmer.skews == {_LAID: SKEW_TRIES}, "второй промах не посчитан"
    assert not vault.path(_LAID).exists(), "кусок мимо сетки остался лежать в показе"
    assert warmer.trouble, "второй промах на том же месте прошёл молча"
    assert "непрогрет" in warmer.line(), f"дыра не названа дырой: {warmer.line()}"
    assert not warmer.done, "«прогрето целиком» при дыре в прогретом"

    trace.shutdown()
    rows = [
        json.loads(raw)
        for path in sorted((tmp_path / "след").glob("trace-*.jsonl"))
        for raw in path.read_text("utf-8").splitlines()
    ]
    skews = [rec for rec in rows if rec["event"] == "skew"]
    assert len(skews) == SKEW_TRIES, f"в следе не оба промаха: {skews}"
    assert skews[0]["slot"] == _LAID and skews[0]["hole"] is False
    assert skews[1]["hole"] is True, "дыра в следе не помечена дырой"
    assert skews[0]["off"] < -SKEW_MAX, f"сдвиг в следе меньше порога: {skews[0]}"


def test_the_guard_checks_every_laid_piece_not_just_the_first(clip: str, tmp_path: Path) -> None:
    """Сверяется КАЖДЫЙ уложенный кусок пачки, а не первый из неё.

    ``publish`` выкладывает пачкой - прогрев опрашивает его раз в полсекунды, и за это
    время на диск ложится несколько кусков сразу. Сторож, который смотрит на первый кусок
    пачки и бросает остальные, оставил бы в показе ровно то, ради чего он поставлен.
    Заход тут кривой по-настоящему: тот же ffmpeg, но заведённый от задуманного сеткой
    начала - ровно так вёл себя дефект TC-124.
    """
    grid = _offkey_grid()
    first, last = _LAID, grid.count - 1
    crooked = tmp_path / "кривой"
    _pack_to_the_end(
        ffmpeg_pack_command(clip, 0, str(crooked / "run"), grid, first, grid.start(first),
                            readrate=0.0, until=last),
        crooked, first, last,
    )  # fmt: skip
    laid = sorted(range(first, grid.count))
    for slot in laid:
        assert (crooked / segment_name(slot)).exists(), (
            f"кривой заход не дал {segment_name(slot)} - ловить нечего"
        )

    vault = _vault(tmp_path, key="пачка")
    for slot in laid:
        shutil.copyfile(crooked / segment_name(slot), vault.path(slot))
    warmer = Warmer(source="нет", audio=0, grid=grid, vault=vault, rate=0.0)

    warmer._inspect(first - 1, last)
    assert sorted(warmer.skews) == laid, f"сторож проверил не всю пачку: {warmer.skews}"
    assert vault.slots() == set(), f"мимо сетки, а в показе лежит: {sorted(vault.slots())}"
