"""Собирает команду ffmpeg для упаковки; её вызывает медиатракт."""

from typing import Any, Final, Protocol

from torrcast.adapters.ffmpeg.pack_inputs import pack_inputs
from torrcast.domain.segment_container import FMP4, MPEGTS, SegmentContainer
from torrcast.domain.segment_suffix import segment_suffix
from torrcast.ports.journal.slot import journal

#: Допуск реза (``-segment_time_delta``) для захода, который ставит опорные кадры сам, -
#: на ЛЮБОЙ сетке. Рез идёт ПО КАДРУ, а муксер отмеряет его от первого пакета прогона,
#: встающего на долю кадра позже границы: допуск обязан покрывать эту долю плюс отступ
#: принудительного кадра (:data:`torrcast.adapters.recode.encode_settings._KEY_SLACK`, 0.02 с).
#: Замер настоящим ffmpeg (ролик 60 с, ровная сетка 10 с): доля кадра вышла 0.010 с на
#: 23.976 к/с и 0.013 с на 29.97 к/с; с прежними 0.02 с муксер проходит мимо
#: принудительного кадра и склеивает два места в одно - кусок 19.98 с вместо двух по 10.
#: Покрывает период вплоть до 6 к/с. А на сетке ПО ОПОРНЫМ КАДРАМ доля превращается в
#: целый кадр, когда граница в ``-ss`` с тремя знаками округляется вверх (ровные 24 к/с:
#: 10.416(6) пишется как "10.417") - точная перемотка роняет кадр на границе, и с узким
#: допуском ВСЕ резы захода уезжают на слот (замер там же: +10.417 с при исправном звуке).
KEY_CUT_SLACK: Final = 0.2


class _Grid(Protocol):
    @property
    def count(self) -> int: ...

    @property
    def origin(self) -> float: ...

    @property
    def on_keys(self) -> bool: ...

    def start(self, slot: int) -> float: ...

    def end(self, slot: int) -> float: ...


def pack_command(
    source_url: str,
    audio_index: int,
    run_dir: str,
    grid: _Grid,
    slot: int,
    at: float,
    readrate: float = 1.0,
    burst: float = 0.0,
    encode: Any = None,
    until: int = -1,
    *,
    seek: float | None = None,
    voice_url: str = "",
    split_slack: float = 0.02,
    audio_codec: str = "aac",
    audio_channels: int = 2,
    audio_bitrate: str = "192k",
    pack_list: str = "index.csv",
    container: SegmentContainer = MPEGTS,
    video_tag: str = "",
) -> list[str]:
    """Собрать прежнюю команду сегментного муксера без запуска процесса.

    🔴 TC-629. Наружу не выходит ни один рез, который для муксера уже в прошлом. Резы
    отмеряются от ПЕРВОГО ПАКЕТА прогона (``grid.start(k) - at``), поэтому рез «раньше
    начала» — это не неточность, а несуществующее место: на списке, начинающемся с минуса,
    сегментный муксер не режет ВООБЩЕ и пишет один кусок до конца фильма. Замер на стенде:
    ``at`` позже своей границы на один сегмент → ``-segment_times -8.000,0.000,8.000,…`` →
    **один кусок 21.2 МБ** вместо одиннадцати по 2.1 МБ; на живом релизе — 240 МБ при 12.

    Это **последний рубеж, а не лечение**: штатно место захода переводит в ленту фильма
    :func:`torrcast.adapters.stream_pack.pack_start.pack_start`. Здесь ловится то, что
    просочилось мимо — новый вызывающий, чужой контейнер, незнакомый демуксер.

    🔴 TC-1002. Рубеж стоит на СВОЁМ слоте, а не на его начале: в минус список уходит ровно
    тогда, когда прогон вошёл ЗА КОНЕЦ слота, — первый названный рез это граница
    СЛЕДУЮЩЕГО, и пока заход внутри своего места, рез остаётся в будущем. Зажимать заход
    внутри слота нельзя: продолжение с закладки заходит ровно на опорный кадр посреди слота
    (:func:`torrcast.usecases.feed_pack.feed_restart._begin`), и подмена числа на границу
    увела бы ВСЕ резы прогона вперёд на долю слота — куски поехали бы под чужими именами.

    ⚠️ Встать позже границы прогон может и по-честному: у mpegts перемотка садится на
    СЛЕДУЮЩИЙ опорный кадр (:data:`torrcast.domain.warm_open.SEEK_SHIFT`). Молча такое
    прятать нельзя — ровно тихая подмена и довела дефект живым до приёмки, — поэтому уезд
    **говорит в журнал**. Громкость записи зависит от сетки, и это замер, а не вкус
    (TC-693): на сетке ПО ОПОРНЫМ КАДРАМ граница и есть опорный кадр, садиться позже
    неоткуда, и запись ``заход позже своей границы`` — заявка на разбор (0 из 419 границ).
    На РОВНОЙ сетке посадка на следующий кадр — норма пути (688 из 768), там запись своя и
    спокойная. Числом дело кончается только на уезде за конец слота, и у него запись третья.

    ``voice_url`` — отдельный файл со звуком рядом с видео
    (:func:`torrcast.adapters.ffmpeg.pack_inputs.pack_inputs`); пусто — звук из видеофайла.

    ``seek`` — с какого места прогон заходит на самом деле, то есть что уедет в ``-ss``.
    Обычно это и есть граница, и тогда его не называют. Врозь они расходятся там, где
    демуксер садится ПОЗЖЕ границы: заход отводят назад
    (:func:`torrcast.adapters.stream_pack.settle_start.settle_start`).
    """
    run = run_dir.rstrip("/")
    tail = grid.end(grid.count - 1) + 1.0  # секунда за концом фильма: туда смотрит рез хвоста
    entry = grid.start(slot) if seek is None else seek
    line = round(grid.start(slot), 3)
    if at > grid.start(slot):
        flat = "посадка позже границы на ровной сетке"
        late = "заход позже своей границы" if grid.on_keys else flat
        journal().mark(late, слот=slot, граница=line, замер=round(at, 3))
    if at >= grid.end(slot):
        # Нарушен тут КОНЕЦ слота, он и пишется: читающий след ищет то число, о котором
        # спор, а начало слота стоит строкой выше и в этой записи не при чём.
        end = round(grid.end(slot), 3)
        journal().mark("заход за концом своего слота", слот=slot, граница=end, замер=round(at, 3))
        at = grid.start(slot)
    # Копия берёт их у исходника, и на ровной сетке они с границами не совпадают по
    # построению - там режем по времени. Перекодирующий заход ставит их САМ и ровно на
    # границы (:meth:`torrcast.adapters.recode.encode.Encode.args`), поэтому режет по ним на
    # любой сетке - с допуском :data:`KEY_CUT_SLACK`.
    #
    # Рез по времени у такого захода отдаёт принудительный кадр куску СЛЕВА: рез
    # отмеряется от первого пакета прогона, а он встаёт на долю кадра позже границы. Кусок
    # справа остаётся без единого опорного кадра, то есть без картинки после склейки
    # (:func:`torrcast.adapters.stream_pack.key_missing.key_missing`), и его выбрасывает
    # выкладка - вместе с потолком битрейта, который в нём и уезжал. Замер настоящим
    # ffmpeg (заход v1..v3 по ровной сетке 10 с): 1 кусок из 3 на 23.976 к/с и 1 из 3 на
    # 29.97 к/с; на 24 и 25 к/с, где период кадра делит границу нацело, - ни одного.
    own_keys = encode is not None
    by_key = grid.on_keys or own_keys
    behind = encode is None and at < grid.start(slot) - split_slack
    first = slot if behind else slot + 1
    upto = grid.count if until < 0 else min(until + 2, grid.count)
    times = ",".join(f"{grid.start(k) - at:.3f}" for k in range(first, upto))
    if not times:
        # 🔴 TC-771. Внутри захода в один-единственный слот-хвост границ сетки нет вовсе,
        # и список резов выходил пустым. Пустой список - это не «не режь», а МОЛЧАНИЕ:
        # сегментный муксер берёт своё умолчание (2 с) и режет хвост по первому опорному
        # кадру за ним. Замер настоящим ffmpeg: законный хвост 7.884 с / 2 086 048 Б
        # выходил куском 2.113 с / 554 788 Б плюс три лишних. Лишние выкладка отбрасывает
        # сама («обрезок за ``-to``»), а обрезанный первый уезжает зрителю: начало у него
        # верное, а длину не сверял никто - то есть терялся конец фильма.
        #
        # Поэтому рез называется ВСЕГДА, и для такого захода он ставится туда же, куда
        # смотрит ``-to``: за концом прогона. Назвать рез на самом конце нельзя - муксер
        # отработал бы его по ближайшему опорному кадру ПЕРЕД ним, то есть тем же
        # обрезком. Границы и имена кусков от этого не двигаются ни на миллисекунду:
        # список резов пустым бывает ровно тогда, когда заход кончается последним слотом
        # сетки, и резать внутри него нечего по построению.
        times = f"{tail - at:.3f}"
    head = entry if slot > 0 else None
    command = pack_inputs(source_url, audio_index, head, readrate, burst, voice_url, tail)
    command += ["-c:v", "copy"] if encode is None else encode.args(grid, slot, upto - 2)
    if video_tag:
        command += ["-tag:v", video_tag]
    if until >= 0:
        command += ["-to", f"{grid.end(until) + 1.0:.3f}"]
    if grid.origin > 0:
        command += ["-output_ts_offset", f"{grid.origin:.3f}"]
    command += [
        "-c:a",
        audio_codec,
        "-ac",
        f"{audio_channels}",
        "-b:a",
        audio_bitrate,
        "-avoid_negative_ts",
        "disabled",
        "-f",
        "segment",
        "-segment_format",
        "mp4" if container == FMP4 else "mpegts",
        "-segment_time_delta",
        f"{KEY_CUT_SLACK if own_keys else split_slack:g}",
        "-break_non_keyframes",
        f"{0 if by_key else 1}",
        "-segment_start_number",
        f"{slot - 1 if behind else slot}",
        "-segment_list",
        f"{run}/{pack_list}",
        "-segment_list_type",
        "csv",
        "-segment_list_flags",
        "+live",
    ]
    if container == FMP4:
        command += [
            "-segment_format_options",
            "movflags=cmaf",
            "-segment_header_filename",
            f"{run}/init.mp4",
            "-individual_header_trailer",
            "0",
            "-write_header_trailer",
            "0",
        ]
    else:  # оба флага и оба по нулю: mpegts иначе двигает ВСЕ метки на 0.7 + 0.7 = 1.4 с
        at_option = command.index("-avoid_negative_ts")
        command[at_option:at_option] = ["-muxdelay", "0", "-muxpreload", "0"]
    command += ["-segment_times", times]
    command.append(f"{run}/v%d{segment_suffix(container)}")
    return command
