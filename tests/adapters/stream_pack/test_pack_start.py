"""Проверяет, откуда берётся место захода: карта верится только после сверки с прогоном."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.conftest import module_of
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.mapped_start import mapped_start
from torrcast.adapters.stream_pack.pack_start import pack_start
from torrcast.domain.film_keys import FilmKeys

module = module_of("torrcast.adapters.stream_pack.pack_start")

#: На столько секунд вперёд уезжают метки контейнера в фикстуре ниже. Число заведомо
#: больше сегмента: ошибка в ленту меньше сегмента дала бы всего лишь кривой рез, а
#: разбирается тут случай, когда весь список резов уходит в минус.
SHIFT = 600.0

#: Опорные кадры в ``clip`` стоят каждые две секунды (``-g 50`` на 25 кадрах). Целимся
#: между ними: только так видно, в какую сторону уезжает посадка у конкретного демуксера.
BETWEEN_KEYS = 41.0

KEYS = FilmKeys(60.0, [round(k * 2.0, 3) for k in range(31)], [k * 4096 for k in range(31)], "mkv")


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


def test_the_map_is_believed_only_after_the_pilot_has_confirmed_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Пробный прогон - один на файл, а не один на заход, и он именно сверка.

    Дёшево поверить карте сразу проект уже дважды не смог: резы захода муксер отмеряет от
    первого пакета, и заход, вставший не туда, кладёт мимо сетки весь участок.
    """
    url = "http://торрент/поток?link=честная"
    trusted: dict[str, bool] = {}
    asked: list[float] = []
    monkeypatch.setattr(module, "_SEEK_OK", trusted)

    def pilot(url: str, at: float, timeout: float = 0.0) -> float:
        asked.append(at)
        return 40.0

    monkeypatch.setattr(module, "_pilot_start", pilot)

    first, second = 42.0, 50.0
    assert pack_start(url, first, keys=KEYS) == pytest.approx(mapped_start(KEYS, first))
    assert pack_start(url, second, keys=KEYS) == pytest.approx(mapped_start(KEYS, second))
    assert asked == [first], f"пробных прогонов {len(asked)}, а карта сверяется один раз"
    assert trusted[url] is True


def test_a_lying_map_is_caught_and_never_believed_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """Карта разошлась с фактом - работает прежний прогон, и место захода верное.

    Разошлось больше полукадра - файл помечен недоверенным навсегда.
    """
    url = "http://торрент/поток?link=врущая"
    trusted: dict[str, bool] = {}
    monkeypatch.setattr(module, "_SEEK_OK", trusted)
    monkeypatch.setattr(module, "_pilot_start", lambda u, at, t=0.0: at - 0.7)

    lying = KEYS._replace(at=[second + 0.7 for second in KEYS.at])
    assert pack_start(url, 42.0, keys=lying) == pytest.approx(41.3)
    assert trusted[url] is False, "враньё карты запоминается: второй раз не спрашиваем"
    assert pack_start(url, 50.0, keys=lying) == pytest.approx(49.3)


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
