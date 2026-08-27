"""Байтовый указатель файла с полки: карта в том объёме, в каком по ней считают ВЕС."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

from torrcast.domain.film_keys import FilmKeys


def weigh_keys(cache: Path) -> FilmKeys | None:
    """Карта с полки для ВЕСА куска, включая ту, что отвергнута как сетка; иначе ``None``.

    🔴 Отличается от :func:`~torrcast.adapters.stream_pack.read_keys.read_keys` ровно одним и
    ровно нарочно: читает и запись с вердиктом
    (:func:`~torrcast.adapters.stream_pack.refuse_keys.refuse_keys`). Вердикт отвергает у карты
    одно утверждение - «здесь стоит опорный кадр», - и режет по такой карте нечем. Но вес
    куска стоит не на кадрах, а на паре «время - смещение», а она честная: это позиции
    кластеров контейнера, проверенные живым чтением файла. Поэтому вопрос «где резать» и
    вопрос «сколько это весит» задаются полке РАЗНЫМИ читателями, и смешивать их нельзя:
    один читатель на обоих либо вернул бы отвергнутую карту сетке, либо оставил бы ровную
    сетку без профиля тяжести.

    Смещений в записи нет (карта прошлой версии) - веса по ней не построить, и ``None``
    честнее выдумки: :meth:`torrcast.adapters.recode.weights.Weights.of` откажет по ней всё
    равно, но откажет молча.

    ⚠️ Номер правил (:data:`~torrcast.domain.warm_open.KEYS_RULES`) тут не спрашивается, и это
    не пропуск. Правила судят разбор ОПОРНЫХ КАДРОВ - того самого утверждения, которое для
    веса и не нужно; смещения кластеров от их смены не меняются. Карту, снятую прежними
    правилами, показ и так перечитает (:func:`~torrcast.adapters.stream_pack.read_keys.read_keys`),
    и сюда дойдёт только та запись, у которой другого ответа нет вовсе.
    """
    with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
        saved = json.loads(cache.read_text("utf-8"))
        at = [float(x) for x in saved["keys"]]
        offset = [int(x) for x in saved["bytes"]]
        if not offset or len(offset) != len(at):
            return None
        return FilmKeys(float(saved["duration"]), at, offset, str(saved.get("kind", "")))
    return None
