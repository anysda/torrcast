"""Нарезка разъехалась с манифестом: снять доверие карте и зайти заново.

Мера про доказательство, а не про уверенность. Место захода упаковка берёт из карты
опорных кадров даром (TC-133), а расплатой за это идёт сверка уже по ФАКТУ: резы
сегментный муксер отмеряет от первого пакета прогона, поэтому промах карты уезжает в
нарезку целиком и виден числом.

🔴 Предъявлять этот счёт можно только там, где карта в заходе участвовала. У головы файла
её не спрашивают вовсе, и стенд обязан заходить оттуда же, откуда заходит продукт: прежде
все пробы тут стояли на слоте 0, то есть ровно на том заходе, которого карта не давала, - и
доказывали лечение там, где лечить нечего.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import feed, here, lay, packer, tract
from torrcast.domain.hls_settings import PACK_LIST
from torrcast.usecases.feed_pack.feed_sweep import _sweep

if TYPE_CHECKING:
    from pathlib import Path

#: На столько секунд карта увела заход: разъезд заведомо больше допуска нарезки
#: (``SPLIT_SLACK`` - полкадра), но меньше сегмента - то есть именно кривой заход, а не
#: другое место фильма.
LIED = 4.0

#: Слот, с которого идут пробы: заход НЕ с головы файла, то есть тот единственный случай,
#: в котором место захода и правда берётся из карты.
FROM = 2

#: Сдвиг головы файла, замеренный на живом ffmpeg (``test_the_map_keeps_quiet_where_the
#: _rule_does_not_hold``): у начала файла dts ниже нуля не пускается, и метки уезжают на
#: кадр-два вперёд. Больше допуска нарезки в четыре раза, а карта тут ни при чём.
HEAD_SHIFT = 0.08


def _cut(run: Path, rows: list[tuple[int, float]]) -> None:
    """Написать прогону его же список резов - тот, что ведёт сегментный муксер.

    Первая строка в нём всегда начало прогона, и сверка её пропускает: там ffmpeg пишет
    ноль независимо от того, куда прогон встал.
    """
    (run / PACK_LIST).write_text(
        "".join(f"v{slot}.ts,{began:.6f},{began + 10.0:.6f}\n" for slot, began in rows),
        encoding="utf-8",
    )


def _lied() -> tuple[set[str], dict[str, object]]:
    """Память о вранье карты - своя на пробу, а не общая на процесс.

    Карта отвечает тут тем же правилом, что и боевая
    (:func:`torrcast.adapters.stream_pack.map_entry.map_entry`): молчит у головы файла и
    молчит по файлу, которому доверие уже снято.
    """
    marked: set[str] = set()
    return marked, {
        "map_trusted": lambda url: url not in marked,
        "map_lied": marked.add,
        "map_entry": lambda url, at: at if at > 0 and url not in marked else math.nan,
    }


def test_a_cut_that_drifted_from_the_manifest_enters_again_without_the_map(
    tmp_path: Path,
) -> None:
    """🔴 TC-133. Карта соврала - показ узнаёт это НАРЕЗКОЙ и заходит заново.

    Ради этой сверки место захода и разрешено брать из карты даром: дешёвая уверенность
    уже дважды клала куски мимо сетки. Замер репы на живом ffmpeg (ровная сетка 10 с,
    600 с плёнки): здоровый заход даёт расхождение 0.000 с на mkv и 0.006 с на mp4, а
    заход, которому соврали на 4.0 с, - ровно 4.000 с.
    """
    marked, memory = _lied()
    tract(now=100.0, spawn=here, **memory)
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=FROM, out=show.out)
    for slot in range(FROM, FROM + 3):
        lay(show.packer.run, slot)
    _cut(show.packer.run, [(FROM, 20.0), (FROM + 1, 30.0 + LIED), (FROM + 2, 40.0 + LIED)])

    _sweep(show, asked.append)

    assert marked == {show.source}, "доверие карте не снято: заход повторит ту же ошибку"
    assert asked == [FROM], f"перезаход просили с {asked}, а кривым лёг весь заход с {FROM}"
    assert list(show.out.glob("v*.ts")) == [], (
        "куски кривого захода остались: запрос сегмента отдал бы их файлом, "
        "не спросив упаковку вовсе"
    )


def test_an_entry_the_map_never_gave_is_not_cured_by_disbelieving_the_map(
    tmp_path: Path,
) -> None:
    """🔴 TC-1309. Заход с головы файла карту не спрашивал - и разъездом не лечится.

    Лечение тут ровно одно: снять доверие карте и зайти заново. Заходу, которому карта
    места не давала, оно не даёт ничего - перезаход считает место тем же правилом и встаёт
    туда же. Замер стенда за 8 суток: все 5 тревог пришлись на слот 0 с расхождениями
    0.052-0.145 с, и после каждой в следе стоит «заход упаковки, слот 0, встали 0.0» - то
    самое место, откуда ушли. На 55 заходов со слотом больше нуля тревог не было ни одной.
    Платил за лечение здорового зритель: свои же куски снесены и прогон поднят заново.
    """
    marked, memory = _lied()
    tract(now=100.0, spawn=here, **memory)
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, out=show.out)
    for slot in range(3):
        lay(show.packer.run, slot)
    _cut(show.packer.run, [(0, 0.0), (1, 10.0 + HEAD_SHIFT), (2, 20.0 + HEAD_SHIFT)])

    _sweep(show, asked.append)

    assert show.packer.drift(show.grid) > 0.0, "стенд собрал не тот случай: разъезда нет вовсе"
    assert marked == set(), "доверие снято с карты, которая этого захода не давала"
    assert asked == [], f"перезаход просили с {asked}, а лечить тут нечего"
    assert (show.out / "v1.ts").exists(), "зрителю снесли кусок ради лечения здорового"


def test_a_pass_that_landed_where_the_manifest_promised_is_left_alone(
    tmp_path: Path,
) -> None:
    """Здоровый заход не трогают: сверка отделяет промах карты от обычного шума муксера."""
    marked, memory = _lied()
    tract(now=100.0, spawn=here, **memory)
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=FROM, out=show.out)
    for slot in range(FROM, FROM + 3):
        lay(show.packer.run, slot)
    _cut(show.packer.run, [(FROM, 20.0), (FROM + 1, 30.0), (FROM + 2, 40.006)])

    _sweep(show, asked.append)

    assert marked == set() and asked == []
    assert (show.out / f"v{FROM + 1}.ts").exists(), "у здорового захода снесли выложенное"


def test_a_run_too_short_to_measure_is_not_a_run_that_agreed(tmp_path: Path) -> None:
    """🔴 Пустота «мерить нечем» не должна выглядеть как «сошлось».

    Расхождение считается по списку резов, а первую его строку сверка пропускает: в ней
    ffmpeg пишет начало прогона нулём. На списке короче двух строк ответ - 0.0, то есть
    ровно тот же, что у безупречной нарезки. Поэтому спрашивают его только там, где счёт
    заведомо есть: край прогона ушёл дальше первого слота. Здесь заход встал на 4.0 с
    мимо, но закрыть успел один кусок - и приговора быть не может.
    """
    marked, memory = _lied()
    tract(now=100.0, spawn=here, **memory)
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=FROM, out=show.out)
    lay(show.packer.run, FROM)
    lay(show.packer.run, FROM + 1)
    _cut(show.packer.run, [(FROM, 20.0 + LIED)])

    _sweep(show, asked.append)

    assert show.packer.edge == show.packer.first, "стенд собрал не тот случай"
    assert marked == set() and asked == []


def test_the_map_of_one_file_is_condemned_once_and_not_every_two_seconds(
    tmp_path: Path,
) -> None:
    """Второй такой же разъезд - больной источник, а не врущая карта: лечить его не тут.

    Часы показа зовут уборку каждые две секунды, и без этой границы кривой заход
    перезапускался бы без конца, ни разу не доиграв до картинки.
    """
    _marked, memory = _lied()
    tract(now=100.0, spawn=here, **memory)
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=FROM, out=show.out)
    for slot in range(FROM, FROM + 3):
        lay(show.packer.run, slot)
    _cut(show.packer.run, [(FROM, 20.0), (FROM + 1, 30.0 + LIED), (FROM + 2, 40.0 + LIED)])

    _sweep(show, asked.append)
    for slot in range(FROM, FROM + 3):
        lay(show.packer.run, slot)
    _sweep(show, asked.append)

    assert asked == [FROM], f"перезаходов вышло {len(asked)}, а решение это одно на файл"
