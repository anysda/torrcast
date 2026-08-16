"""Отладочная ручка ``cast voices <запрос>``: какие озвучки есть у релиза для ТВ.
Зовёт её :func:`torrcast.commands.main`, показ отсюда не начинается.
"""

# ruff: noqa: F821, F822

from __future__ import annotations

__all__ = [
    "EXIT_OK",
    "Args",
    "NotFoundError",
    "Progress",
    "State",
    "TorrServer",
    "_cmd_voices",
    "load_config",
    "native_picture",
]

from torrcast.domain.exit_codes import EXIT_OK
from torrcast.ports.module import module

for _module_name, _names in {
    "torrcast": ("NotFoundError",),
    "torrcast.console": ("Progress",),
    "torrcast.state": ("State", "load_config"),
    "torrcast.stream": ("TorrServer",),
    "torrcast.voice_origin": ("native_picture",),
}.items():
    _dependency = module(_module_name)
    globals().update({name: getattr(_dependency, name) for name in _names})


def _cmd_voices(args: Args) -> int:
    """``cast voices <запрос>`` — какие озвучки есть у релиза, который поедет на ТВ.

    Отладочная ручка того же рода, что ``cast releases``: на счастливом пути озвучка
    выбирается сама, а посмотреть, из чего она выбрана, — сюда. Играть конкретную:
    ``cast <запрос> --voice N``.

    Показ отсюда не начинается и состояние не пишется; прогретые раздачи убираются из
    TorrServer, как и на всяком пути мимо показа (:meth:`_Bench.drop_all`).
    """
    config = load_config()
    inner = Args(query=list(args.query[1:]), release=args.release, pick=args.pick, file=args.file)
    if not inner.query:
        raise NotFoundError("что искать? cast voices <запрос>")
    with Progress() as progress:
        plans = _search(config, inner, progress)
        bench = _Bench(TorrServer(config.torrserver_url), choose=_file_picker(inner))
        try:
            plan = _pick_plan(plans, pick=inner.pick, asked=inner.title_query)
            native_picture(plan.picture, inner.title_query)
            prep = bench.resolve(plan, inner, progress)
        finally:
            bench.drop_all()
    media = prep.found
    remembered = _remembered(State.load(), plan.picture.key, None)
    print()
    print(f"{_named(plan.picture)} - релиз {prep.number}: {_cut(prep.release.title, 60)}")
    print(voices_table(media, media.default_track(), remembered))
    print()
    print("играть конкретную: cast <запрос> --voice N   (выбор запомнится на эту картину)")
    return EXIT_OK
