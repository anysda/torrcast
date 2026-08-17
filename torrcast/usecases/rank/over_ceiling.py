"""Потолок битрейта отбора; зовут ворота отбора и счёт отсева."""

from __future__ import annotations

from torrcast.domain.recode_settings import RECODE_HEIGHT
from torrcast.domain.release import Release
from torrcast.usecases.rank.bitrate_of import bitrate_of


def over_ceiling(
    release: Release, runtime: float, warn_mbit: float, hard_mbit: float = 0.0
) -> bool:
    """Битрейт релиза выше потолка отбора: играть его нечем, и в очередь он не идёт.

    Потолок у кадра выше 1080p свой (``hard_mbit``): запас скорости у ужатого 4К вдвое
    тоньше, а из роя тянуть надо вес исходника — см. :func:`is_candidate`.

    Отдельной функцией это стоит затем, что решение «выкинуть по битрейту» обязано
    называться одним и тем же кодом и в воротах, и в счёте отсева (:func:`drop_reason`):
    иначе счёт объяснял бы отказ не тем, чем он случился.
    """
    ceiling = warn_mbit
    if hard_mbit > 0 and release.height > RECODE_HEIGHT:
        ceiling = min(warn_mbit, hard_mbit)
    mbit = bitrate_of(release, runtime)
    # Вес неизвестен (TC-344) - потолок молчит: выкидывать по весу, которого нет,
    # нельзя, а тяжесть файла рассудит ffprobe уже после выбора (:meth:`_Bench._trouble`).
    return mbit is not None and mbit > ceiling
