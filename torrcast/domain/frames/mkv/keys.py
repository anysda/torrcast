"""Карта опорных кадров mkv: разбор индекса ``Cues``.

Что это за индекс и чем он взят - в докстроке пакета
(:mod:`torrcast.domain.frames.mkv`); матрёшку EBML разбирают соседи
(:func:`~torrcast.domain.frames.mkv.walk.walk`, :class:`~torrcast.domain.frames.mkv.head.Head`),
здесь сам индекс.
"""

from __future__ import annotations

from torrcast.domain.frames.keymap.key_map import KeyMap
from torrcast.domain.frames.keymap.point import Point
from torrcast.domain.frames.mkv.cue import Cue
from torrcast.domain.frames.mkv.head import Head
from torrcast.domain.frames.mkv.ids import (
    CUE_CLUSTER_POSITION,
    CUE_POINT,
    CUE_RELATIVE_POSITION,
    CUE_TIME,
    CUE_TRACK,
    CUE_TRACK_POSITIONS,
    CUES,
    CUES_CHUNK,
    HEAD_BYTES,
)
from torrcast.domain.frames.mkv.key_frame import key_frame
from torrcast.domain.frames.mkv.probes import probes
from torrcast.domain.frames.mkv.uint import uint
from torrcast.domain.frames.mkv.walk import walk
from torrcast.domain.frames.range_reader import RangeReader as Reader
from torrcast.domain.infra_error import InfraError


def keys(reader: Reader, head: bytes) -> KeyMap:
    """Карта опорных кадров mkv. ``head`` — уже прочитанные :data:`HEAD_PEEK` байт.

    Заходов к рою минимум два (:data:`~torrcast.adapters.frames.keyframes.HEAD_PEEK` и
    :data:`CUES_CHUNK`), и оба — минимально возможного размера: у холодной раздачи цена
    карты — это не байты, а сколько раз мы заставили рой отдать новое место и сколько ждали
    перед следующим запросом. Сверх них - пробы честности индекса (:func:`_honest`):
    бывают индексы-вруны, и отличает их от честных только содержимое кадра.
    """
    facts = Head(head)
    if facts.cues_at is None or facts.duration <= 0:  # маленького куска не хватило
        facts = Head(reader.read(0, HEAD_BYTES))
    if facts.segment is None:
        raise InfraError("это не mkv: элемента Segment в голове файла нет")
    if facts.cues_at is None:
        raise InfraError("в файле нет индекса Cues - карту опорных кадров взять неоткуда")

    chunk = reader.read(facts.cues_at, CUES_CHUNK)
    found = walk(chunk, 0, min(32, len(chunk)))
    if not found:
        raise InfraError("по позиции из SeekHead читается не элемент EBML")
    ident, size, data = found[0]
    if ident != CUES:
        raise InfraError(f"по позиции из SeekHead лежит не Cues, а {ident:#x}")
    body = chunk[data : data + size]
    if len(body) < size:  # редкий толстый индекс - добираем остаток
        body += reader.read(facts.cues_at + len(chunk), size - len(body))

    cues = _cues(body, facts)
    if not cues:
        raise InfraError("Cues в файле есть, но точек в нём нет")
    _honest(cues, facts, reader)
    duration = facts.duration * facts.scale / 1e9
    points = tuple(sorted(cue.point for cue in cues))
    return KeyMap(duration, points, reader.taken, reader.requests, "mkv", facts.video)


def _honest(cues: list[Cue], facts: Head, reader: Reader) -> None:
    """Проверка, что точки Cues - опорные кадры, а не призраки; врущий индекс - ошибка.

    Замер TC-639: бывают файлы, чей муксер ставит точку Cues на каждый кластер и флаг
    опорности на каждый видеоблок, - карта из такого индекса на 89.7 % призраки (замер
    по полному перебору ffprobe: 7235 из 8065), и наружу она уехать не имеет права.
    Отличает призрака только содержимое кадра (:func:`key_frame`), причём именно того
    блока, который назвала точка (:attr:`~torrcast.domain.frames.mkv.cue.Cue.inside`):
    первый видеоблок кластера бывает чужим кадром, и тогда проверка судит не то, о чём
    говорит точка. Куда ставить пробы, решает :func:`~torrcast.domain.frames.mkv.probes.
    probes` - это соседняя пара, и она ловит вруна счётом, а не удачей.

    Не проверяем и верим, когда файл не назвал дорожку видео или когда кодек нам не по
    зубам: ``None`` у :func:`key_frame` - это «не разобрать», а не призрак.
    """
    if facts.video is None:
        return
    own = [cue for cue in cues if cue.point.track == facts.video]
    for cue in probes(own):
        at, offset, _ = cue.point
        if key_frame(reader, offset, facts.video, facts.codec, cue.inside) is False:
            raise InfraError(
                f"индекс Cues врёт: точка {at:.3f} ссылается не на опорный кадр - "
                "карта из него была бы призрачной"
            )


def _cues(body: bytes, facts: Head) -> list[Cue]:
    """Точки Cues: время в секундах, **абсолютное** смещение кластера и место блока в нём.

    ⚠️ ``CueClusterPosition`` в файле отсчитан от начала данных ``Segment``, а наружу
    смещение обязано быть абсолютным: по нему греется рой под перемотку, а рою всё
    равно, что там за матрёшка, — он знает только байты от начала файла.

    ``CueRelativePosition`` наружу не идёт вовсе и абсолютным не делается: это адрес
    внутри кластера, и нужен он одной лишь проверке честности (:func:`_honest`).
    """
    base = facts.segment or 0
    cues: list[Cue] = []
    for _, point_size, point in [e for e in walk(body, 0, len(body)) if e[0] == CUE_POINT]:
        at = None
        for sub, sub_size, sub_data in walk(body, point, point + point_size):
            if sub == CUE_TIME:
                at = uint(body, sub_data, sub_size) * facts.scale / 1e9
            elif sub == CUE_TRACK_POSITIONS and at is not None:
                offset, track, inside = 0, 0, 0
                for deep, deep_size, deep_data in walk(body, sub_data, sub_data + sub_size):
                    if deep == CUE_CLUSTER_POSITION and not offset:
                        offset = uint(body, deep_data, deep_size)
                    elif deep == CUE_TRACK:
                        track = uint(body, deep_data, deep_size)
                    elif deep == CUE_RELATIVE_POSITION:
                        inside = uint(body, deep_data, deep_size)
                cues.append(Cue(Point(at, base + offset, track), inside))
    return cues
