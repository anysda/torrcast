"""Спрашивает один индексер под секундомером: выдача, миллисекунды и ошибка."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from torrcast.adapters.prowlarr.from_json import from_json
from torrcast.adapters.prowlarr.raw_result import RawResult
from torrcast.domain.infra_error import InfraError


def ask_indexer(
    get_json: Callable[[str, float], Any], url: str, budget: float
) -> tuple[list[RawResult] | None, int, InfraError | None]:
    """Один индексер под нашим секундомером: выдача, миллисекунды и ошибка.

    Замер ровно вокруг вызова, чтобы хвост круга (кто и сколько держал) читался из следа
    без внешнего секундомера - и для молчунов тоже, поэтому ошибка возвращается
    значением, а не вылетает мимо замера.

    Выдачи нет (``None``) - это молчание или отказ; пустой список - честный ноль, то есть
    полноценный ответ каталога.
    """
    began = time.monotonic()
    try:
        rows: list[RawResult] | None = from_json(get_json(url, budget))
        return rows, int((time.monotonic() - began) * 1000), None
    except InfraError as exc:
        return None, int((time.monotonic() - began) * 1000), exc


__all__ = ["ask_indexer"]
