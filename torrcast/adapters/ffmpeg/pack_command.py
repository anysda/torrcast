"""Собирает команду ffmpeg для упаковки; её вызывает медиатракт."""

from typing import Any, Protocol

from torrcast.ports.journal.slot import journal


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
    split_slack: float = 0.02,
    audio_codec: str = "aac",
    audio_channels: int = 2,
    audio_bitrate: str = "192k",
    pack_list: str = "index.csv",
) -> list[str]:
    """Собрать прежнюю команду сегментного муксера без запуска процесса.

    🔴 TC-629. Наружу не выходит ни один рез, который для муксера уже в прошлом. Резы
    отмеряются от ПЕРВОГО ПАКЕТА прогона (``grid.start(k) - at``), поэтому рез «раньше
    начала» — это не неточность, а несуществующее место: на списке, начинающемся с минуса,
    сегментный муксер не режет ВООБЩЕ и пишет один кусок до конца фильма. Замер на стенде:
    ``at`` позже своей границы на один сегмент → ``-segment_times -8.000,0.000,8.000,…`` →
    **один кусок 21.2 МБ** вместо одиннадцати по 2.1 МБ; на живом релизе это было 240 МБ
    при норме 12 МБ.

    Это **последний рубеж, а не лечение**. Штатно ``at`` приезжает сюда уже верным:
    место захода переводит в ленту фильма
    :func:`torrcast.adapters.stream_pack.pack_start.pack_start`, и уехать дальше границы больше чем
    на сегмент ему там уже неоткуда. Здесь ловится то, что просочилось мимо — новый вызывающий,
    чужой контейнер, незнакомый демуксер.

    ⚠️ Зажим не бесплатен и не безобиден, поэтому он **говорит в журнал**, а не подменяет
    число молча. Встать позже своей границы прогон вполне может по-честному: у mpegts
    перемотка садится на СЛЕДУЮЩИЙ опорный кадр (:data:`torrcast.domain.warm_open.SEEK_SHIFT`), и
    такой уезд — правда о потоке. Молча такое прятать нельзя: ровно тихая подмена и
    довела этот дефект живым до приёмки.

    🔴 Но громкость записи зависит от сетки, и это замер, а не вкус (TC-693). На сетке ПО
    ОПОРНЫМ КАДРАМ граница и есть опорный кадр, садиться позже неоткуда, и запись
    ``заход позже своей границы`` — заявка на разбор: на честном входе она молчит всегда
    (замер: 0 из 419 границ). На РОВНОЙ сетке граница с опорными кадрами не совпадает по
    построению, посадка на следующий кадр — норма этого пути, и та же запись говорит 688
    раз из 768. Аварийным именем это красило бы штатную работу, поэтому у ровной сетки
    запись своя и спокойная — ``посадка позже границы на ровной сетке``. Само число
    зажимается одинаково: ошибиться именем куска нельзя ни на какой сетке.
    """
    run = run_dir.rstrip("/")
    if at > grid.start(slot):
        journal().mark(
            "заход позже своей границы"
            if grid.on_keys
            else "посадка позже границы на ровной сетке",
            слот=slot,
            граница=round(grid.start(slot), 3),
            замер=round(at, 3),
        )
        at = grid.start(slot)
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
        times = f"{grid.end(grid.count - 1) + 1.0 - at:.3f}"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]
    if readrate > 0:
        command += ["-readrate", f"{readrate:g}"]
        if burst > 0:
            command += ["-readrate_initial_burst", f"{burst:g}"]
    command += ["-copyts"]
    if slot > 0:
        command += ["-ss", f"{grid.start(slot):.3f}"]
    command += ["-i", source_url, "-map", "0:v:0", "-map", f"0:a:{audio_index}"]
    command += ["-c:v", "copy"] if encode is None else encode.args(grid, slot, upto - 2)
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
        "-muxdelay",
        "0",
        "-muxpreload",
        "0",
        "-avoid_negative_ts",
        "disabled",
        "-f",
        "segment",
        "-segment_format",
        "mpegts",
        "-segment_time_delta",
        f"{split_slack:g}",
        "-break_non_keyframes",
        f"{0 if grid.on_keys else 1}",
        "-segment_start_number",
        f"{slot - 1 if behind else slot}",
        "-segment_list",
        f"{run}/{pack_list}",
        "-segment_list_type",
        "csv",
        "-segment_list_flags",
        "+live",
    ]
    command += ["-segment_times", times]
    command.append(f"{run}/v%d.ts")
    return command
