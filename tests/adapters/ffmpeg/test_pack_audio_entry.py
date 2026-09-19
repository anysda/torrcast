"""Проверяет настоящим ffmpeg, что звук первого куска показа приезжает вместе с картинкой."""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import pytest

from tests.conftest import CLIP_KEY_SECONDS
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.grid import Grid

#: Ровная сетка по 10 с на шестидесятисекундном ролике - та же, что кладёт показ.
GRID = Grid(tuple(float(k * 10) for k in range(7)), 60.0)

#: Слот, с которого заходит прогон, и куда просят зайти: между опорными кадрами, как
#: просит возобновление показа с запомненного места. Расхождение звука с картинкой видно
#: ТОЛЬКО здесь: при заходе ровно на опорный кадр обе дорожки начинаются в одной точке.
SLOT = 4
BETWEEN_KEYS = 41.0

#: Где прогон встаёт на самом деле - опорный кадр ролика перед местом захода. Считается,
#: а не пишется числом: опорные кадры стоят каждые :data:`CLIP_KEY_SECONDS` = 2.0854 с
#: (50 кадров на 24000/1001), и ровного числа среди них нет вовсе. Ровно это место в
#: живом показе меряет пилотный заход и приносит упаковке доводом ``at``.
LANDED = CLIP_KEY_SECONDS * math.floor(BETWEEN_KEYS / CLIP_KEY_SECONDS)

#: Потолок расхождения звука с картинкой в первом куске, секунды.
#:
#: Взят между двумя своими масштабами, а не подогнан под дерево: он заведомо БОЛЬШЕ кадра
#: ролика (0.042 с) и набивки кодировщика AAC (0.021 с, :data:`AUDIO_PRIMING`), то есть
#: законных расхождений не ловит, и заведомо МЕНЬШЕ расстояния между опорными кадрами
#: (2.0854 с), то есть ловит любое расхождение на опорный кадр. Живой замер на стенде:
#: 0.004 с на картине с ac3 5.1 и 0.006 с на картине с aac 2.0.
SKEW_LIMIT = 0.1


class _Encode:
    """Перекод в договоре сборки: она спрашивает у него только аргументы кодера."""

    def args(self, grid: Grid, slot: int, until: int) -> list[str]:
        return ["-c:v", "libx264"]


def _first_packets(path: Path) -> dict[str, float]:
    """Метка первого пакета каждой дорожки куска."""
    found = subprocess.run(
        ["ffprobe", "-v", "error", "-of", "json", "-show_entries", "packet=codec_type,pts_time",
         "-read_intervals", "%+#40", str(path)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    first: dict[str, float] = {}
    for packet in json.loads(found.stdout).get("packets", []):
        kind = str(packet["codec_type"])
        first.setdefault(kind, float(packet["pts_time"]))
    return first


@pytest.fixture
def first_segment(clip: str, tmp_path: Path) -> Path:
    """Первый кусок прогона, зашедшего между опорными кадрами."""
    command = ffmpeg_pack_command(
        clip, 0, str(tmp_path), GRID, SLOT, LANDED, readrate=0.0, seek=BETWEEN_KEYS
    )
    subprocess.run(command, check=True, capture_output=True)
    return tmp_path / f"v{SLOT}.ts"


@pytest.mark.ffmpeg
def test_sound_of_the_first_chunk_starts_with_the_picture(first_segment: Path) -> None:
    """Звук и картинка первого куска начинаются в одной точке, а не через опорный кадр.

    🔴 Пока заход называл просимое место, а не место посадки, точный вход резал ЗВУК
    ровно по ``-ss``, а видео шло копией и обрезать его было нечем: оно приходит с
    опорного кадра перед названным местом. Зритель получал до 5.3 с картинки вовсе без
    звука на первом куске показа и слышал это как «со звуком что-то ужасное».
    """
    first = _first_packets(first_segment)
    assert "audio" in first, f"звука в первом куске нет вовсе: {first}"
    skew = first["audio"] - first["video"]
    assert abs(skew) <= SKEW_LIMIT, f"звук разъехался с картинкой на {skew:.3f} с"


@pytest.mark.ffmpeg
def test_the_chunk_carries_the_sound_of_its_whole_length(first_segment: Path) -> None:
    """Звук занимает весь кусок, а не его хвост: иначе начало показа молчит.

    Отдельная проба к предыдущей: совпасть по первому пакету и при этом нести звука
    вдвое меньше куска - ровно тот способ, которым дефект вернулся бы незамеченным.
    """
    spans = subprocess.run(
        ["ffprobe", "-v", "error", "-of", "json", "-show_entries", "stream=codec_type,duration",
         str(first_segment)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    found = {s["codec_type"]: float(s["duration"]) for s in json.loads(spans.stdout)["streams"]}
    assert found["audio"] >= found["video"] - SKEW_LIMIT, f"звук короче картинки: {found}"


def test_only_the_copying_run_takes_what_the_seek_gives() -> None:
    """Не обрезать по заходу просит копия, и только она: место захода у обеих одно.

    🔴 Копия обрезать картинку не может и берёт её с опорного кадра ПЕРЕД названным
    местом, а звук режется точно - отсюда показ без звука в первом куске. Перекодирующий
    заход режет обе дорожки сам, расходиться им нечем, и обрезать их он обязан: без
    обрезки его первый пакет уезжает назад за границу сетки, которую он держит, и сторож
    стыков поймал это на выложенной зрителю ленте откатом видео на 1.4181 с.
    """
    copied = ffmpeg_pack_command("u", 0, "/run", GRID, SLOT, LANDED, seek=BETWEEN_KEYS)
    recoded = ffmpeg_pack_command(
        "u", 0, "/run", GRID, SLOT, LANDED, encode=_Encode(), seek=BETWEEN_KEYS
    )
    assert "-noaccurate_seek" in copied
    assert "-noaccurate_seek" not in recoded
    assert copied[copied.index("-ss") + 1] == f"{BETWEEN_KEYS:.3f}"
    assert recoded[recoded.index("-ss") + 1] == f"{BETWEEN_KEYS:.3f}"
