"""Круг поиска целиком: запрос - картины франшизы, каждая со своим пулом релизов."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.cluster import cluster
from torrcast.domain.config import Config
from torrcast.domain.episode import Episode
from torrcast.domain.facts.origin import Origin
from torrcast.domain.infra_error import InfraError
from torrcast.domain.menu_order import menu_order
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.other_words import other_words
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.ports.journal.slot import journal
from torrcast.ports.progress.progress import Progress
from torrcast.ports.state_store.slot import store as watch_store
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.choice._named import _also, _different_display_names, _title
from torrcast.usecases.discover._ask import _ask
from torrcast.usecases.discover._nothing import _nothing
from torrcast.usecases.discover._reread import _relayout, _titled_number
from torrcast.usecases.discover._second_language import _second_language
from torrcast.usecases.discover.kin_line import _kin
from torrcast.usecases.discover.season_gaps import season_gaps
from torrcast.usecases.discover.season_reread import season_reread
from torrcast.usecases.discover.worth_asking_original import worth_asking_original
from torrcast.usecases.reinforce._ceiling_reinforce import _ceiling_reinforce
from torrcast.usecases.reinforce._leading import _leading
from torrcast.usecases.reinforce._season_reinforce import _season_reinforce
from torrcast.usecases.reinforce._voice_reinforce import _voice_reinforce
from torrcast.usecases.reinforce.ceiling_hides_name import ceiling_hides_name
from torrcast.usecases.reinforce.lacks_season import lacks_season
from torrcast.usecases.reinforce.plan_for import plan_for
from torrcast.usecases.reinforce.voiceless_pool import voiceless_pool
from torrcast.usecases.select._measured_runtime import _measured_runtime
from torrcast.usecases.select._studio_seen import _studio_seen

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select.plan import Plan


def search_circle(
    config: Config,
    args: Args,
    progress: Progress,
    profile: Profile = CAUTIOUS,
    *,
    indexer: Callable[[str, str], IndexerClient] | None = None,
    passport: Callable[..., Origin] | None = None,
) -> list[Plan]:
    """Поиск и разбор выдачи: запрос → картины франшизы, каждая со своим пулом релизов.

    ``profile`` - чей декодер судит релизы (:mod:`torrcast.domain.profile`). Пороги битрейта до
    отбора доезжают сами - профиль накладывается на настройки ещё в ``_cmd_play``
    (:func:`torrcast.domain.tune.tune`), - а вот НАБОР КОДЕКОВ в настройках ключа не имеет, и
    спросить о нём можно только сам профиль (:func:`last_hope`). Умолчание осторожное, и
    пользуются им только ручки вроде ``cast voices``: ``cast releases`` передаёт
    обнаруженный профиль явно - таблица обязана судить про тот приёмник, на который
    поедет показ (TC-241).

    ``indexer`` и ``passport`` - откуда берутся клиент индексеров и справка. Умолчание
    боевое (:class:`~torrcast.adapters.prowlarr.prowlarr.Prowlarr`,
    :func:`~torrcast.usecases.passport.Passport.of`); называют их те, у кого своих служб нет, -
    тесты и щупы.
    """
    if not config.prowlarr_apikey:  # без Prowlarr искать нечем - это инфра-ошибка
        raise InfraError(phrase("discover.prowlarr_not_configured"))
    query = args.title_query
    name, index = split_franchise_index(query)
    client = (indexer or _search_state._search_indexers)(
        config.prowlarr_url, config.prowlarr_apikey
    )
    progress.phase(phrase("discover.search_phase", query=name))
    raw = _ask(client, name, progress)
    if not raw:
        # Ни одной строки - повод заподозрить забытую раскладку (:func:`unswap_layout`).
        # Проверка стоит один заход к индексерам и только там, где иначе был бы отказ.
        query, name, index, raw = _relayout(client, query, name, index, progress)
    journal().mark("индексеры ответили", строк=len(raw))  # TC-108: замер
    pictures = cluster(_search_state._search_catalogue.to_releases(raw))
    # Номер в запросе - позиция во франшизе, а не в общей выдаче.
    found = pick_franchise(query, pictures)
    titled = False
    if (reread := season_reread(args, name, index, found, pictures)) is not None:
        # 🔴 TC-363. У сериала номер это сезон, а не часть франшизы
        # (:func:`~torrcast.domain.reads_season.reads_season`), и дальше по строке он идёт ровно тем
        # же путём, что и явное `sNeM`: своей сезонной машинерией, вплоть до честного «раздач с
        # сезоном N нет». Молчать о таком прочтении нельзя - номер человек написал сам, и он вправе
        # знать, чем мы его сочли.
        progress.note(phrase("discover.season_not_part", name=name, index=index))
        args = reread
        query, index = name, None
    if index is not None and not found:
        # Цифра оказалась частью названия, и обрубок увёз поиск не туда
        # (:func:`_titled_number`). Заход платится только вместо отказа.
        raw, pictures, found = _titled_number(client, query, name, raw, progress)
        # Каталог ответил: цифра - часть имени. Дальше по строке идут справка и добор, и
        # обрубок им не годится ровно так же, как не годился индексерам.
        titled = bool(found)
        if titled:
            name, index = query, None
    if worth_asking_original(found, args, config, profile):
        raw, pictures, found = _second_language(
            client, query, args, raw, found, progress, titled, passport=passport
        )
    elif index is None and not titled and ceiling_hides_name(client, name, pictures, found):
        # Номер части и «цифра - часть названия» уточнению не подчиняются: запрос «имя +
        # год» строится по голому имени, и смысл номера в нём теряется.
        raw, pictures, found = _ceiling_reinforce(
            client, name, args, raw, pictures, found, progress, passport=passport
        )
    # Сериал есть, а раздач нужного сезона в нём нет - добрать сезонной строкой по
    # оригиналу, прежде чем честно отказать (:func:`_season_reinforce`).
    if lacks_season(found, args):
        raw, pictures, found = _season_reinforce(
            client, query, args, raw, found, progress, titled, passport=passport
        )
    # Картина есть, а русской дорожки не обещает ни одна её играбельная раздача - добрать
    # точной строкой «оригинал + год» (:func:`_voice_reinforce`).
    if (voiceless := voiceless_pool(found, args, config, profile)) is not None:
        raw, pictures, found = _voice_reinforce(
            client, query, voiceless, raw, found, progress, titled
        )
    journal().mark("поиск", найдено=len(raw))
    journal().emit("search", "query", query=query, raw=len(raw), pictures=len(pictures))
    if not raw:
        raise NotFoundError(phrase("discover.nothing_found", name=name))
    if not pictures:
        raise NotFoundError(phrase("discover.nothing_parsed", name=name))
    if not found:
        raise NotFoundError(_nothing(name, index, pictures))
    lead = _leading(found)
    if lead is not None and other_words(name, lead):
        progress.note(phrase("discover.catalog_alias", name=name, other=_title(lead)))
    if lead is not None and lead.also:
        # Склейка картин (:func:`~torrcast.domain.glue.glue`) - решение автоматическое, и молчать
        # о нём нельзя: человек спросил одно имя, а в меню и в отборе теперь оба.
        also, title = _also(lead), _title(lead)
        if _different_display_names(lead):
            count = len(lead.releases)
            progress.note(phrase("discover.glued_pictures", also=also, title=title, count=count))
    progress.phase("")
    # Номер пункта меню человек читает как номер части и им же отвечает: «Тачки 2» обязаны
    # стоять вторыми, а безномерные - после линейки
    # (:func:`~torrcast.domain.menu_order.menu_order`).
    found = menu_order(found)
    # Память картины доезжает до отбора здесь, и здесь же по одной причине: ступень
    # студии нужна КАЖДОМУ, кто строит меню, - и показу, и `cast releases`, - иначе
    # таблица показывала бы один порядок, а играл бы другой.
    seen = watch_store().load()
    remembered = seen.find(args.title_query)
    plans = []
    for p in found:
        # 🔴 TC-819. Знаменатель битрейта сперва спрашивается у паспорта файла - у уже
        # начатой картины он лежит в записи состояния, и прикидке по типу («серия это
        # 45 минут») верить рядом с замером незачем: на «Киберпанке» она занизила вес
        # релиза вдвое, и ворота пустили его как «под потолком приёмника» в сплошной
        # перекод на весь показ. Молчит и паспорт - прикидка идёт в дело под своим
        # именем: источник знаменателя у каждого плана уходит в след.
        measured = _measured_runtime(seen, p.key, remembered)
        plan = plan_for(
            p, args, config, profile, runtime=measured, studio=_studio_seen(seen, p.key, remembered)
        )
        journal().emit(
            "search",
            "runtime",
            title=p.title,
            secs=round(plan.runtime),
            src="guess" if plan.runtime_estimated else "passport",
        )
        if plan.ranked:
            plans.append(plan)
    for line in season_gaps(found, {plan.picture.key for plan in plans}, args.episode):
        progress.note(line)
    # Соседи по франшизе, до меню не доехавшие: понадобятся, если у выбранной картины
    # годного релиза не окажется вовсе (:func:`kin_line`).
    kin = _kin(_leading(found), pictures, {plan.picture.key for plan in plans})
    for plan in plans:
        plan.kin = kin
        # Опоздавший индексер (круг ушёл по кворуму, TC-118) доедет уже после меню -
        # ручку долива несёт план, а зовут её один раз и после ответа (:func:`_topup`).
        plan.late = client.late
        # 🔴 TC-703. Кто ещё в пути - признак неполноты выдачи: без него отказ по пустой
        # очереди звучит приговором картине (:func:`unfit_line`).
        plan.waiting = client.waiting
    if not plans:  # картина есть, а раздач нужного сезона в ней нет
        want = args.episode or Episode(1, 1)
        raise NotFoundError(
            phrase("discover.no_season_releases", title=_title(found[0]), season=want.season)
        )
    return plans
