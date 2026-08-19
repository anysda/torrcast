#!/usr/bin/env python3
"""Разовый сбор живых данных: какие звуковые дорожки на самом деле лежат в раздачах.

Ходит тем же путём, что счастливый путь ``cast`` (поиск → отбор релиза → прогрев →
ffprobe), но вместо показа печатает список дорожек: язык, заголовок, кодек, каналы.
Нужен, чтобы эвристику дефолта озвучки писать по фактам, а не по воображению.

Состояние не трогает вовсе — ни читает, ни пишет; раздачи из TorrServer убирает за собой.

    python scripts/voicedump.py моана "моана 2" киберпанк
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 🔴 Свой корень впереди всего: без этой строки щуп брал ``torrcast`` из того дерева, на
# которое смотрит editable-установка венва, а не из того, в котором запущен. Замерено:
# с ``.pth`` на соседний клон щуп импортировал чужой пакет, а паспорт прогона (:mod:`runpass`)
# честно называл при этом коммит и отпечаток СВОЕГО дерева - то есть замер был снят одним
# кодом, а подписан другим. В параллельной волне соседний клон меняют соседи, и повторить
# такой замер нельзя вовсе.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.adapters.console.console.progress import Progress
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.domain.args import Args
from torrcast.runtime.wire import wire
from torrcast.usecases.discover.search_circle import search_circle
from torrcast.usecases.playback.file_picker import file_picker
from torrcast.usecases.select_bench.bench import Bench


def main(argv: list[str]) -> int:
    # Тракт отбора сценарию раздаёт композиционный корень: без него первый же
    # вопрос сценария внешнему миру падает на несобранной среде.
    wire()
    config = load_config()
    out: list[dict[str, object]] = []
    for query in argv:
        args = Args(query=query.split())
        try:
            with Progress() as progress:
                plans = search_circle(config, args, progress)
                torrserver = TorrServer(config.torrserver_url)
                bench = Bench(torrserver, choose=file_picker(args))
                for plan in plans[:1]:
                    prep = bench.resolve(plan, args, progress)
                    out.append(
                        {
                            "запрос": query,
                            "картина": f"{plan.picture.title} ({plan.picture.year})",
                            "релиз": prep.release.title,
                            "файл": prep.want.base,
                            "дорожки": [
                                {
                                    "i": t.index,
                                    "lang": t.language,
                                    "title": t.title,
                                    "codec": t.codec,
                                    "ch": t.channels,
                                }
                                for t in prep.found.tracks
                            ],
                        }
                    )
                bench.drop_all()
        except Exception as exc:  # это одноразовый сбор данных, падать на одном запросе незачем
            out.append({"запрос": query, "ошибка": f"{type(exc).__name__}: {exc}"})
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
