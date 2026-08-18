#!/usr/bin/env python3
"""Снять сравнимую выдачу Prowlarr, не продолжая замер поверх его отсрочки.

Щуп спрашивает индексеры по одному, перед каждым запросом перечитывает status и
останавливается, если Prowlarr уже исключил хотя бы один источник. Поэтому строки
после первого отказа не смешиваются с выдачей урезанного каталога. Параллели нет:
один запрос щупа означает один запрос к одному индексеру.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeAlias

#: Чем щуп спрашивает Prowlarr: боевой HTTP-запрос (:func:`_json`) или ответ стенда.
Ask: TypeAlias = Callable[[str, str, str, float], Any]


def _json(base: str, key: str, path: str, timeout: float) -> Any:
    request = urllib.request.Request(
        base.rstrip("/") + path,
        headers={"X-Api-Key": key, "User-Agent": "torrcast-catalogprobe/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        return json.load(answer)


def blocked(base: str, key: str, timeout: float, ask: Ask = _json) -> dict[int, str]:
    payload = ask(base, key, "/api/v1/indexerstatus", timeout)
    if not isinstance(payload, list):
        raise ValueError("Prowlarr вернул неожиданный статус индексеров")
    return {
        int(row["indexerId"]): str(row.get("disabledTill") or "")
        for row in payload
        if isinstance(row, dict) and str(row.get("indexerId", "")).isdigit()
    }


def measure(
    base: str, key: str, query: str, timeout: float, ask: Ask = _json
) -> list[dict[str, Any]]:
    """``ask`` - чем спрашивать Prowlarr. Умолчание боевое (:func:`_json`); называет своё
    только стенд, которому нужен ответ на бумаге, а не живой каталог."""
    indexers = ask(base, key, "/api/v1/indexer", timeout)
    if not isinstance(indexers, list):
        raise ValueError("Prowlarr вернул неожиданный список индексеров")
    rows: list[dict[str, Any]] = []
    for indexer in indexers:
        if not isinstance(indexer, dict) or not indexer.get("enable"):
            continue
        banned = blocked(base, key, timeout, ask)
        if banned:
            names = ", ".join(
                str(row.get("name") or row.get("id")) for row in indexers if row.get("id") in banned
            )
            raise RuntimeError(f"замер остановлен: Prowlarr исключил источники: {names}")
        number, name = int(indexer["id"]), str(indexer.get("name") or indexer["id"])
        params = urllib.parse.urlencode(
            [
                ("apikey", key),
                ("query", query),
                ("type", "search"),
                ("limit", "100"),
                ("indexerIds", str(number)),
            ]
        )
        began = time.monotonic()
        payload = ask(base, key, "/api/v1/search?" + params, timeout)
        elapsed = round(time.monotonic() - began, 3)
        if not isinstance(payload, list):
            raise ValueError(f"{name}: Prowlarr вернул неожиданный ответ")
        rows.append({"query": query, "indexer": name, "rows": len(payload), "seconds": elapsed})
    banned = blocked(base, key, timeout, ask)
    if banned:
        raise RuntimeError("замер недействителен: источник выпал во время последнего запроса")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("query")
    parser.add_argument("--config", type=Path, default=Path("/etc/torrcast/config.json"))
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    try:
        rows = measure(config["prowlarr_url"], config["prowlarr_apikey"], args.query, args.timeout)
    except (OSError, ValueError, RuntimeError) as exc:
        print(exc)
        return 2
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
