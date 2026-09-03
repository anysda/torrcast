"""Ответы порций одного запроса: чем частичный отказ отличается от отказа сети."""

from __future__ import annotations

from concurrent.futures import Future

from torrcast.domain.json_value import JsonValue


def answered(tasks: list[Future[JsonValue]]) -> list[JsonValue]:
    """Ответы порций; отказала ЧАСТЬ - работаем неполной, отказали все - это отказ сети.

    🔴 Разница тут не косметическая. «Статьи не нашлось» и «Википедия не ответила» - два
    разных ответа, и проглоти заход второй, картина, попавшая на 429, осталась бы без
    постера до конца жизни склада, а выглядело бы это честным «не нашлось».
    """
    out: list[JsonValue] = []
    failed: list[BaseException] = []
    for task in tasks:
        bad = task.exception()
        if bad is None:
            out.append(task.result())
        else:
            failed.append(bad)
    if failed and not out:
        raise failed[0]
    return out
