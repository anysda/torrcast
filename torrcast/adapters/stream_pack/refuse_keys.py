"""Кладёт на полку вердикт «карты с этого файла не будет»; читает его :func:`refused_keys`."""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path
from typing import Any

from torrcast.adapters.stream_pack._keys_draft import _keys_draft
from torrcast.domain.film_keys import FilmKeys


def refuse_keys(cache: Path, refused: str, keys: FilmKeys | None = None) -> None:
    """Положить на полку вердикт «карты с этого файла не будет» - на место самой карты.

    Пишется через тот же черновик, что и карта (:func:`_keys_draft`): имя на полке одно, и
    два писателя на одно имя пишут вперемешку.

    Вердикт выносят двое, и оба - про этот самый файл: разбор индекса, когда индекс врёт
    или его нет вовсе (:func:`film_keys`), и сетка, когда снятая карта разошлась с
    пробным прогоном по живому файлу
    (:func:`~torrcast.adapters.stream_pack.grid_for.grid_for`). Второй нужен ровно потому,
    что первый судит карту двумя пробами байт, а второй - фактом: где ffmpeg встал на
    самом деле. Не запиши мы вердикт второго, следующий показ того же фильма взял бы ту
    же карту с полки и построил бы по ней ту же сетку - полка помнит карту дольше, чем
    сеанс помнит, что она соврала.

    🔴 ``keys`` - та самая отвергнутая карта, и вместе с вердиктом на полке остаётся её
    БАЙТОВЫЙ указатель. Отвергнуто в ней ровно одно утверждение - «здесь стоит опорный
    кадр»; пара «время - смещение» при этом честная, и по ней считается вес куска
    (:class:`torrcast.adapters.recode.weights.Weights`). Замер на «Матрице» 1999 (18.2 ГБ,
    индекс с точкой Cues на каждый кластер): 17 проб вразброс по всему фильму, от 1.251 до
    7778.899 с, - **на каждом обещанном смещении лежит настоящий кластер Matroska**, и его
    собственная метка времени сходится с обещанной картой в пределах кадра (0.042-0.125 с).
    Тот же индекс доводит до 18 050 079 042 байт при длине файла 18 196 642 688, то есть
    описывает 99.2 % файла.

    Без этой записи цена вердикта достаётся зрителю на ВТОРОМ показе того же фильма:
    карта уже стёрта вердиктом, сетка выходит ровной, а профиля тяжести к ней нет - и
    каждый кусок идёт ужатием на месте, посреди которого упаковка замирает
    (:func:`torrcast.adapters.recode.yield_to_shrink._yield_to_shrink`).

    ⚠️ Картой такая запись не становится: :func:`~torrcast.adapters.stream_pack.read_keys.read_keys`
    отдаёт ``None`` всему, на чём стоит вердикт, - иначе полка вернула бы отвергнутую
    карту сетке следующего показа, то есть отменила бы сам вердикт.
    """
    with contextlib.suppress(OSError):
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = _keys_draft(cache)
        body: dict[str, Any] = {"refused": refused, "when": time.time()}
        if keys is not None and keys.offset and len(keys.offset) == len(keys.at):
            body |= {
                "duration": keys.duration,
                "keys": keys.at,
                "bytes": keys.offset,
                "kind": keys.kind,
            }
        try:
            tmp.write_text(json.dumps(body), "utf-8")
            tmp.replace(cache)
        finally:
            tmp.unlink(missing_ok=True)
