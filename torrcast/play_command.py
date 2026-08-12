"""Часть CLI; публичный фасад — :mod:`torrcast.cli`."""

from __future__ import annotations

__all__ = [
    "EXIT_OK",
    "TYPE_CHECKING",
    "Entry",
    "Facts",
    "Picture",
    "Progress",
    "Prowlarr",
    "RawResult",
    "State",
    "TorrServer",
    "_cmd_play",
    "_forget_progress",
    "_relayout",
    "_season_asked",
    "_titled_number",
    "bitrate_mbit",
    "detect_profile",
    "load_config",
    "mark",
    "merge",
    "slugify",
    "split_franchise_index",
    "to_releases",
    "trace",
    "tune_profile",
]

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.choice import (
        _is_default,
        _passport,
        _pick_plan,
        _played,
        namesake_note,
        swap_note,
        warm_order,
        year_note,
    )
    from torrcast.commands import PREWARM, Args, _Clock, _release_orphans, _say_showing
    from torrcast.discovery import _ask, _no_budget, _search
    from torrcast.playback import _file_picker, _launch
    from torrcast.ranking import _gb, _hms, pick_voice, quality_text, sound_note, voice_note
    from torrcast.reinforce import _timed, _topup
    from torrcast.selection import _Bench, _continue, _remembered


from torrcast import (
    trace,
)
from torrcast.commands import EXIT_OK
from torrcast.console import Progress
from torrcast.facts import (
    Facts,
)
from torrcast.parse import (
    Picture,
    slugify,
    split_franchise_index,
)
from torrcast.profile import detect as detect_profile
from torrcast.profile import tune as tune_profile
from torrcast.search import (
    Prowlarr,
    RawResult,
    merge,
    to_releases,
)
from torrcast.state import Entry, State, load_config
from torrcast.stream import (
    TorrServer,
    bitrate_mbit,
)
from torrcast.timing import mark


def _cmd_play(args: Args) -> int:
    """Счастливый путь: запрос → «какой фильм?» → «какая озвучка?» → показ.

    Релиз и файл выбираются сами, таблиц и списков файлов на этом пути нет. Пока человек
    отвечает на вопрос про франшизу, топ-3 кандидата уже греются в TorrServer и читаются
    ffprobe: к моменту ответа критический путь чаще всего пуст.

    ``--new`` здесь ничего не стирает: сохранённая позиция уходит в расход только тогда,
    когда показ уже точно начинается (:func:`_forget_progress`). Почему так — там же.
    """
    mark("команда")
    clock = _Clock()
    config = load_config()
    # Раздача показа, убитого не по-людски, - первое, что убирается: она держит рой и
    # место в TorrServer, а хозяина у неё нет. Пустое состояние это не стоит ни секунды.
    _release_orphans(config)
    # Профиль приёмника - до всего остального: от него зависят и потолки отбора, и то,
    # какой кодек считается играбельным. Спрашивать о нём человека нечего: он выбирается
    # по паспорту устройства, а незнакомому приёмнику достаётся осторожный набор.
    chosen = detect_profile(config)
    config = tune_profile(config, chosen.profile)
    state = State.load()
    # Один телевизор - один показ. Сироты уже убраны выше, поэтому непустая отметка
    # раздачи здесь значит ровно «на экране прямо сейчас идёт наш показ».
    live = state.showing()
    _say_showing(live)
    found_entry = state.find(args.title_query)
    # --new: прежний прогресс не продолжаем и выбираем заново, но запись пока цела.
    stale = found_entry[0] if found_entry is not None and args.new else None
    if found_entry is not None and not args.new:
        code = _continue(config, *found_entry, args=args, clock=clock)
        if code is not None:
            return code

    with Progress() as progress:
        plans = _search(config, args, progress, chosen.profile)
        # Справка к меню (рейтинг, хронометраж, о чём кино) едет фоном - ровно в те
        # секунды, что уходят на подъём прогрева. Меню её не ждёт: см. torrcast.facts.
        facts = Facts([(p.picture.title, p.picture.year) for p in plans])
        facts.start()
        # 🔴 TC-199/TC-200. Год картины, которая встанет дефолтом, сверяется со справкой -
        # так же, как добор сверяет свой (:func:`year_note`). Справку зовём вслепую и фоном,
        # ровно в те секунды, что уходят на меню и прогрев: путь до меню её не ждёт, а к
        # последней строке перед стартом паспорт уже приехал. Год выдачи ей НЕ сообщаем -
        # иначе подстроится под подмену и сверять станет нечего.
        passport = _passport(plans)
        torrserver = TorrServer(config.torrserver_url)
        bench = _Bench(torrserver, choose=_file_picker(args), profile=chosen.profile)
        # Прогрев под меню: пока идёт вопрос, раздачи уже качают метаданные. Греется
        # голова ОЧЕРЕДИ, а не верх ранжира: верх мог не пройти ворота (TC-432), и
        # греть то, что отбор не возьмёт, - тянуть чужой вес из роя зря.
        order = warm_order(plans)
        # 🔴 Пока на экране идёт наш показ, прогрев под меню не поднимается вовсе: он
        # тянет из роя чужие раздачи, пишет их на тот же диск и читает ту же сеть, а
        # показ первичен. Человек ещё не выбрал картину, и платить за его раздумья
        # обязаны мы скоростью своего меню, а не зритель - картинкой.
        prewarm = [] if live is not None else order[:PREWARM]
        for plan in prewarm:
            # Номер, названный руками, у каждой картины меню свой, и у части их столько
            # раздач не наберётся: спрос с той, которую человек выберет, - за отбором.
            if args.release is not None and not 1 <= args.release <= len(plan.ranked):
                continue
            if queue := plan.candidates(args):
                bench.start(plan, queue[0])
        # ...и запасной релиз той картины, в которую попадёт Enter: брак верха не должен
        # стоить человеку подъёма второй раздачи с нуля (:data:`PREWARM_SPARE`).
        if live is None:
            bench.spare(order[0], args)
        mark("прогрев пущен", придержан=live is not None)  # TC-108: замер
        try:
            try:
                plan = _pick_plan(plans, facts, pick=args.pick, asked=args.title_query)
                mark("картина выбрана")  # TC-108: замер
                # Опоздавший индексер: круг ушёл по кворуму, и его выдача доехала, пока
                # человек читал меню. Доливаем ЗДЕСЬ - список уже прочитан и отвечен,
                # менять под курсором нечего (:func:`_topup`). Ключи меню ему нужны,
                # чтобы отличить картину, которой в списке не было (о ней - честная
                # строка), от соседней по меню (о ней говорить «её не было» - соврать).
                plan = bench.reorder(
                    plan,
                    _topup(
                        plan,
                        args,
                        config,
                        chosen.profile,
                        progress,
                        menu=frozenset(p.picture.key for p in plans),
                    ),
                )
                # Справка уже дождана меню - её хронометраж встаёт в знаменатель
                # битрейта вместо прикидки (:func:`_timed`), и порядок отбора
                # пересобирается на настоящих числах. Прогретое при этом не пропадает:
                # номера релизов переезжают вместе с порядком (:meth:`_Bench.reorder`).
                plan = bench.reorder(plan, _timed(plan, facts, args, config, chosen.profile))
                # Прогретые кандидаты ДРУГИХ картин с этой секунды - мусор: они тянут
                # куски у той раздачи, которую сейчас будем показывать, и всё это время
                # стоят в TorrServer лишними (:meth:`_Bench.keep_plan`).
                bench.keep_plan(plan)
            finally:
                # Меню уже на экране, и ответ на него получен: пусть фоновый добор допишет
                # кэш - СЛЕДУЮЩЕЕ меню этой франшизы будет полным. Ко времени до меню это
                # отношения не имеет, а к моменту ответа поток обычно давно закончил.
                facts.finish()
            plan, prep = _played(bench, plans, plan, args, progress, facts, config, chosen.profile)
            mark("отбор релиза", релиз=prep.number)  # TC-108: замер
        except BaseException:  # Ctrl-C, «картин много, а терминала нет», «годного нет»
            bench.drop_all()  # прогретое без показа - мусор в рое и кэш в чужой RAM
            raise
        bench.keep_only(prep)  # прогрев греет лишнее - до показа лишнее убираем

    release, video, media = prep.release, prep.want, prep.found
    audio, voice = pick_voice(media, args, _remembered(state, plan.picture.key, found_entry))
    mark("ответы")  # ноль секундомера: Enter после последнего вопроса
    label = media.tracks[audio].label if audio < len(media.tracks) else "-"
    series = plan.series
    what = f"«{plan.picture.title}»" + (
        f" {series.want}" if series else f" ({plan.picture.year or '?'})"
    )
    about = f"{what} · {quality_text(release, media)} · {label}"
    trace.emit(
        "select",
        "select",
        release=prep.number,
        quality=quality_text(release, media),
        track=label,
        codec=media.video or "",
        mbit=round(bitrate_mbit(video.size, media.duration or plan.runtime), 1),
    )
    # Настоящий битрейт: размер файла серии/фильма на его же длительность, а не оценка.
    peak = bitrate_mbit(video.size, media.duration or plan.runtime)
    if peak > config.bitrate_warn_mbit:
        print(
            f"внимание: ~{peak:.0f} Мбит/с - тяжёлые куски перекодирую на ходу"
            if config.recode
            else f"внимание: ~{peak:.0f} Мбит/с - ресивер на таком битрейте может встать"
        )
    # Молчаливого японского не бывает: перевода в файле нет - человек слышит об этом
    # строкой, а не на слух через минуту показа.
    playable = [plan.ranked[number - 1] for number in plan.candidates(args)]
    if note := sound_note(
        media,
        audio,
        playable,
        release,
        prep.files,
        native=plan.picture.native,
    ):
        print(note)
    # Русских дорожек было несколько - говорим, сколько и что взяли: подпись дорожки
    # отвечает «что играет», а эта строка - «почему это, а не соседняя».
    if note := voice_note(media, audio):
        print(note)
    if args.pinned:  # отладочный путь: тут внутренности показывать и надо
        print(f"файл: {video.base} · {_gb(video.size)} · {_hms(media.duration)} · {media.video}")
    # 🔴 TC-198. Последняя строка перед стартом: взяли не то, что назвали вслух. Место
    # выбрано не для порядка - фазы поиска к этой секунде уехали вверх экрана, а решение
    # про КАРТИНУ человек должен унести с собой. Человек выбрал пункт меню сам - подмены
    # нет и строки нет (:func:`default_note`).
    if note := swap_note(plans, plan, args.title_query):
        print(note)
    # 🔴 TC-199/TC-200. Год дефолтной картины против независимого слова справки: имя
    # раздачи врёт («Оно» 2014, «Медведь» 2026), а год у дефолта не сверялся нигде.
    if _is_default(plans, plan) and (note := year_note(plan, passport.get(), args.title_query)):
        print(note)
    # 🔴 TC-371. Двусмысленность самих источников: под одним именем и годом картин две,
    # и развести их отбору нечем - значит человек читает об этом строкой.
    if note := namesake_note(plan, passport.get()):
        print(note)
    if args.dry:
        # Показа не будет: «сыгранная» раздача - такой же мусор, как прогретое лишнее.
        # Убирается по СВОИМ явным хэшам, как на любом выходе без показа.
        bench.drop_all()
        # Сухой прогон - главный замер отбора, поэтому он называет, ЧТО выбрал бы:
        # имя файла внутри раздачи, а не эхо запроса. Иначе дефект «сыграла не та
        # серия» (сквозная нумерация против сезонной) всухую не виден вовсе (TC-302).
        print(f"(--dry) {about} · файл «{video.base}» - каста нет")
        return EXIT_OK
    entry = Entry(
        title=plan.picture.title,
        magnet=release.magnet,
        kind="tv" if plan.picture.kind == "tv" else "movie",
        file_idx=video.index,
        audio=audio,
        voice=voice,
        dur=media.duration,
        # Вес видеодорожки из паспорта: по нему показ строит профиль тяжести с первой
        # секунды, не набирая поправку «контейнер → ТВ» вслепую.
        vbps=media.video_bps / 1e6 or -1.0,
        # Кодек оттуда же: по нему показ решает, играть копией или перекодировать файл
        # целиком, и решает это один раз - до первого сегмента (:func:`_encode_all`).
        codec=media.video or "",
        # И глубина цвета рядом: одного имени кодека для этого решения не хватает.
        depth=media.depth,
        # То, что уехало на ТВ: `cast status` покажет факт, а не заявку имени.
        quality=media.quality if media.height else "",
        # Тот же кадр числом: по нему показ решает, до чего ужать картинку перекодом.
        frame=media.frame,
        # И HDR оттуда же: ужатому кадру ещё решать, приводить ли цвет к SDR.
        hdr=media.hdr,
        query=slugify(args.title_query),
        season=series.want.season if series else None,
        episode=series.want.episode if series else None,
        episodes=series.table if series else [],
    )
    if stale is not None:  # точка невозврата пройдена - вот теперь --new вправе забывать
        _forget_progress(stale)
    return _launch(config, plan.picture.key, entry, about, clock)


def _forget_progress(key: str) -> None:
    """Забыть прежний прогресс по ``--new`` — в момент, когда показ уже точно начинается.

    Раньше запись стиралась первым же действием команды, до единого вопроса. Любой обрыв
    после этого — «ничего не разобралось», Ctrl-C, упавший ffprobe, а на прогоне без
    терминала ещё и выбор вслепую — оставлял пользователя без сохранённого места, и взять
    его было неоткуда: state уже перезаписан (ровно так и терялась запись фильма).

    Раннее стирание при этом ничего не давало: свежую запись с нулевой позицией всё равно
    кладёт :func:`_launch`. То есть у него была одна цена и ни одной пользы.
    """
    state = State.load()  # перечитываем: рядом мог писать другой ход
    state.drop(key)
    state.save()


def _relayout(
    client: Prowlarr, query: str, name: str, index: int | None, progress: Progress
) -> tuple[str, str, int | None, list[RawResult]]:
    """Второй заход той же строкой, прочитанной как забытая раскладка. Пусто - как было.

    `cast nfxrb` - это «тачки»: запрос, набранный не переключив раскладку. Отказ по
    такой строке правдив для ``nfxrb``, но не для картины, которая есть в каталоге.

    Зовётся ровно на пустой выдаче, и это принципиально: у латинской строки всегда есть
    кириллический двойник, и звать перевод раньше значило бы искать «сфкы» вместо
    «cars». Пустая выдача - единственный случай, когда терять нечего, и стоит он один
    заход к индексерам там, где иначе человек уже читал бы отказ.

    Номер части перечитывается заново (:func:`~torrcast.parse.split_franchise_index`):
    «nfxrb 2» - это «тачки 2», и цифра в новой строке обязана снова стать номером, а не
    остаться в имени. Подмена не молчаливая: строка про раскладку печатается до меню -
    человек видит, ЧТО именно за него прочитали.
    """
    from torrcast.parse import unswap_layout

    swapped = unswap_layout(query)
    if swapped == query.casefold():
        return query, name, index, []
    fixed, moved = split_franchise_index(swapped)
    progress.phase(f"поиск «{fixed}»")
    raw = _ask(client, fixed, progress)
    if not raw:
        return query, name, index, []
    progress.note(f"«{query}» - это «{swapped}» в русской раскладке")
    return swapped, fixed, moved, raw


def _titled_number(
    client: Prowlarr, query: str, name: str, raw: list[RawResult], progress: Progress
) -> tuple[list[RawResult], list[Picture], list[Picture]]:
    """Второй заход ВСЕЙ строкой: цифра оказалась частью названия. Не помогло - как было.

    🔴 TC-296. `cast «бен 10»` уезжал искать «Бен-Гур». Хвостовая цифра читается номером
    части франшизы (:func:`~torrcast.parse.split_franchise_index`), и в индексеры уходил
    обрубок «бен» - строка, по которой каталог отдаёт «Бена» 1972 года и три десятка
    однофамильцев, а семи картин «Бен 10» не отдаёт ВООБЩЕ НИ ОДНОЙ. Дальше всё честно
    работало по чужой выдаче: тощий пул звал добор, справка по «бену» приводила
    ``Ben-Hur``, и человек читал «картин во франшизе 1, номера 10 нет» при живом сериале,
    который лежит в том же каталоге. Замер той же строкой без обрезки: 88 строк, семь
    картин линейки «Бен 10».

    Отличить номер части от цифры в названии ДО первого круга нечем: «тачки 2» и «бен 10»
    - одна и та же строка с точностью до слов. Зато после круга каталог уже ответил, и
    ответ этот однозначный: картины с таким номером в найденной франшизе НЕТ (пустой
    ``found`` при названном номере) - значит либо номер лишний, либо франшиза не та.
    В обоих случаях впереди был отказ, и заход всей строкой стоит ровно столько же,
    сколько стоил бы он, - как и второй заход по забытой раскладке (:func:`_relayout`).

    На счастливом пути этого захода нет вовсе: «тачки 2», «форсаж 5», «шрек 2» находят
    свою картину первым же кругом, и сюда не заглядывают. Круг платится из остатка цели
    (:func:`_no_budget`), как и все прочие доборы.

    ⚠️ Не помогло - остаётся ПРЕЖНЯЯ выдача, а не расширенная. Лишние строки сдвинули бы
    нумерацию франшизы (о том же :func:`_second_language`), и честное «номера N нет»
    стало бы неправдой про другую линейку.
    """
    from torrcast.parse import cluster, pick_franchise

    if _no_budget(client, f"поиск «{query}» целиком", progress) is None:
        return raw, cluster(to_releases(raw)), []
    progress.phase(f"поиск «{query}»")
    merged = merge(raw, _ask(client, query, progress))
    progress.phase("")
    if len(merged) == len(raw):
        return raw, cluster(to_releases(raw)), []
    pictures = cluster(to_releases(merged))
    found = pick_franchise(query, pictures)
    if not found:
        return raw, cluster(to_releases(raw)), []
    progress.note(f"по «{name}» картины не нашлось - искал «{query}» целиком")
    return merged, pictures, found


def _season_asked(found: list[Picture], name: str, pictures: list[Picture]) -> bool:
    """Номер запроса просит СЕЗОН сериала, а не часть франшизы (TC-363).

    Спрашивается ровно то же, что решил разбор (:func:`~torrcast.parse.reads_season`), и
    сверяется его ответом: номер отдан сериалам франшизы, а не картине по счёту. Двух
    правил тут нет - есть одно, и cli лишь читает, чем оно кончилось: номер должен
    доехать до сезонной машинерии, а знает про сезоны она, а не разбор.
    """
    from torrcast.parse import pick_franchise, reads_season

    if not found or any(picture.kind != "tv" for picture in found):
        return False
    return reads_season(pick_franchise(name, pictures))


__all__ = [name for name in globals() if not name.startswith("__")]
