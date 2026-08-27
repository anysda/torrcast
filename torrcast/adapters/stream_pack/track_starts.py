"""Где на ленте стоят обе дорожки готового куска: метки их первых пакетов.

Спрашивает выкладка упаковщика (:mod:`torrcast.adapters.stream_pack._merged_out`) и ужатие
на месте (:mod:`torrcast.adapters.stream_pack._shrunk_out`) - у каждой склейки, прежде чем
отдать её приёмнику.
"""

from __future__ import annotations

import json
import math
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from torrcast.domain.probe_settings import _TIMEOUT

#: Сколько пакетов головы читает проба. Дорожки в куске чередуются: кадр видео - это 41 мс
#: на самом медленном кино (23.976 к/с), кадр AAC - 21-23 мс, поэтому обе дорожки
#: показываются в первом же десятке пакетов. Замер на корпусе из 34 склеек (24, 25, 29.97 и
#: 50 к/с, звук 44.1 и 48 кГц, куски 4-20 с): обеих дорожек хватало уже восьми пакетов, все
#: 34 раза. Сорок - запас впятеро; цена от него не зависит, её держит подъём процесса.
#:
#: Голова, а не весь кусок, - это и мера, и цена. Цена (замер, медиана 12 прогонов на кусок):
#: голова 79.6 / 86.9 / 92.6 мс на кусках 2.8 / 9.7 / 15.8 МБ, полное чтение тех же -
#: 87.8 / 108.9 / 139.6 мс. То есть голова почти не зависит от веса (её держит подъём
#: процесса), а полное чтение растёт с ним, и куски бывают по 16-28 МБ. Мера:
#: дорожка, не попавшая в голову, начинается позже всей головы - то есть дальше любого
#: порога места, и ``nan`` за неё говорит ровно то, что нужно решению: на своём месте её нет.
_HEAD_PACKETS: Final = 40


def track_starts(
    piece: str | Path, timeout: float = _TIMEOUT, *, run: Callable[..., Any] = subprocess.run
) -> tuple[float, float]:
    """Метки первых пакетов **картинки и звука** куска, секунды ленты; ``nan`` - не нашли.

    🔴 TC-833. Склейка (:func:`torrcast.adapters.stream_pack.merge_tracks.merge_tracks`) берёт
    картинку из куска кодировщика, а звук - из куска упаковщика **с тем же номером**, и до
    сих пор верила, что один номер значит одно место фильма. Это неправда всякий раз, когда
    сегментный муксер пропускает рез: границы он отмеряет по своему списку, а файлы считает
    подряд, - и номер файла перестаёт быть номером слота. Живой замер («Матрица», 26-08):
    манифест 741 кусок по ~10.5 с, упаковщик 112 кусков длиной 0.041-79.3 с, сдвиг звука от
    картинки +123…+324 с. Зритель слышит это как «звук то есть, то нет».

    Ловится это только здесь. Сторож уложенного (:func:`~torrcast.usecases.warm.segment_start`)
    берёт метку первого пакета ВИДЕО и только его; звук до этой карточки не проверял никто, и
    склейка с чужим звуком уезжала зрителю кодом ноль.

    Отдаются обе метки, а не их разница, и это не мелочь: сравнивать их надо не между собой,
    а **с границей слота**, потому что промахнуться вправе любая из двух. Замер на корпусе из
    53 здоровых склеек: разница дорожек между собой доходит до 0.197 с там, где каждая из них
    стоит на своей границе с точностью 0.04-0.19, - то есть порог на разницу пришлось бы
    делать вдвое шире и он всё равно не сказал бы, КОТОРАЯ уехала. Тот же корпус поймал этим
    разделением вторую поломку того же рода: заход кодировщика на сетке по опорным кадрам
    потерял рез и уехал ровно на слот (+10.417 с) при исправном звуке - на разнице дорожек это
    выглядело бы виной звука, и наружу ушёл бы как раз испорченный перекод.

    ``nan`` у дорожки - честное «на своём месте её нет»: ffprobe не поднялся, не дожил, не
    разобрал контейнер (голый фрагмент fMP4 без своего заголовка), в куске такой дорожки нет
    вовсе или она начинается позже всей головы. Решает по нему вызывающий, и решает отказом:
    цена отказа - шов звука на голове захода кодировщика, то есть 2-5 с пересборки
    синхронизации у приёмника; цена доверия молчанию - десять секунд чужого звука.

    ⚠️ ``start_time`` потоков на этот вопрос НЕ отвечает, и это проверено: у mpegts он берётся
    от часов транспорта, а не от первого пакета дорожки. На куске с разошедшимся звуком
    (картинка 20.154, звук 40.096) ffprobe печатает ``start_time`` 20.154 у ОБЕИХ дорожек - то
    есть отвечает «сошлось» там, где разошлось на двадцать секунд. Проба, построенная на нём,
    была бы куплена одной строкой.

    Цена пробы: 80-93 мс на кусок (замер, куски 2.8-15.8 МБ, медиана 12 прогонов на каждый),
    рядом со склейкой в 90.5 мс (замер, 34 куска, разброс 75.3-116.8). Байт проба не пишет ни
    одного: файл склейки написан и без неё, а отказ его сносит.

    🔴 Не попавшую в голову дорожку проба спрашивает ОТДЕЛЬНО, и на CMAF без этого меры нет
    вовсе. Пакеты муксер отдаёт по возрастанию метки, а у куска CMAF счётчики дорожек свои
    (:func:`torrcast.domain.chunk_tape.tape_spots`): на живом куске показа звук стоит на
    49.792, а картинка того же куска - на 59.809, и весь звук куска (467 пакетов) выходит
    ПЕРЕД первым пакетом картинки. Голова в сорок пакетов не доставала до картинки никогда,
    то есть проба отвечала «картинки на месте нет» о каждом здоровом куске.

    Спрошенная порознь дорожка стоит 0.15 с и только там, где в голове её не нашлось: на
    mpegts обе дорожки лежат в первом десятке пакетов, и второго ffprobe там не бывает.
    Смысл ``nan`` от этого не меняется: дорожки нет в куске вовсе - решать по нему
    вызывающему, и решает он отказом.

    ``piece`` бывает и строкой: голый кусок CMAF читается только вместе со своим заголовком
    (:func:`torrcast.adapters.stream_pack.piece_with_head.piece_with_head`), а это протокол
    чтения, а не файл на диске.

    ``run`` - чем поднимается ffprobe. Доводом, а не именем модуля: прежде стенд подменял
    :mod:`subprocess` целиком, вместе с его же классом ошибок, - то есть знал не договор
    пробы, а список имён внутри неё.
    """
    command = [
        "ffprobe", "-v", "error", "-read_intervals", f"%+#{_HEAD_PACKETS}",
        "-show_entries", "stream=index,codec_type:packet=stream_index,pts_time",
        "-of", "json", str(piece),
    ]  # fmt: skip
    try:
        done = run(command, capture_output=True, timeout=timeout, check=False)
        payload = json.loads(done.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return math.nan, math.nan
    if not isinstance(payload, dict):
        return math.nan, math.nan
    kinds: dict[int, str] = {}
    for stream in payload.get("streams") or []:
        if isinstance(stream, dict) and isinstance(stream.get("index"), int):
            kinds[stream["index"]] = str(stream.get("codec_type", ""))
    first: dict[str, float] = {}
    for packet in payload.get("packets") or []:
        if not isinstance(packet, dict):
            continue
        kind = kinds.get(packet.get("stream_index", -1), "")
        if kind not in ("video", "audio") or kind in first:
            continue
        try:
            first[kind] = float(packet["pts_time"])
        except (KeyError, TypeError, ValueError):
            continue
    for kind, stream in (("video", "v"), ("audio", "a")):
        if kind not in first:
            apart = _apart(piece, stream, timeout, run=run)
            if apart is not None:
                first[kind] = apart
    return first.get("video", math.nan), first.get("audio", math.nan)


def _apart(
    piece: str | Path, stream: str, timeout: float, *, run: Callable[..., Any]
) -> float | None:
    """Метка первого пакета одной дорожки, спрошенной у неё самой; ``None`` - не ответила."""
    command = [
        "ffprobe", "-v", "error", "-select_streams", stream, "-read_intervals", "%+#4",
        "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(piece),
    ]  # fmt: skip
    try:
        done = run(command, capture_output=True, timeout=timeout, check=False)
        lines = done.stdout.decode("utf-8", "replace").splitlines()
    except (OSError, subprocess.SubprocessError, AttributeError):
        return None
    found = []
    for line in lines:
        try:
            found.append(float(line.strip().rstrip(",")))
        except ValueError:
            continue
    return min(found) if found else None
