#!/usr/bin/env python3
"""Снимает выдачу Prowlarr по именам корпуса в файл, чтобы счёт был офлайновым.

Инструмент разработчика: в устанавливаемый пакет не входит. Ходит в сеть ОДИН раз,
дальше замер повторяется по файлу и не зависит ни от источника, ни от часа суток.

    python scripts/siblingcache.py --names names.txt --out sibling_results.jsonl.gz

Пишет по строке на имя: сам запрос и ЗАГОЛОВКИ найденных раздач. Ничего, кроме
заголовков, для замера вида не нужно, и лишнего в файл не кладётся.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.domain.parse_release_name import parse_release_name

PROWLARR = "http://127.0.0.1:9696"
CATS = "".join(f"&categories={c}" for c in (2000, 5000, 6000, 8000))
CONFIG = Path("/opt/torrcast/prowlarr-data/config.xml")


def apikey() -> str:
    text = CONFIG.read_text(encoding="utf-8")
    return text.split("<ApiKey>")[1].split("</ApiKey>")[0]


def ask(query: str, key: str, limit: int) -> list[str]:
    url = (
        f"{PROWLARR}/api/v1/search?apikey={urllib.parse.quote(key)}"
        f"&query={urllib.parse.quote(query)}&type=search&limit={limit}{CATS}"
    )
    with urllib.request.urlopen(url, timeout=90) as resp:
        return [str(item.get("title", "")) for item in json.load(resp)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    key = apikey()
    names = [
        line.strip()
        for line in Path(args.names).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    done = 0
    with gzip.open(args.out, "wt", encoding="utf-8") as out:
        for raw in names:
            query = parse_release_name(raw).title or raw
            started = time.monotonic()
            try:
                titles, err = ask(query, key, args.limit), ""
            except Exception as exc:
                titles, err = [], f"{type(exc).__name__}: {exc}"
            out.write(
                json.dumps(
                    {
                        "raw": raw,
                        "query": query,
                        "titles": titles,
                        "err": err,
                        "took": round(time.monotonic() - started, 2),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            done += 1
            if done % 25 == 0:
                print(f"{done}/{len(names)}", flush=True)
    print(f"снято {done} имён в {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
