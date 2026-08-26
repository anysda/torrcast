"""Что уходит наружу от перекодированного места: склейка, копия или перекод как есть.

Зовёт это выкладка упаковщика (:mod:`torrcast.adapters.stream_pack.packer_publish`).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from torrcast.domain.mixed_name import mixed_name
from torrcast.domain.segment_container import MPEGTS, SegmentContainer
from torrcast.domain.track_place import TRACK_PLACE_MAX
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _merged_out(
    run_dir: Path,
    slot: int,
    copy: Path,
    recode: Path,
    copy_size: int,
    cap: int,
    want: float,
    container: SegmentContainer = MPEGTS,
    *,
    merge: Callable[..., bool],
    starts_of: Callable[[Path], tuple[float, float]],
) -> tuple[Path, str]:
    """Файл этого места для приёмника и одно слово о том, чем он стал.

    Наружу идёт картинка перекода со звуком копии (:func:`merge_tracks`): звук показа обязан
    остаться одним непрерывным потоком одного прогона.

    🔴 Метки картинке НЕ правятся: оба захода пакуют ленту фильма (``-copyts`` и общий
    :attr:`~.grid.Grid.origin`), а голова куска копии лентой не является. Муксер режет поток в
    порядке ДЕКОДИРОВАНИЯ по условию на время показа, и она встаёт тем раньше границы, чем
    сильнее переупорядочен кадр на ней, - от куска к куску по-разному. Заход кодировщика идёт
    одной непрерывной лентой, и подгонка по такой голове вносила в неё скачок на 1-3 кадра;
    приёмник зовёт это ``Parsed buffers not in DTS sequence`` и бросает показ (живой замер: 13
    стыков с меткой назад из 41 и 18 его перезаходов).

    🔴 TC-833. Спариваются картинка и звук по МЕСТУ фильма, а не по номеру слота. Один номер
    значит одно место, только пока оба захода режутся по границам сетки; стоит муксеру
    пропустить рез - он сдвигает НУМЕРАЦИЮ файлов, и под именем слота лежит другое место.
    Живой замер («Матрица», 26-08): 741 кусок в манифесте против 112 у упаковщика, сдвиг звука
    от картинки +123…+324 с. Уезжало это зрителю кодом ноль, потому что видео у склейки было
    правильное, а звук не сверял никто.

    ``want`` - место этого слота на ленте (``grid.start(slot) + grid.origin``), и сверяются с
    ним ОБЕ дорожки готовой склейки порознь. Порознь - потому что промахнуться вправе любая:
    тот же корпус, на котором снят порог, поймал заход КОДИРОВЩИКА, потерявший рез и уехавший
    ровно на слот (+10.417 с) при исправном звуке. По разнице дорожек между собой это выглядело
    бы виной звука, и наружу ушёл бы как раз испорченный перекод.

    Отсюда и развилка отказа: наружу идёт та половина пары, которая **сама** стоит на месте.
    Уехал звук - значит уехала копия, из которой он взят, и наружу идёт перекод. Уехала
    картинка - значит уехал перекод, и наружу идёт копия. Уехали обе - годного куска на этом
    месте нет вовсе, и это уже про недоверенную карту опорных кадров (TC-834), а не про
    склейку: наружу идёт прежний выбор, но молча он больше не идёт.

    ``want`` бывает ``nan``: сетки у прогона нет (щупы и стенды), сверять не с чем, и место не
    проверяется вовсе. На всех трёх живых путях упаковки сетка есть всегда.

    ``merge`` и ``starts_of`` приезжают доводами: оба поднимают ffmpeg и ffprobe на настоящих
    кусках, а здесь меряется РЕШЕНИЕ - что именно уедет на приёмник и как это назовут.
    """
    # Копия тут меньшее зло ровно пока влезает в потолок: перекод уехал бы со своим звуком,
    # на своей сетке AAC, а это дыра на обоих стыках куска.
    without = (copy, "копия") if copy_size and copy_size <= cap else (recode, "перекод")
    mixed = run_dir / mixed_name(slot, container)
    if not merge(recode, copy, mixed, container=container):
        return without
    picture, sound = starts_of(mixed)
    astray_picture, astray_sound = _astray(picture, want), _astray(sound, want)
    if not astray_picture and not astray_sound:
        return mixed, "склейка"
    mixed.unlink(missing_ok=True)
    journal().mark(
        _refusal(astray_picture, astray_sound),
        слот=slot,
        картинка=_miss(picture, want),
        звук=_miss(sound, want),
    )
    if astray_sound and not astray_picture:
        return recode, "перекод"
    if astray_picture and not astray_sound:
        return copy, "копия"
    return without


def _astray(mark: float, want: float) -> bool:
    """Дорожка стоит НЕ на месте своего слота; сверять не с чем - значит и промаха нет.

    Сравнение написано отрицанием намеренно: ``mark`` бывает ``nan`` - дорожки в куске не
    нашлось, - и такая дорожка обязана считаться уехавшей. Прямое ``> порога`` на ``nan``
    даёт ложь, то есть объявило бы пропавшую дорожку стоящей на месте.
    """
    return not math.isnan(want) and not abs(mark - want) <= TRACK_PLACE_MAX


def _miss(mark: float, want: float) -> float | None:
    """На сколько дорожка отошла от места слота; ``None`` - дорожки в куске не нашлось."""
    return None if math.isnan(mark) or math.isnan(want) else round(mark - want, 3)


def _refusal(astray_picture: bool, astray_sound: bool) -> str:
    """Кто именно уехал: об этом говорят разными словами, потому что лечится оно разным."""
    if astray_picture and astray_sound:
        return "склейка не с этого места целиком"
    if astray_picture:
        return "картинка склейки не с этого места"
    return "звук склейки не с этого места"
