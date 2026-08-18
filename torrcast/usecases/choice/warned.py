"""Предупреждения к меню: что человек обязан прочитать до ответа."""

from __future__ import annotations

from torrcast.domain.release import Release
from torrcast.usecases.choice.configure import _environment_port


def warned(
    release: Release,
    runtime: float,
    warn_mbit: float,
    recode_at: float = 0.0,
    hard_mbit: float = 0.0,
) -> str:
    """Почему релиз не дефолт: HEVC ресивер может не потянуть, жирный битрейт — тоже.

    Словами, а не значками: ``⚠`` из вывода убран целиком — в терминале он не нёс
    смысла и разъезжался по ширине.

    ⚠️ «Не берём» про HEVC осталось правдой ровно там, где перекодирование выключено:
    иначе такой релиз играет, перекодированный целиком, и таблица обязана говорить то же,
    что и показ (:func:`_encode_all`).
    """
    peak = _environment_port().bitrate_of(release, runtime)
    marks: list[str] = []
    if release.is_hevc:
        marks += ["перекодирую целиком" if recode_at > 0 else "не берём"]
    if peak is None:  # вес неизвестен (TC-344) - пометок по весу нет, врать нечем
        return ", ".join(marks)
    if peak > warn_mbit:
        marks += ["тяжёлый"]
    elif hard_mbit > 0 and peak > hard_mbit:
        # Тяжелее прежнего потолка, но играбелен: уедет перекодированным целиком.
        if "перекодирую целиком" not in marks:
            marks += ["перекодирую целиком"]
    elif recode_at > 0 and peak > recode_at:
        # Не брак, а честное предупреждение - тяжёлые куски поедут перекодированными.
        marks += ["перекодируем"]
    return ", ".join(marks)
