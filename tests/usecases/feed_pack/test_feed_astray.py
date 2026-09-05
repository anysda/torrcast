"""Нарезка разъехалась с манифестом: снять доверие карте и зайти заново.

Мера про доказательство, а не про уверенность. Место захода упаковка берёт из карты
опорных кадров даром (TC-133), а расплатой за это идёт сверка уже по ФАКТУ: резы
сегментный муксер отмеряет от первого пакета прогона, поэтому промах карты уезжает в
нарезку целиком и виден числом.
"""

from __future__ import annotations

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
    """Память о вранье карты - своя на пробу, а не общая на процесс."""
    marked: set[str] = set()
    return marked, {"map_trusted": lambda url: url not in marked, "map_lied": marked.add}


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
    show.packer = packer(tmp_path, first=0, out=show.out)
    for slot in range(3):
        lay(show.packer.run, slot)
    _cut(show.packer.run, [(0, 0.0), (1, 10.0 + LIED), (2, 20.0 + LIED)])

    _sweep(show, asked.append)

    assert marked == {show.source}, "доверие карте не снято: заход повторит ту же ошибку"
    assert asked == [0], f"перезаход просили с {asked}, а кривым лёг весь заход с нуля"
    assert list(show.out.glob("v*.ts")) == [], (
        "куски кривого захода остались: запрос сегмента отдал бы их файлом, "
        "не спросив упаковку вовсе"
    )


def test_a_pass_that_landed_where_the_manifest_promised_is_left_alone(
    tmp_path: Path,
) -> None:
    """Здоровый заход не трогают: сверка отделяет промах карты от обычного шума муксера."""
    marked, memory = _lied()
    tract(now=100.0, spawn=here, **memory)
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, out=show.out)
    for slot in range(3):
        lay(show.packer.run, slot)
    _cut(show.packer.run, [(0, 0.0), (1, 10.0), (2, 20.006)])

    _sweep(show, asked.append)

    assert marked == set() and asked == []
    assert (show.out / "v1.ts").exists(), "у здорового захода снесли выложенное"


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
    show.packer = packer(tmp_path, first=0, out=show.out)
    lay(show.packer.run, 0)
    lay(show.packer.run, 1)
    _cut(show.packer.run, [(0, LIED)])

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
    show.packer = packer(tmp_path, first=0, out=show.out)
    for slot in range(3):
        lay(show.packer.run, slot)
    _cut(show.packer.run, [(0, 0.0), (1, 10.0 + LIED), (2, 20.0 + LIED)])

    _sweep(show, asked.append)
    for slot in range(3):
        lay(show.packer.run, slot)
    _sweep(show, asked.append)

    assert asked == [0], f"перезаходов вышло {len(asked)}, а решение это одно на файл"
