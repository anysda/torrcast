"""Проверяет совместимость старого имени адаптера упаковки и ленту, в которой он мерит."""

import subprocess
from pathlib import Path

import pytest

from torrcast.adapters.stream_pack import Grid, ffmpeg_pack_command, pack_start

#: На столько секунд вперёд уезжают метки контейнера в фикстуре ниже. Число заведомо
#: больше сегмента: ошибка в ленту меньше сегмента дала бы всего лишь кривой рез, а
#: разбирается тут случай, когда весь список резов уходит в минус.
SHIFT = 600.0

#: Шаг сетки в этих проверках. Ролик из ``clip`` длиной в минуту даёт на нём семь
#: сегментов - достаточно, чтобы «один кусок» и «много кусков» различались очевидно.
STEP = 8.0

#: Опорные кадры в ``clip`` стоят каждые две секунды (``-g 50`` на 25 кадрах). Целимся
#: между ними: только так видно, в какую сторону уезжает посадка у конкретного демуксера.
BETWEEN_KEYS = 41.0


def test_old_module_name_is_adapter() -> None:
    import torrcast.adapters.stream_pack as adapter
    import torrcast.stream_pack as facade

    assert facade is adapter


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
    прогон - единственный механизм, и разложить куски под именами мест, в которых поток
    не начинался.
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
def test_a_run_told_it_stands_past_its_boundary_still_gets_cut_into_pieces(
    clip: str, tmp_path: Path
) -> None:
    """🔴 TC-629. На вранье о месте захода упаковка отдаёт куски, а не один ком.

    Это и есть тот самый 240-мегабайтный кусок из живой приёмки: список резов уходил в
    минус целиком, сегментный муксер не резал ничего и писал один кусок до конца фильма.
    Проверяется настоящим ffmpeg, потому что «не режет» - свойство муксера, а не сборки.
    """
    grid = Grid.uniform(60.0, STEP)
    run = tmp_path / "run"
    run.mkdir()
    # Замер соврал так, как врал он на сдвинутом контейнере: место захода названо позже
    # своей границы (16.0) больше чем на сегмент.
    command = ffmpeg_pack_command(clip, 0, str(run), grid, 2, 16.0 + SHIFT, readrate=0)
    subprocess.run(command, check=True, capture_output=True, timeout=300)

    sizes = [piece.stat().st_size for piece in run.glob("v*.ts")]
    assert len(sizes) > 1, "муксер не разрезал ничего: весь хвост фильма лёг одним куском"
    assert max(sizes) * 2 < sum(sizes), (
        f"самый тяжёлый кусок {max(sizes)} из {sum(sizes)} - это ком, а не сегмент сетки"
    )
