"""Счастливый путь показа: запрос → «какой фильм?» → «какая озвучка?» → показ.

Зовёт его :func:`torrcast.cli.play.play`, внешний мир кладёт композиционный корень.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import torrcast.usecases.cast_command._play_state as _state
from torrcast.domain.bitrate_mbit import bitrate_mbit
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.for_tab import for_tab
from torrcast.domain.show_receiver import show_receiver
from torrcast.domain.track_studio import track_studio
from torrcast.domain.tune import tune as tune_profile
from torrcast.ports.journal.slot import journal
from torrcast.ports.state_store.slot import store as watch_store
from torrcast.usecases.cast_command._account_watched import _account_watched
from torrcast.usecases.cast_command._bookmark import _from_start, _kept_place
from torrcast.usecases.cast_command._card_bookmark import _card_bookmark
from torrcast.usecases.cast_command._choose import _choose
from torrcast.usecases.cast_command._default_query import _default_query
from torrcast.usecases.cast_command._entry_of import _entry_of
from torrcast.usecases.cast_command._kept_dead import _kept_dead
from torrcast.usecases.cast_command._notes import _notes
from torrcast.usecases.choice._named import _title
from torrcast.usecases.playback._launch import _launch
from torrcast.usecases.playback.head_ahead import HEAD, HeadAhead
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.rank.quality_text import quality_text
from torrcast.usecases.rank.spoken_label import _spoken_media_label
from torrcast.usecases.say_showing import _say_showing
from torrcast.usecases.select._continue import _continue
from torrcast.usecases.start_clock import _Clock
from torrcast.usecases.torrent_claims import CLAIMS
from torrcast.usecases.torrents import _release_orphans

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.entry import Entry
    from torrcast.usecases.cast_command._choose import Chosen


def _cmd_play(
    args: Args,
    *,
    restart: Callable[..., int | None] = _from_start,
    resume: Callable[..., int | None] = _continue,
    choose: Callable[..., Chosen] = _choose,
    card: Callable[..., int | None] = _card_bookmark,
    head: HeadAhead = HEAD,
) -> int:
    """Счастливый путь: запрос → «какой фильм?» → «какая озвучка?» → показ.

    Релиз и файл выбираются сами; топ-3 кандидата уже греются в TorrServer и читаются ffprobe,
    пока человек отвечает на вопрос про франшизу - к ответу путь чаще всего уже пуст.

    ``--new`` играет сохранённую раздачу с нулевой позиции; нет записи - обычный поиск.

    Три дороги отсюда - игра с начала, продолжение с места и путь до релиза - названы
    аргументами с боевым умолчанием: развилка и есть работа этой единицы, и зеркалу
    надо мерить именно её, а не то, чем каждая дорога кончается в сети и на экране."""
    journal().mark("команда")
    clock = _Clock()
    config = _state._play_settings()
    # Раздача показа, убитого не по-людски, - первое, что убирается: она держит рой и
    # место в TorrServer, а хозяина у неё нет. Раздачи закладок ждут конца подъёма (cli.play).
    _release_orphans(config)
    # Профиль приёмника - до всего остального: от него зависят и потолки отбора, и то,
    # какой кодек считается играбельным. Спрашивать о нём человека нечего: он выбирается
    # по паспорту устройства, а незнакомому приёмнику достаётся осторожный набор.
    # 🔴 И до ``here``: вкладка играет тот же поток, что и ТВ (иначе «На ТВ» - куски до 110 с).
    # Вкладка, сказавшая о себе ``--tab``, получает замеренные пороги, только если она их
    # заслужила (:func:`torrcast.domain.for_tab.for_tab`); иначе - выбор ``dev``.
    # Страница просит показ себе - настройка машины остаётся прежней, играет только ЭТОТ запуск;
    # без ``here`` - телевизор, даже у машины с приёмником-вкладкой (TC-1370).
    launch = show_receiver(config, args.here)
    chosen = for_tab(_state._play_detect(config if args.here else launch), config, args.tab)
    config = tune_profile(launch, chosen.profile)
    state = watch_store().load()
    if not args.query:
        args.query = [_default_query(state)]
    # Один телевизор - один показ. Сироты уже убраны выше, отметка раздачи значит «идёт наш показ».
    live = state.showing()
    _say_showing(live, origin=_state._play_origin)
    found_entry = state.find(args.title_query)
    watched = False
    # Бухгалтерия досмотра трогает только тот путь, который сам решает, что играть дальше.
    # Названная руками серия, `--new` и дверь меню решают это за неё, и обещать им
    # следующую серию нельзя: строка «играю s1e3» перед честным «играю s1e1» - подмена.
    named = args.episode is not None
    # Ручки, которыми зритель называет картину сам, старше закладки: `--menu` и `--pick N`
    # просят меню, а сохранённое место отвечает на «где я остановился» (TC-773).
    own_choice = args.pinned or args.from_menu
    if found_entry is not None and not (args.from_start or own_choice or named):
        found_entry, watched = _account_watched(state, found_entry)
    resumed: Entry | None = None
    if found_entry is not None and args.pinned and not args.from_start:
        # 🔴 TC-807. «Возьми другую раздачу» у начатого сериала - про раздачу, а не про
        # место в нём: серия закладки встаёт в запрос, и её видят поиск, отбор и подпись,
        # а позиция ниже доезжает до записи показа. С начала сериал играет только --new.
        kept = _kept_place(state, found_entry, args)
        if kept is not None:
            found_entry, args, resumed = kept
    # --new поднимает сохранённый выбор лишь когда он действительно отвечает на
    # весь запрос. Явная серия сперва прыгает внутри сохранённой раздачи, а ручной
    # релиз/файл выбирается обычным путём: эти ручки нельзя выбросить молча.
    if args.from_start and found_entry is not None and not own_choice:
        code = restart(config, *found_entry, args=args, clock=clock)
        if code is not None:
            return code
    # 🔴 Названный руками релиз весит здесь ровно столько же, сколько на втором раннем
    # выходе (:func:`_continue_picked`): человек выбирает раздачу сам, и продолжение
    # записанной на этот путь не заходит. Пока условия у двух выходов расходились, один и
    # тот же `--release N` то уважался, то пропадал молча, и решал это лишь текст запроса:
    # совпал с записью - выход был здесь, и флаг выбрасывался, не назвав себя ни строкой;
    # не совпал - картина выбиралась в меню, и тот же флаг работал.
    if found_entry is not None and not own_choice:
        if watched and not found_entry[1].serial:
            code = restart(config, *found_entry, args=args, clock=clock)
            if code is not None:
                return code
        code = resume(config, *found_entry, args=args, clock=clock)
        if code is not None:
            return code
        if args.dead_hash and resumed is None:
            # Записанная раздача не играется, и продолжение само ушло в поиск. Серия
            # начатого сериала встаёт при этом в запрос тем же приёмом, что и при ручном
            # выборе релиза (TC-807): без неё поиск взял бы сезон с первой серии.
            kept = _kept_place(state, found_entry, args)
            if kept is not None:
                found_entry, args, resumed = kept

    # The card's key finds its bookmark with no circle: the recorded release plays, and the
    # search stays the fallback for a missing or dead one (:func:`_card_bookmark`).
    code = card(config, state, args, clock=clock)
    if code is not None:
        return code
    picked = choose(config, args, chosen, state, live, clock)
    if isinstance(picked, int):
        return picked  # закладка выбранной картины ответила показом сама
    plans, plan, prep, bench, passport = picked
    # Взятую раздачу держит отбор, пока показ её не поднял: уборка страницы её не снесёт.
    with CLAIMS.kept(prep.torrent_hash, bench):
        release, video, media = prep.release, prep.want, prep.found
        sound = prep.voiced
        entry, audio = _entry_of(state, found_entry, plan, prep, args)
        journal().mark("ответы")  # ноль секундомера: Enter после последнего вопроса
        label = _spoken_media_label(sound, audio, native=plan.picture.native)
        if prep.apart and prep.voice_file is not None:
            print(phrase("cmd_play.voice_apart", base=prep.voice_file.base))
        # Чья это озвучка - в подписи дорожки бывает не написано: пак подписывает дорожки
        # голым «rus», а студию зовёт своим именем. Строка запуска говорит, ЧТО играет (TC-701).
        studio = track_studio(sound, audio, release.studios)
        if studio is not None and studio.name.casefold() not in label.casefold():
            label = f"{label} ({studio.name})"
        if resumed is None:
            # Фильм, чья записанная раздача не играется: место у него одно на всю картину, и
            # спрашивается оно по ключу выбранной картины - закладка, ответившая после меню,
            # до найденной по запросу записи не доходит вовсе (:func:`_kept_dead`).
            resumed = _kept_dead(state, plan.picture.key, args)
        if resumed is not None and resumed.resumable and (not entry.dur or resumed.pos < entry.dur):
            # Позиция - от серии, а не от файла: другая раздача той же серии продолжается с
            # того же места (TC-807). Позиция за концом файла новой раздачи - не место,
            # а его отсутствие: такая серия играется с начала.
            entry.pos = resumed.pos
        # Подпись серии - у того файла, который реально играет (TC-807), а не у запроса:
        # запрос мог звать «s1e1» серию, которая в этой раздаче - s5e1.
        shown = f" {entry.label}" if entry.label else ""
        if not plan.series and not shown:
            shown = f" ({plan.picture.year or '?'})"
        what = f"{phrase('choice.quoted', it=_title(plan.picture))}{shown}"
        about = f"{what} · {quality_text(release, media)} · {label}"
        if entry.pos > 0:
            about = f"{about}{phrase('cmd_play.resumed_from', pos=_hms(entry.pos))}"
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
            # Показа не будет: «сыгранная» раздача - мусор, убираемый по СВОИМ явным хэшам.
            bench.drop_all()
            # Сухой прогон называет, ЧТО выбрал бы: имя файла, а не эхо запроса. Иначе
            # «сыграла не та серия» (сквозная нумерация против сезонной) не видна (TC-302).
            print(phrase("cmd_play.dry_no_cast", about=about, base=video.base))
            return EXIT_OK
        # Тяжёлая голова кодируется, пока поднимается юнит: он возьмёт её с полки.
        head.want(config, chosen.profile, _state._play_engines(config.torrserver_url), entry)
        return _launch(config, plan.picture.key, entry, about, clock, here=args.here, tab=args.tab)
