#!/usr/bin/env python3
"""Compare redirected names with and without hatnotes on live Wikipedia extracts.

Run from the repository root: .venv/bin/python scripts/hatnoteprobe.py snapshot.json
Add --live to refresh the named sample from Wikipedia and overwrite that snapshot.
Exit 1 means a changed verdict or an unrecognized pointer. The gate never uses the network.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.domain.facts.redirected_name import redirected_name
from torrcast.domain.facts.unhatted import unhatted
from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue


def _api(**query: str | int) -> dict[str, JsonValue]:
    url = "https://ru.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "format": "json", "formatversion": 2, **query}
    )
    request = urllib.request.Request(url, headers={"User-Agent": "torrcast-probe/1.0"})
    with urllib.request.urlopen(request, timeout=90) as reply:
        return json_map(json.load(reply))


def _collect(pages: list[JsonValue]) -> list[JsonValue]:
    """Refresh the named sample, including real Cyrillic redirects, without searching."""
    titles = [str(json_map(page)["title"]) for page in pages]
    fresh: list[JsonValue] = []
    for start in range(0, len(titles), 20):
        reply = _api(
            prop="extracts|redirects|pageprops",
            explaintext=1,
            exintro=1,
            rdlimit=500,
            rdnamespace=0,
            titles="|".join(titles[start : start + 20]),
        )
        if "continue" in reply:
            raise RuntimeError("API reply is incomplete; paginate before reporting a count")
        fresh.extend(json_rows(json_map(reply.get("query")).get("pages")))
    return fresh


def _raw(text: str) -> str:
    """Reproduce the historical reader before it started stripping hatnotes."""
    return text


def _measure(pages: list[JsonValue]) -> int:
    count = changed = hats = unknown = 0
    lengths: list[int] = []
    for value in pages:
        page = json_map(value)
        aliases = [
            str(json_map(row)["title"])
            for row in json_rows(page.get("redirects"))
            if re.search("[а-яё]", str(json_map(row)["title"]), re.IGNORECASE)
        ]
        if not aliases or "disambiguation" in json_map(page.get("pageprops")):
            continue
        title, raw = str(page["title"]), str(page.get("extract") or "")
        name, clean = aliases[0], unhatted(raw)
        with patch("torrcast.domain.facts.redirected_name.unhatted", _raw):
            before = redirected_name([name], {name: title}, {title: page}, name)
            after = redirected_name(
                [name], {name: title}, {title: {**page, "extract": clean}}, name
            )
        count += 1
        changed += before != after
        # Inventory the actual leading lines independently of the production regexes.
        lines = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            if not re.match(
                r"(Не путать|Не следует путать|У этого|У этой|У этих|Другие .*названием"
                r"|О .*см\.|Об .*см\.|Запрос|В Википедии|Эта статья|Эта страница)",
                line,
            ):
                break
            lines.append(line)
        hats += bool(lines)
        lengths.extend(map(len, lines))
        unknown += sum(line in clean for line in lines)
        print(f"{name} -> {title}: {before.title!r} / {after.title!r}; шляпок {len(lines)}")
        for line in lines:
            print(f"  {line}")
    print(f"Статей: {count}; со шляпкой: {hats}; расхождений: {changed}")
    print(
        f"Длины строк: {dict(sorted(Counter(lengths).items()))}; "
        f"максимум: {max(lengths, default=0)}"
    )
    print(f"Не снято строк шляпок: {unknown}")
    if not hats:
        raise RuntimeError("Empty hatnote sample is not evidence")
    return int(bool(changed or unknown))


if __name__ == "__main__":
    snapshot = Path(sys.argv[1])
    corpus = json_rows(json.loads(snapshot.read_text()))
    if "--live" in sys.argv[2:]:
        corpus = _collect(corpus)
        snapshot.write_text(json.dumps(corpus, ensure_ascii=True, indent=2) + "\n")
    raise SystemExit(_measure(corpus))
