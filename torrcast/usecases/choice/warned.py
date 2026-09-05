"""Предупреждения к меню: что человек обязан прочитать до ответа."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.recodes_whole import recodes_whole
from torrcast.domain.release import Release
from torrcast.usecases.choice.configure import _environment_port


def warned(
    release: Release,
    runtime: float,
    warn_mbit: float,
    recode_at: float = 0.0,
    hard_mbit: float = 0.0,
) -> str:
    """Почему релиз не дефолт: картинку ресивер может не потянуть, жирный битрейт - тоже.

    Словами, а не значками: ``⚠`` из вывода убран целиком — в терминале он не нёс
    смысла и разъезжался по ширине.

    ⚠️ «Не берём» осталось правдой ровно там, где перекодирование выключено: иначе такой
    релиз играет, перекодированный целиком, и таблица обязана говорить то же, что и показ
    (:func:`_encode_all`).

    🔴 TC-355. Спрашивается это ОДНОЙ функцией с показом и отбором
    (:func:`torrcast.domain.recodes_whole.recodes_whole`), а не своей проверкой на HEVC рядом с
    ними. Своя проверка стояла тут и знала ровно один кодек из набора приёмника: mpeg4
    (XviD/DivX) показ берёт сплошным перекодом с тех пор, как цена его перекода замерена
    (TC-299), а таблица о том же релизе молчала - инструмент и показ говорили о нём разное.
    Имя раздачи переводится на язык профиля (:attr:`Release.named_codec`,
    :attr:`Release.named_depth`) ровно так же, как переводит его ступень отбора
    (:func:`torrcast.usecases.rank.fits_receiver.fits_receiver`).
    """
    peak = _environment_port().bitrate_of(release, runtime)
    marks: list[str] = []
    if recodes_whole(release.named_codec, release.named_depth):
        whole = phrase("choice.mark_recode_all")
        marks += [whole if recode_at > 0 else phrase("choice.mark_not_taken")]
    if peak is None:  # вес неизвестен (TC-344) - пометок по весу нет, врать нечем
        return ", ".join(marks)
    if peak > warn_mbit:
        marks += [phrase("choice.mark_heavy")]
    elif hard_mbit > 0 and peak > hard_mbit:
        # Тяжелее прежнего потолка, но играбелен: уедет перекодированным целиком.
        whole = phrase("choice.mark_recode_all")
        if whole not in marks:
            marks += [whole]
    elif recode_at > 0 and peak > recode_at:
        # Не брак, а честное предупреждение - тяжёлые куски поедут перекодированными.
        marks += [phrase("choice.mark_recode_parts")]
    return ", ".join(marks)
