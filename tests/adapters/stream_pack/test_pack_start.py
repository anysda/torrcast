"""Проверяет, откуда берётся место захода: карте верят сразу, прогон - для недоверенных."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from torrcast.adapters.pack_memory import _MAP_LIED
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.map_lied import map_lied
from torrcast.adapters.stream_pack.mapped_start import mapped_start
from torrcast.adapters.stream_pack.pack_start import pack_start
from torrcast.domain.film_keys import FilmKeys

#: На столько секунд вперёд уезжают метки контейнера в фикстуре ниже. Число заведомо
#: больше сегмента: ошибка в ленту меньше сегмента дала бы всего лишь кривой рез, а
#: разбирается тут случай, когда весь список резов уходит в минус.
SHIFT = 600.0

#: Опорные кадры в ``clip`` стоят каждые две секунды (``-g 50`` на 25 кадрах). Целимся
#: между ними: только так видно, в какую сторону уезжает посадка у конкретного демуксера.
BETWEEN_KEYS = 41.0

KEYS = FilmKeys(60.0, [round(k * 2.0, 3) for k in range(31)], [k * 4096 for k in range(31)], "mkv")


@pytest.fixture(autouse=True)
def _own_memory() -> Iterator[None]:
    """Снятое доверие помнится на весь процесс; каждой пробе оно достаётся нетронутым."""
    _MAP_LIED.clear()
    yield
    _MAP_LIED.clear()


@pytest.fixture
def clip_shifted(clip: str, tmp_path: Path) -> str:
    """Тот же ролик в mpegts, чьи метки начинаются не с нуля.

    Так лежат .ts и .m2ts (BluRay-ремуксы): начало у них любое. Карты опорных кадров для
    такого контейнера взять неоткуда, поэтому место захода там считает пробный прогон - и
    он там не запасной путь, а единственный.
    """
    path = tmp_path / "shifted.ts"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", clip,
         "-c", "copy", "-output_ts_offset", f"{SHIFT:g}",
         "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


def test_the_start_of_the_film_needs_no_measurement() -> None:
    """Заход от нуля стоит на нуле: мерить тут нечего."""
    assert pack_start("http://торрент/поток", 0.0) == 0.0
    assert pack_start("http://торрент/поток", -3.0) == 0.0


def test_the_map_is_believed_from_the_very_first_entry_without_any_pilot() -> None:
    """🔴 TC-133. Пробного прогона нет ни на одном заходе, включая ПЕРВЫЙ по файлу.

    Прежде первый заход по файлу платил прогон, сверяя им карту: 0.029 с на файле в
    tmpfs, 0.042 с по http на петле - против 1.6-10.9 мкс на тот же ответ по карте.
    Сверка не отменена, а переехала с предсказания на ФАКТ нарезки: резы захода муксер
    отмеряет от первого пакета, поэтому промах карты уводит их все и виден расхождением
    нарезанного с манифестом (:func:`torrcast.usecases.feed_pack.feed_astray._astray`).
    """
    url = "http://торрент/поток?link=честная"
    asked: list[float] = []

    def pilot(source: str, at: float, timeout: float = 0.0) -> float:
        asked.append(at)
        return 40.0

    first, second = 42.0, 50.0
    assert pack_start(url, first, keys=KEYS, pilot=pilot) == pytest.approx(
        mapped_start(KEYS, first)
    )
    assert pack_start(url, second, keys=KEYS, pilot=pilot) == pytest.approx(
        mapped_start(KEYS, second)
    )
    assert asked == [], f"прогонов подняли {len(asked)}, а место захода карта даёт даром"


def test_a_file_whose_map_lied_goes_back_to_the_pilot_for_good() -> None:
    """Доверие снято - место захода снова меряет прогон, и меряет на каждом заходе.

    Снимает доверие лента показа, увидев нарезку не на своём месте; здесь проверяется
    вторая половина того же правила - что снятое доверие и правда уводит заход на прогон.
    Обе половины лежат в одном модуле (:mod:`torrcast.adapters.stream_pack.map_lied`)
    именно поэтому: порознь они бессмысленны.
    """
    url = "http://торрент/поток?link=врущая"

    def pilot(source: str, at: float, timeout: float = 0.0) -> float:
        return at - 0.7

    lying = KEYS._replace(at=[second + 0.7 for second in KEYS.at])
    assert pack_start(url, 42.0, keys=lying, pilot=pilot) == pytest.approx(
        mapped_start(lying, 42.0)
    ), "доверие не снято - заход идёт по карте, какой бы она ни была"
    map_lied(url)
    assert pack_start(url, 42.0, keys=lying, pilot=pilot) == pytest.approx(41.3)
    assert pack_start(url, 50.0, keys=lying, pilot=pilot) == pytest.approx(49.3)


def test_the_verdict_about_one_file_says_nothing_about_its_neighbour() -> None:
    """Доверие снимается ПОФАЙЛОВО: соседняя раздача заходит по карте и дальше даром.

    Ключ тут - URL потока, тот же, что у кэша карты. Промахнуться им значило бы вернуть
    пробный прогон на все файлы разом, стоило соврать карте одного.
    """
    lied = "http://торрент/поток?link=врущая"
    neighbour = "http://торрент/поток?link=соседняя"
    asked: list[str] = []

    def pilot(source: str, at: float, timeout: float = 0.0) -> float:
        asked.append(source)
        return 40.0

    map_lied(lied)
    pack_start(lied, 42.0, keys=KEYS, pilot=pilot)
    pack_start(neighbour, 42.0, keys=KEYS, pilot=pilot)
    assert asked == [lied], f"прогон подняли для {asked}, а врала карта одного файла"


@pytest.mark.ffmpeg
def test_where_the_run_stands_is_measured_in_film_time_not_in_container_time(
    clip_shifted: str,
) -> None:
    """🔴 TC-629. Замер захода обязан лежать в той же ленте, что и границы сетки.

    ``-ss`` отсчитывается от начала контейнера, а ``-copyts`` печатает метку вместе с этим
    началом. Пока контейнер начинается с нуля (mkv, mp4), разницы не видно; на сдвинутом
    замер уезжал вперёд на весь сдвиг - и дальше это число ехало в резы как «где встал
    прогон», превращая весь список в отрицательный.
    """
    stood = pack_start(clip_shifted, 16.0)
    assert stood < SHIFT / 2, f"заход измерен как {stood}: это лента контейнера, не фильма"
    assert stood == pytest.approx(16.0, abs=1.0)


@pytest.mark.ffmpeg
def test_a_demuxer_landing_forward_keeps_its_measured_place_instead_of_the_boundary(
    clip: str, clip_shifted: str
) -> None:
    """🔴 TC-629. Уезд ВПЕРЁД - правда о потоке, и стирать его вместе с чужой лентой нельзя.

    Два демуксера ведут себя противоположно, и обе посадки одинаково настоящие: mkv берёт
    опорный кадр строго РАНЬШЕ запрошенного (докатка), mpegts - СЛЕДУЮЩИЙ за ним, и докатки
    у него не бывает вовсе (``SEEK_SHIFT``, замер репы: +1 на 89 границах). Зажать замер
    границей значило бы подменить измеренное место предполагаемым ровно там, где пробный
    прогон - единственный механизм.
    """
    forward = pack_start(clip_shifted, BETWEEN_KEYS)
    backward = pack_start(clip, BETWEEN_KEYS)
    assert forward > BETWEEN_KEYS, (
        f"посадка mpegts зажата до {forward}: измеренное место подменено границей"
    )
    assert backward < BETWEEN_KEYS, f"докатка mkv потеряна: {backward}"
    assert forward == pytest.approx(42.0, abs=0.5)
    assert backward == pytest.approx(40.0, abs=0.5)


@pytest.mark.ffmpeg
def test_a_grid_still_gets_cut_into_pieces_when_the_run_lies_about_its_place(
    clip: str, tmp_path: Path
) -> None:
    """🔴 TC-629. На вранье о месте захода упаковка отдаёт куски, а не один ком.

    Это и есть тот самый 240-мегабайтный кусок из живой приёмки: список резов уходил в
    минус целиком, сегментный муксер не резал ничего и писал один кусок до конца фильма.
    """
    from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command

    grid = Grid.uniform(60.0, 8.0)
    run = tmp_path / "run"
    run.mkdir()
    command = ffmpeg_pack_command(clip, 0, str(run), grid, 2, 16.0 + SHIFT, readrate=0)
    subprocess.run(command, check=True, capture_output=True, timeout=300)

    sizes = [piece.stat().st_size for piece in run.glob("v*.ts")]
    assert len(sizes) > 1, "муксер не разрезал ничего: весь хвост фильма лёг одним куском"
    assert max(sizes) * 2 < sum(sizes), (
        f"самый тяжёлый кусок {max(sizes)} из {sum(sizes)} - это ком, а не сегмент сетки"
    )
