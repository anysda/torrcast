"""Чистое правило swarm_alive для потокового фасада."""

from __future__ import annotations

from collections.abc import Mapping

from torrcast.domain.json_value import JsonValue


def swarm_alive(status: Mapping[str, JsonValue]) -> bool | None:
    """Есть ли у раздачи хоть один контакт по мнению самой службы. ``None`` — она молчит.

    Это тот же приём, что :func:`swarm_pulse`, только для фазы, где потока ещё нет.
    Признак жизни у :func:`swarm_pulse` - пришедший байт, и раньше метаданных взять его
    неоткуда: ``/stream`` дожидается метаданных внутри себя, то есть до них не отдаёт ни
    байта даже у самой живой раздачи. Спросить на этой фазе можно ровно одно - что служба
    сама знает про рой, - и приезжает этот ответ тем же опросом (``action=get``), которым
    берутся файлы (:meth:`TorrServer.wait_files`): ни одного лишнего запроса.

    🔴 Считается СОСТОЯВШИЙСЯ контакт, а не найденный адрес, и это замерено, а не выведено.
    У раздачи с мёртвым роем служба бодро рапортует ``total_peers`` 7-9 и столько же
    ``half_open_peers`` и держит их так минутами: это кандидаты из DHT, с которыми никто
    не поговорил. Считай мы их жизнью, отсрочка не срабатывала бы никогда. У живой
    раздачи в тот же миг стоят ``active_peers``, ``connected_seeders`` и ``bytes_read``,
    а у мёртвой этих ключей нет вовсе.

    Отсюда два разных списка слов: «нашли адрес» (total/pending/half open) жизнью не
    считается, «поговорили» (active, connected, скорости, байты) - считается.

    Раздача, про рой которой нам НЕ сказали ВООБЩЕ, обязана ждать полный бюджет ровно
    как ждала всегда - отсюда третий ответ ``None``. Отличаем это от честного нуля по
    тому, есть ли в ответе хоть один счётчик роя: служба, которая про рой рассказывает,
    просто опускает нулевые поля.
    """
    said = False
    for key, value in status.items():
        name = key.casefold()
        if not any(word in name for word in ("peers", "speed", "bytes")):
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            continue
        said = True
        if any(word in name for word in ("total", "pending", "half")):
            continue
        if value > 0:
            return True
    return False if said else None
