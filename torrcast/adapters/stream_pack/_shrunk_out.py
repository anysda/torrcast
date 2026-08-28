"""Что уходит наружу от ужатия на месте: его картинка со звуком тяжёлой копии.

Зовёт это выкладка упаковщика (:mod:`torrcast.adapters.stream_pack.packer_publish`).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack.bare_on_tape import bare_on_tape
from torrcast.adapters.stream_pack.splice_on_tape import splice_on_tape
from torrcast.domain.mixed_name import mixed_name
from torrcast.domain.segment_container import FMP4, MPEGTS, SegmentContainer
from torrcast.domain.track_place import TRACK_PLACE_MAX
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _shrunk_out(
    run_dir: Path,
    slot: int,
    copy: Path,
    shrunk: Path,
    cap: int,
    want: tuple[float, float],
    container: SegmentContainer = MPEGTS,
    heads: tuple[Path | None, Path | None] = (None, None),
    *,
    merge: Callable[..., bool],
    shift_of: Callable[[Path, Path], float | None],
    keyless: Callable[[Path], bool],
    starts_of: Callable[[Path], tuple[float, float]],
    on_tape: Callable[..., bool] = splice_on_tape,
    on_bare: Callable[..., bool] = bare_on_tape,
) -> Path:
    """Файл ужатого места для приёмника: склейка со звуком копии, иначе ужатие как есть.

    🔴 Ужатие на месте - это ВТОРОЙ прогон ffmpeg над одним местом фильма, и звук он
    приносит свой. Кадровая сетка AAC отсчитывается от ``-ss`` прогона, а прогоны у
    соседних кусков и у ужатого разные, поэтому сетки сдвинуты друг относительно друга
    на произвольную долю кадра - ровно та беда, ради которой написана
    :func:`torrcast.adapters.stream_pack.merge_tracks.merge_tracks`, только приходит она не с
    головы захода кодировщика, а с обоих стыков ужатого куска сразу.

    Замер на живом показе (1080p, 13.5 Мбит/с, место 3:33, ужато одно место окна):
    у соседей-копий стык звука ``+0.021333`` с - ровно один кадр AAC, - а у ужатого
    на входе ``+0.074667`` (дыра **53 мс**), на выходе ``-0.053334`` (метки НАЗАД).
    Ужатое место при этом честное: метки картинки на обоих стыках совпадают с копией
    до 0.0004 с, вес и битрейт внутри потолков.

    Платит за эти 53 мс приёмник секундами, и говорит об этом сам: на стыке он пишет
    ``DEMUXER_UNDERFLOW`` по ЗВУКУ, гасит конвейер и уходит в BUFFERING. Живой замер по
    его же часам - **4.1 и 4.3 с** потерянной плёнки на этом месте в двух прогонах без
    склейки против **нуля** (ниже 0.05 с) в трёх прогонах подряд с ней; остальная лента
    у всех пяти одна и та же. Картинку это не лечит и не должно: смена настройки
    видеодекодера на границе ужатого места остаётся, со склейкой она стоит тех же нулей.

    Склеивать есть с чем и есть чем: тяжёлая копия этого же места ещё лежит в каталоге
    прогона (её вес и позвал ужатие), и её звук - тот самый непрерывный поток, что уехал
    в соседние куски. Склейка - переупаковка без единого перекодирования.

    Потолок веса проверяется здесь же, а не у вызывающего: наружу уходит ровно один из
    двух файлов, и решать, какой, обязано одно место. Не влезла склейка - она сносится,
    и место идёт голой картинкой ужатия, как ходило раньше.

    ⚠️ Кусок БЕЗ опорного кадра в начале не склеивается вовсе (TC-698): склейка идёт
    ``-c copy``, а копирование выбрасывает всё до первого опорного кадра, и склеить такой
    кусок значит отдать приёмнику место без картинки. Свежий перекод такого не даёт -
    первый кадр захода всегда опорный, - но сюда приходит и готовый кусок кодировщика,
    доехавший, пока ужатие ждало замка, а он таким бывает. Ему остаётся прежний путь:
    наружу как есть.

    ⚠️ Звук копии годится, только пока копия - это ЭТО ЖЕ место фильма (TC-833). Ужатие берёт
    копию из своего же каталога прогона и по тому же номеру, что и выкладка, поэтому промах
    номера здесь тот же самый: муксер, пропустивший рез, сдвигает нумерацию файлов, и под
    именем слота лежит другое место. Обе дорожки готовой склейки сверяются с ``want`` -
    местом слота на ленте КАРТИНКИ и на ленте ЗВУКА (:func:`track_starts`), - и не сошедшаяся
    наружу не идёт: ужатое как есть - это шов звука на двух стыках, а склейка с чужим звуком -
    десять секунд чужого звука. Мест два, потому что лент две: на CMAF счётчик у каждой
    дорожки свой (:mod:`torrcast.adapters.stream_pack.run_tape`). ``want`` бывает ``nan``
    (сетки у прогона нет или лента не измерена) - тогда место не проверяется вовсе.

    ``heads`` - заголовки прогонов, сделавших картинку (ужатие) и звук (копия). Без них
    склейка на CMAF не выходит вовсе: голый фрагмент не открывается ничем
    (:func:`torrcast.adapters.stream_pack.piece_with_head.piece_with_head`).

    ``on_bare`` ставит на ту же ленту само УЖАТИЕ
    (:func:`torrcast.adapters.stream_pack.bare_on_tape.bare_on_tape`): это второй прогон
    ffmpeg над одним местом, счёт у него свой, и всюду, где склейка не сложилась, наружу
    уходит именно он. Отказ выкладку не отменяет: кусок уходит как уходил, но уже не молча.

    ``on_tape`` ставит готовую склейку на ленту показа
    (:func:`torrcast.adapters.stream_pack.splice_on_tape.splice_on_tape`): собрана она новым
    прогоном ffmpeg, и счёт у него начинается с нуля, а уйти она обязана туда же, где стоял
    ужатый кусок. Не встала - наружу идёт ужатое как есть: шов звука дешевле, чем кусок,
    уводящий приёмник в начало ленты.

    ``merge``, ``shift_of``, ``keyless`` и ``starts_of`` приезжают доводами: все четверо
    поднимают ffmpeg и ffprobe на настоящих кусках, а здесь меряется решение - что именно
    уедет на приёмник.
    """
    if keyless(shrunk):
        on_bare(shrunk, copy, slot, "ужатие", container, heads)
        return shrunk
    mixed = run_dir / mixed_name(slot, container)
    why = "склейка ужатого не вышла"
    shift = shift_of(copy, shrunk) or 0.0
    if merge(shrunk, copy, mixed, shift=shift, container=container, heads=heads):
        if container == FMP4 and not on_tape(mixed, copy, heads[1]):
            mixed.unlink(missing_ok=True)
            journal().mark("склейку ужатого не поставить на ленту показа", слот=slot)
            on_bare(shrunk, copy, slot, "ужатие", container, heads)
            return shrunk
        astray = [
            name
            for name, mark, place in zip(("картинка", "звук"), starts_of(mixed), want, strict=True)
            if not math.isnan(place) and not abs(mark - place) <= TRACK_PLACE_MAX
        ]
        if not astray:
            try:
                if mixed.stat().st_size <= cap:
                    return mixed
            except OSError:
                pass
        else:
            why = f"склейка ужатого не с этого места: {' и '.join(astray)}"
    mixed.unlink(missing_ok=True)
    # Молчать об этом нельзя: без склейки на обоих стыках ужатого места возвращается
    # разрыв звука, а он стоит приёмнику секунд, а не миллисекунд.
    journal().mark(why, слот=slot)
    on_bare(shrunk, copy, slot, "ужатие", container, heads)
    return shrunk
