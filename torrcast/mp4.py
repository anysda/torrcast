"""Карта опорных кадров mp4: таблицы ``stss``/``stts``/``ctts`` из ``moov``.

Общее для всех контейнеров — в :mod:`torrcast.keymap`, там же и вход
(:func:`torrcast.keymap.keyframes`). Здесь только боксы ISO BMFF.

Индекс mp4 устроен не как ``Cues`` mkv: одной таблицы «время → байт» в файле нет, она
собирается из пяти.

===========  =================================================================
таблица      что даёт
===========  =================================================================
``stss``     номера **опорных** сэмплов (кадров); нет её вовсе — опорный каждый
``stts``     длительность сэмпла (сжато: «столько-то подряд по столько-то»)
``ctts``     сдвиг вывода: ``pts = dts + ctts``, из-за него B-кадры и нужны
``stsc``     сколько сэмплов в чанке (тоже сжато)
``stco``     смещение чанка в файле (``co64`` — то же для файлов больше 4 ГБ)
``stsz``     размер сэмпла: без него нельзя найти сэмпл **внутри** чанка
===========  =================================================================

Плюс ``elst``: список правок сдвигает всё время дорожки. Его пропуск — самая частая
ошибка самодельных разборов: у YTS-релизов ``media_time`` равен 2002 при масштабе 24000,
то есть ровно на два кадра, и без него вся карта уезжает на 83 мс — как раз настолько,
чтобы граница сегмента перестала попадать на опорный кадр.

**Где лежит moov.** У релизов для сети (YTS в том числе) — в голове, перед ``mdat``:
иначе плеер не начал бы играть, не скачав файл. Тогда карта стоит того же, что и голова,
которую показ греет под меню всё равно (:func:`torrcast.stream.warm_at`), — то есть ничего
сверх. Замер на «Moana.2.2024.REPACK.1080p.BluRay.x264.AAC5.1-[YTS.MX]»
(1.97 ГБ, 1304 опорных кадра, в рое один сид): три Range-запроса, 2.36 МБ, 15.9 с на
холодной раздаче и 0.05 с, когда те же байты уже в кэше TorrServer. Целиком ``moov`` там
5.26 МБ, но дорожка звука лежит за дорожкой видео, и до неё дело не доходит.

Карта сверена с ``ffprobe`` на живой раздаче в четырёх местах фильма (0…5 мин, 25 мин,
50 мин, 96 мин): 144 опорных кадра, расхождений по времени и по байтам — ноль.

Если ``moov`` оказался в хвосте, он всё равно находится — шагами по верхним боксам, по
16 байт заголовка на шаг: ``mdat`` в 2 ГБ при этом не читается ни байтом.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

from torrcast import InfraError
from torrcast.keymap import KeyMap, Point, Reader

__all__ = ["MOOV_CHUNK", "keys"]

#: Каким шагом дочитывается ``moov``. Разбор идёт строго вперёд, поэтому куски ложатся
#: подряд - для роя это лучший из возможных запросов. Мельче делать нечего: заход к
#: холодной раздаче стоит дороже мегабайта, крупнее - начинаем тянуть дорожку звука,
#: которая нам не нужна.
MOOV_CHUNK: Final = 1 << 20
#: Сколько верхних боксов пройдём в поисках ``moov``. Их в файле единицы (``ftyp``,
#: ``free``, ``mdat``, ``moov``); полсотни - это уже не mp4, а мусор, и лучше честно
#: сдаться, чем ходить по нему запросами.
MAX_TOP_BOXES: Final = 50


class _Window:
    """Кусок файла, который дочитывается по мере надобности — и только вперёд.

    Разбор ``moov`` идёт сверху вниз и никогда не возвращается назад, поэтому окно растёт
    подряд идущими Range-запросами и обрывается там, где разбору перестало быть нужно.
    Ровно поэтому дорожка звука (у «Моаны 2» это 3.2 МБ из 5.3) не читается вовсе: она
    лежит за дорожкой видео.
    """

    def __init__(self, reader: Reader, base: int, size: int, have: bytes = b"") -> None:
        self.reader = reader
        self.base = base
        self.size = size
        self.data = have[:size]

    def need(self, upto: int) -> None:
        """Дочитать так, чтобы байт ``upto`` (от начала окна) был на месте."""
        want = min(upto, self.size)
        if want <= len(self.data):
            return
        want = min(self.size, max(want, len(self.data) + MOOV_CHUNK))
        self.data += self.reader.read(self.base + len(self.data), want - len(self.data))

    def take(self, at: int, size: int) -> bytes:
        self.need(at + size)
        return self.data[at : at + size]


def _boxes(window: _Window, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    """Дети бокса: (тип, начало данных, конец бокса). Читает ровно заголовки.

    ⚠️ Именно генератор, а не список. Заголовок каждого следующего ребёнка лежит за
    предыдущим, то есть «перечислить всех детей» — это дочитать окно до последнего из них.
    У «Моаны 2» от YTS дети ``moov`` — это ``mvhd``, дорожка видео, дорожка звука и
    ``udta``: списком мы вычитывали все 5.26 МБ ради дорожки видео, которая кончается на
    2.08 МБ. Генератор обрывается на первом подошедшем — 2.36 МБ вместо 5.26 (замер
    на «Моане 2» от YTS).
    """
    at = start
    while at + 8 <= end:
        head = window.take(at, 16)
        if len(head) < 8:
            return
        size = struct.unpack(">I", head[:4])[0]
        kind = head[4:8]
        data = at + 8
        if size == 1:  # 64-битный размер: лежит сразу за типом
            if len(head) < 16:
                return
            size = struct.unpack(">Q", head[8:16])[0]
            data = at + 16
        elif size == 0:  # «до конца родителя» - так пишут последний бокс
            size = end - at
        if size < data - at or at + size > end:
            return
        yield kind, data, at + size
        at += size


def _find(window: _Window, start: int, end: int, want: bytes) -> tuple[int, int] | None:
    return next(((a, b) for kind, a, b in _boxes(window, start, end) if kind == want), None)


def _full(window: _Window, data: int) -> tuple[int, int]:
    """Заголовок ``FullBox``: версия и смещение сразу за версией с флагами."""
    return window.take(data, 1)[0], data + 4


def _table(window: _Window, data: int, end: int, width: int) -> tuple[int, int]:
    """Начало и число записей таблицы фиксированной ширины; лишнее не читаем."""
    _, at = _full(window, data)
    count = struct.unpack(">I", window.take(at, 4))[0]
    at += 4
    return at, min(count, max(0, (end - at) // width))


def _find_moov(reader: Reader, head: bytes) -> tuple[int, int, int]:
    """Где в файле лежит ``moov``: начало, размер и длина заголовка.

    Идём шагами по верхним боксам, читая по 16 байт заголовка: ``mdat`` в два гигабайта
    так не читается ни байтом, даже если ``moov`` спрятан за ним в хвосте файла.
    """
    at = 0
    for _ in range(MAX_TOP_BOXES):
        raw = head[at : at + 16] if at + 16 <= len(head) else reader.read(at, 16)
        if len(raw) < 8:
            break
        size = struct.unpack(">I", raw[:4])[0]
        kind = raw[4:8]
        header = 8
        if size == 1:
            if len(raw) < 16:
                break
            size = struct.unpack(">Q", raw[8:16])[0]
            header = 16
        if kind == b"moov":
            return at, size, header
        if size < header:
            break
        at += size
    raise InfraError("в mp4 нет бокса moov - карту опорных кадров взять неоткуда")


def _movie(window: _Window, moov: tuple[int, int]) -> tuple[int, float]:
    """Масштаб времени фильма и его длительность из ``mvhd`` — то же, что печатает ffprobe."""
    found = _find(window, *moov, b"mvhd")
    if found is None:
        return 0, 0.0
    version, at = _full(window, found[0])
    at += 16 if version == 1 else 8  # created/modified
    scale = struct.unpack(">I", window.take(at, 4))[0]
    length = (
        struct.unpack(">Q", window.take(at + 4, 8))[0]
        if version == 1
        else struct.unpack(">I", window.take(at + 4, 4))[0]
    )
    return scale, (length / scale if scale else 0.0)


def _video_trak(window: _Window, moov: tuple[int, int]) -> tuple[int, int]:
    """Дорожка видео: ту, что назвалась ``vide`` в ``hdlr``. Гадать не нужно (mkv — нужно)."""
    for kind, data, end in _boxes(window, *moov):
        if kind != b"trak":
            continue
        media = _find(window, data, end, b"mdia")
        if media is None:
            continue
        handler = _find(window, *media, b"hdlr")
        if handler is not None and window.take(handler[0] + 8, 4) == b"vide":
            return data, end
    raise InfraError("в mp4 нет дорожки видео")


def _track_id(window: _Window, trak: tuple[int, int]) -> int:
    found = _find(window, *trak, b"tkhd")
    if found is None:
        return 1
    version, at = _full(window, found[0])
    at += 16 if version == 1 else 8
    return int(struct.unpack(">I", window.take(at, 4))[0])


def _media_scale(window: _Window, media: tuple[int, int]) -> int:
    found = _find(window, *media, b"mdhd")
    if found is None:
        return 0
    version, at = _full(window, found[0])
    at += 16 if version == 1 else 8
    return int(struct.unpack(">I", window.take(at, 4))[0])


def _edit_shift(window: _Window, trak: tuple[int, int], movie: int, media: int) -> float:
    """Сдвиг из ``elst``, секунды: время наружу = время в файле **минус** этот сдвиг.

    Правки бывают двух видов, и обе встречаются в живых файлах:

    * обычная (``media_time >= 0``) выкидывает начало дорожки — так YTS-релизы срезают
      два кадра (``media_time = 2002`` при масштабе 24000);
    * пустая (``media_time = -1``) наоборот вставляет паузу перед дорожкой — так ffmpeg
      выравнивает видео со звуком, и ремукс mkv в mp4 даёт ровно её (6 мс).

    ⚠️ Пустую правку легко принять за «ничего не делает» и пропустить: она задана не в
    масштабе дорожки, а в масштабе фильма. Пропуск стоил бы 6 мс на всей карте — ровно
    столько, чтобы граница сегмента промахнулась мимо опорного кадра.
    """
    edits = _find(window, *trak, b"edts")
    found = _find(window, *edits, b"elst") if edits else None
    if found is None or not media:
        return 0.0
    version, at = _full(window, found[0])
    count = struct.unpack(">I", window.take(at, 4))[0]
    at += 4
    width = 20 if version == 1 else 12
    delay = 0.0
    for _ in range(min(count, max(0, (found[1] - at) // width))):
        raw = window.take(at, width)
        if version == 1:
            span, start = struct.unpack(">Qq", raw[:16])
        else:
            span, start = struct.unpack(">Ii", raw[:8])
        if start >= 0:
            return float(start) / media - delay
        delay += span / movie if movie else 0.0
        at += width
    return -delay


def _sync_samples(window: _Window, stbl: tuple[int, int], total: int) -> list[int]:
    """Номера опорных сэмплов (с единицы). Нет ``stss`` — опорным считается каждый."""
    found = _find(window, *stbl, b"stss")
    if found is None:
        return list(range(1, total + 1))
    at, count = _table(window, *found, 4)
    raw = window.take(at, count * 4)
    return list(struct.unpack(f">{count}I", raw))


def _sample_times(window: _Window, stbl: tuple[int, int], wanted: list[int]) -> list[int]:
    """Время декодирования нужных сэмплов, по сжатой таблице ``stts``.

    ⚠️ Разбор идёт **слиянием** двух отсортированных списков, а не поиском по таблице на
    каждый кадр. Ровно на этом месте карта mkv однажды стала квадратичной и стоила 18.5 с
    чистого процессора — повторять эту цену незачем.
    """
    found = _find(window, *stbl, b"stts")
    if found is None:
        raise InfraError("в mp4 нет таблицы stts - времена кадров взять неоткуда")
    at, count = _table(window, *found, 8)
    runs = struct.iter_unpack(">II", window.take(at, count * 8))
    times: list[int] = []
    sample, clock, run = 1, 0, next(runs, None)
    for want in wanted:
        while run is not None and want >= sample + run[0]:
            sample += run[0]
            clock += run[0] * run[1]
            run = next(runs, None)
        if run is None:
            break
        times.append(clock + (want - sample) * run[1])
    return times


def _offsets(window: _Window, stbl: tuple[int, int], wanted: list[int]) -> list[int]:
    """Смещение нужных сэмплов в файле: ``stsc`` + ``stco``/``co64`` + ``stsz``.

    Тем же слиянием, и по той же причине. У YTS-релизов сэмпл в чанке один, поэтому
    смещение получается точным до байта; когда их несколько, ``stsz`` даёт размеры
    предшественников внутри чанка — и лежит он аккурат перед ``stco``, то есть читается
    по дороге и бесплатно.
    """
    plain = _find(window, *stbl, b"stco")
    chunks = plain or _find(window, *stbl, b"co64")
    counts = _find(window, *stbl, b"stsc")
    if chunks is None or counts is None:
        return []
    width = 4 if plain else 8
    at, count = _table(window, *chunks, width)
    where = struct.unpack(f">{count}{'I' if plain else 'Q'}", window.take(at, count * width))
    at, count = _table(window, *counts, 12)
    runs = list(struct.iter_unpack(">III", window.take(at, count * 12)))
    sizes = _sample_sizes(window, stbl)

    found: list[int] = []
    chunk, sample, step, index = 1, 1, 1, 0  # чанк, первый сэмпл в нём, сэмплов на чанк
    for want in wanted:
        while True:
            if index < len(runs) and chunk >= runs[index][0]:
                step = runs[index][1]
                index += 1
                continue
            if step <= 0:
                return found
            following = runs[index][0] if index < len(runs) else len(where) + 1
            if want < sample + step * (following - chunk):
                break
            sample += step * (following - chunk)
            chunk = following
        skip, inside = divmod(want - sample, step)
        chunk += skip
        sample += skip * step
        if chunk > len(where):
            break
        found.append(where[chunk - 1] + sum(sizes[sample - 1 : sample + inside - 1]))
    return found


def _sample_sizes(window: _Window, stbl: tuple[int, int]) -> list[int]:
    """Размеры сэмплов из ``stsz``; общий размер на все — пустой список не нужен."""
    found = _find(window, *stbl, b"stsz")
    if found is None:
        return []
    _, at = _full(window, found[0])
    one, count = struct.unpack(">II", window.take(at, 8))
    if one:
        return [one] * count
    at += 8
    count = min(count, max(0, (found[1] - at) // 4))
    return list(struct.unpack(f">{count}I", window.take(at, count * 4)))


def keys(reader: Reader, head: bytes) -> KeyMap:
    """Карта опорных кадров mp4. ``head`` — уже прочитанные байты начала файла.

    Отдаёт точки **только дорожки видео**: ``hdlr`` называет её тип прямо, и угадывать
    дорожку по регулярности точек, как в mkv, здесь не нужно.
    """
    at, size, header = _find_moov(reader, head)
    # Окно отсчитывается от самого бокса, а его дети начинаются сразу за заголовком.
    window = _Window(reader, at, size, head[at:])
    moov = (header, size)
    movie, length = _movie(window, moov)
    trak = _video_trak(window, moov)
    media = _find(window, *trak, b"mdia")
    stbl = _find(window, *media, b"minf") if media else None
    stbl = _find(window, *stbl, b"stbl") if stbl else None
    if media is None or stbl is None:
        raise InfraError("в mp4 нет таблиц дорожки видео (stbl)")
    scale = _media_scale(window, media)
    if not scale:
        raise InfraError("в mp4 не читается масштаб времени дорожки (mdhd)")

    sizes = _find(window, *stbl, b"stsz")
    total = struct.unpack(">I", window.take(sizes[0] + 8, 4))[0] if sizes else 0
    sync = _sync_samples(window, stbl, total)
    if not sync:
        raise InfraError("в mp4 нет ни одного опорного кадра")
    times = _sample_times(window, stbl, sync)
    shift = _edit_shift(window, trak, movie, scale)
    ahead = _composition(window, stbl, sync)
    where = _offsets(window, stbl, sync)
    track = _track_id(window, trak)

    points = [
        Point((clock + ahead.get(number, 0)) / scale - shift, offset, track)
        for number, clock, offset in zip(sync, times, where, strict=False)
    ]
    if not points:
        raise InfraError("таблицы mp4 есть, но карта из них не собралась")
    if length <= 0:
        length = points[-1].at
    return KeyMap(length, tuple(sorted(points)), reader.taken, reader.requests, "mp4")


def _composition(window: _Window, stbl: tuple[int, int], wanted: list[int]) -> dict[int, int]:
    """Сдвиги ``ctts`` для нужных сэмплов; нет таблицы — B-кадров нет и сдвига тоже.

    ⚠️ Именно этот сдвиг превращает время декодирования в то, что показывает ffprobe и
    по чему режет сегментный муксер. У «Моаны 2» он равен ``elst`` и с ним сокращается —
    но полагаться на это нельзя: в первом же релизе с другим кодировщиком они разъедутся.
    """
    found = _find(window, *stbl, b"ctts")
    if found is None:
        return {}
    at, count = _table(window, *found, 8)
    runs = struct.iter_unpack(">Ii", window.take(at, count * 8))
    ahead: dict[int, int] = {}
    sample, run = 1, next(runs, None)
    for want in wanted:
        while run is not None and want >= sample + run[0]:
            sample += run[0]
            run = next(runs, None)
        if run is None:
            break
        ahead[want] = run[1]
    return ahead
