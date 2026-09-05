"""Плагин pytest: какие тесты ДОХОДЯТ до каждого места речи.

Карту снимает быстрый набор гейта, а читает её сторож речи (:mod:`speech_guard`): без неё
он не знает, чьим прогоном мерить место, и мерил бы каждое место всем деревом.

🔴 Речь ловится событием запуска кодового объекта ``phrase`` (``sys.monitoring``), а не
подменой имени: ``phrase`` импортировано по значению в полсотни модулей, и подмена в
модуле-источнике не увидела бы НИ ОДНОГО живого вызова, отдав пустую карту за честную.

Место опознаётся по строке ВЫЗЫВАЮЩЕГО кадра: она попадает внутрь диапазона стока из
переписи, и этого хватает, чтобы развести два места в одном файле.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Final

from speech_sites import Site, fingerprint, sites

# Продукт берётся из СВОЕГО дерева, а не из того, на которое смотрит editable-установка
# венва: карта, снятая соседним клоном, подписалась бы отпечатком нашей переписи и
# развела бы места не по тем строкам.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

#: Наблюдатель за запуском кода. Взят через ``getattr``, а не именем: пакет объявлен от
#: 3.11, а ``sys.monitoring`` живёт с 3.12, и разбор типов ведётся по нижней границе.
#: Нет его - карта не снимается, и молчать об этом нельзя (см. :func:`pytest_configure`).
monitoring: Any = getattr(sys, "monitoring", None)

#: Переменная среды с каталогом, куда лечь карте. Не задана - плагин молчит и не мерит.
OUT_VAR: Final = "SPEECH_REACH_OUT"
_TOOL: Final = 3

_spans: dict[str, list[tuple[int, int, int]]] = {}
_hits: dict[int, set[str]] = {}
_current: str | None = None
_stamp: str = ""


def _remember(found: list[Site], root: Path) -> None:
    global _stamp
    _stamp = fingerprint(found)
    for index, site in enumerate(found):
        _spans.setdefault(str(root / site.path), []).append(
            (site.span.line, site.span.end_line, index)
        )


def _callback(code: Any, offset: int) -> None:
    caller = sys._getframe(1).f_back
    if caller is None:
        return
    spans = _spans.get(caller.f_code.co_filename)
    if spans is None:
        return
    line = caller.f_lineno
    for first, last, index in spans:
        if first <= line <= last:
            _hits.setdefault(index, set()).add(_current or "<импорт>")
            return


def pytest_configure(config: Any) -> None:
    if not os.environ.get(OUT_VAR):
        return
    if monitoring is None:
        raise RuntimeError(
            "карта досягаемости речи снимается наблюдателем sys.monitoring, а его нет: "
            f"нужен Python 3.12 и выше, здесь {sys.version_info.major}."
            f"{sys.version_info.minor}. Пустая карта тут хуже отказа: сторож речи принял "
            "бы её за честную и назвал бы голыми все 92 места разом."
        )
    from torrcast.domain.catalogs.phrase import phrase

    root = Path(config.rootpath)
    _remember(sites(root), root)
    events = monitoring.events
    monitoring.use_tool_id(_TOOL, "speech-reach")
    monitoring.register_callback(_TOOL, events.PY_START, _callback)
    monitoring.set_local_events(_TOOL, phrase.__code__, events.PY_START)


def pytest_runtest_protocol(item: Any) -> None:
    global _current
    _current = item.nodeid
    return None


def pytest_sessionfinish() -> None:
    out = os.environ.get(OUT_VAR)
    if not out:
        return
    from torrcast.domain.catalogs.phrase import phrase

    monitoring.set_local_events(_TOOL, phrase.__code__, 0)
    monitoring.free_tool_id(_TOOL)
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    (folder / f"{worker}.json").write_text(
        json.dumps(
            {"stamp": _stamp, "hits": {str(k): sorted(v) for k, v in _hits.items()}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
