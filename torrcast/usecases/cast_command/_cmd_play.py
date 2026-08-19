"""Счастливый путь показа: запрос → «какой фильм?» → «какая озвучка?» → показ.

Зовёт его :func:`torrcast.cli.play.play`, внешний мир кладёт композиционный корень.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import torrcast.usecases.cast_command._play_state as _state
from torrcast.domain.bitrate_mbit import bitrate_mbit
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.tune import tune as tune_profile
from torrcast.ports.journal import journal
from torrcast.ports.state_store import store as watch_store
from torrcast.usecases.cast_command._bookmark import _account_watched, _from_start
from torrcast.usecases.cast_command._choose import _choose
from torrcast.usecases.cast_command._entry_for import _entry_for
from torrcast.usecases.cast_command._notes import _notes
from torrcast.usecases.playback import _launch
from torrcast.usecases.rank.pick_voice import pick_voice
from torrcast.usecases.rank.quality_text import quality_text
from torrcast.usecases.say_showing import _say_showing
from torrcast.usecases.select._continue import _continue
from torrcast.usecases.select._remembered import _remembered
from torrcast.usecases.start_clock import _Clock
from torrcast.usecases.torrents import _release_orphans

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.cast_command._choose import Chosen


def _cmd_play(
    args: Args,
    *,
    restart: Callable[..., int | None] = _from_start,
    resume: Callable[..., int | None] = _continue,
    choose: Callable[..., Chosen] = _choose,
) -> int:
    """Счастливый путь: запрос → «какой фильм?» → «какая озвучка?» → показ.

    Релиз и файл выбираются сами, таблиц и списков файлов на этом пути нет. Пока человек
    отвечает на вопрос про франшизу, топ-3 кандидата уже греются в TorrServer и читаются
    ffprobe: к моменту ответа критический путь чаще всего пуст.

    ``--new`` играет сохранённую раздачу, файл и дорожку с нулевой позиции. Если записи
    нет, команда идёт обычным путём поиска.

    Три дороги отсюда - игра с начала, продолжение с места и путь до релиза - названы
    аргументами с боевым умолчанием: развилка и есть работа этой единицы, и зеркалу
    надо мерить именно её, а не то, чем каждая дорога кончается в сети и на экране.
    """
    journal().mark("команда")
    clock = _Clock()
    config = _state._play_settings()
    # Раздача показа, убитого не по-людски, - первое, что убирается: она держит рой и
    # место в TorrServer, а хозяина у неё нет. Пустое состояние это не стоит ни секунды.
    _release_orphans(config)
    # Профиль приёмника - до всего остального: от него зависят и потолки отбора, и то,
    # какой кодек считается играбельным. Спрашивать о нём человека нечего: он выбирается
    # по паспорту устройства, а незнакомому приёмнику достаётся осторожный набор.
    chosen = _state._play_detect(config)
    config = tune_profile(config, chosen.profile)
    state = watch_store().load()
    # Один телевизор - один показ. Сироты уже убраны выше, поэтому непустая отметка
    # раздачи здесь значит ровно «на экране прямо сейчас идёт наш показ».
    live = state.showing()
    _say_showing(live)
    found_entry = state.find(args.title_query)
    watched = False
    # Бухгалтерия досмотра трогает только тот путь, который сам решает, что играть дальше.
    # Названная руками серия, `--new` и ручной релиз решают это за неё, и обещать им
    # следующую серию нельзя: строка «играю s1e3» перед честным «играю s1e1» - подмена.
    named = args.episode is not None
    if found_entry is not None and not (args.from_start or args.pinned or named):
        found_entry, watched = _account_watched(state, found_entry)
    # --new поднимает сохранённый выбор лишь когда он действительно отвечает на
    # весь запрос. Явная серия сперва прыгает внутри сохранённой раздачи, а ручной
    # релиз/файл выбирается обычным путём: эти ручки нельзя выбросить молча.
    if args.from_start and found_entry is not None and not args.pinned:
        code = restart(config, *found_entry, args=args, clock=clock)
        if code is not None:
            return code
    # 🔴 Названный руками релиз весит здесь ровно столько же, сколько на втором раннем
    # выходе (:func:`_continue_picked`): человек выбирает раздачу сам, и продолжение
    # записанной на этот путь не заходит. Пока условия у двух выходов расходились, один и
    # тот же `--release N` то уважался, то пропадал молча, и решал это лишь текст запроса:
    # совпал с записью - выход был здесь, и флаг выбрасывался, не назвав себя ни строкой;
    # не совпал - картина выбиралась в меню, и тот же флаг работал.
    if found_entry is not None and not args.pinned:
        if watched and not found_entry[1].serial:
            code = restart(config, *found_entry, args=args, clock=clock)
            if code is not None:
                return code
        code = resume(config, *found_entry, args=args, clock=clock)
        if code is not None:
            return code

    picked = choose(config, args, chosen, state, live, clock)
    if isinstance(picked, int):
        return picked  # закладка выбранной картины ответила показом сама
    plans, plan, prep, bench, passport = picked
    release, video, media = prep.release, prep.want, prep.found
    audio, voice = pick_voice(media, args, _remembered(state, plan.picture.key, found_entry))
    journal().mark("ответы")  # ноль секундомера: Enter после последнего вопроса
    label = media.tracks[audio].label if audio < len(media.tracks) else "-"
    series = plan.series
    what = f"«{plan.picture.title}»" + (
        f" {series.want}" if series else f" ({plan.picture.year or '?'})"
    )
    about = f"{what} · {quality_text(release, media)} · {label}"
    journal().emit(
        "select",
        "select",
        release=prep.number,
        quality=quality_text(release, media),
        track=label,
        codec=media.video or "",
        mbit=round(bitrate_mbit(video.size, media.duration or plan.runtime), 1),
    )
    # Настоящий битрейт: размер файла серии/фильма на его же длительность, а не оценка.
    _notes(config, plans, plan, prep, media, audio, release, video, passport, args)
    if args.dry:
        # Показа не будет: «сыгранная» раздача - такой же мусор, как прогретое лишнее.
        # Убирается по СВОИМ явным хэшам, как на любом выходе без показа.
        bench.drop_all()
        # Сухой прогон - главный замер отбора, поэтому он называет, ЧТО выбрал бы:
        # имя файла внутри раздачи, а не эхо запроса. Иначе дефект «сыграла не та
        # серия» (сквозная нумерация против сезонной) всухую не виден вовсе (TC-302).
        print(f"(--dry) {about} · файл «{video.base}» - каста нет")
        return EXIT_OK
    entry = _entry_for(plan, prep, release, video, media, audio, voice, args)
    return _launch(config, plan.picture.key, entry, about, clock)
