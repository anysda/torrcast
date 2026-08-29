"""Где кончается уже уложенный кусок, по его собственному хвосту."""

from __future__ import annotations

import math
from pathlib import Path

from torrcast.usecases.warm.settings import TAIL_BYTES, TS_PACKET, TS_SYNC
from torrcast.usecases.warm.ts_stamp import _stamp


def segment_end(path: Path) -> float:
    """Метка последнего кадра ЛЮБОЙ дорожки куска; ``nan``, если хвост TS прочесть нельзя.

    Читается хвост уже лежащего файла, и только он — по той же причине, что и голова
    (:func:`torrcast.usecases.warm.ts_stamp.ts_stamp`): сверка стоит на горячем
    пути показа и не имеет права ни ждать сеть, ни поднимать процесс.

    🔴 TC-772. Считается последняя метка по ВСЕМ дорожкам — и звуковой, и видео, — а не
    по одной видео, и это не осторожность, а единственный способ отличить обрезок от
    свойства релиза. Длительность фильма берётся из паспорта контейнера
    (:attr:`torrcast.adapters.stream_pack.grid.Grid.duration`), а паспорт меряет весь
    контейнер, то есть самую длинную дорожку. Видеодорожка кончиться раньше неё имеет
    полное право: у релиза «Kung Fu Panda WEB-DL» последний видеокадр стоит на 5521.0 при
    паспорте 5526.176 — звук идёт ещё пять секунд по чёрному полю. Это ЗДОРОВЫЙ файл, и
    хвост у него здоровый.

    Замер на 33 настоящих релизах (mkv, mp4, ts; из них 4 avi отпали — видео в них не
    перекладывается в TS копией). Недобор целого хвоста до паспорта:

    * по одной видеодорожке — 0.000-1.323 с, и на 3 релизах из 33 (9%) он больше любого
      разумного допуска: у всех трёх «The Lord of the Rings Extended-Cut BDRip-AVC» это
      1.0-1.323 с. У «Kung Fu Panda» же в последних 64 КиБ видеопакетов нет ВОВСЕ, и
      мера по видео возвращала бы ``nan`` — то есть «конец не прочитан» на целом куске;
    * по любой дорожке — 0.000-0.261 с, медиана 0.005 с, ни одного выброса.

    А обрезанный кусок обе дорожки теряет вместе: его закрывает муксер, и звук за
    видео не продолжается. Замер тем же резом на 5 релизах: недобор по любой дорожке
    0.593-7.640 с, знак в знак с недобором по видео. Свободный промежуток 0.261-0.593
    и держит :data:`torrcast.usecases.warm.settings.TAIL_GAP_MAX`.

    Тем же меряет обрыв прогона живая упаковка
    (:func:`torrcast.adapters.stream_pack.packer_finished._reached`): она берёт конец куска
    из списка нарезки ffmpeg, а там стоит конец МУКСА — то есть последний пакет любой
    дорожки. Поэтому на этих релизах живая упаковка и не спотыкалась никогда, а сверка
    прогретого по одной видеодорожке спотыкалась бы на каждом показе.

    ``nan`` — честное «не знаю»: файл не читается или не выровнен по пакетам TS.
    """
    try:
        size = path.stat().st_size
        offset = max(0, size - TAIL_BYTES)
        offset -= offset % TS_PACKET
        with path.open("rb") as handle:
            handle.seek(offset)
            tail = handle.read()
    except OSError:
        return math.nan
    latest = math.nan
    for at in range(0, len(tail) - TS_PACKET + 1, TS_PACKET):
        packet = tail[at : at + TS_PACKET]
        if packet[0] != TS_SYNC:
            return math.nan
        control = (packet[3] >> 4) & 0x3
        payload = 4
        if control & 0x2:
            payload = 5 + packet[4]
        if not control & 0x1 or payload + 14 > TS_PACKET or not packet[1] & 0x40:
            continue
        pes = packet[payload:]
        # 0xC0-0xDF - звук, 0xE0-0xEF - видео: конец куска ставит любая из них.
        if pes[:3] != b"\x00\x00\x01" or not 0xC0 <= pes[3] <= 0xEF or not pes[7] & 0x80:
            continue
        mark = _stamp(pes[9:14])
        latest = mark if math.isnan(latest) else max(latest, mark)
    return latest
