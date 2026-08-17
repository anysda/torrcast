"""Часть CLI; публичный фасад — :mod:`torrcast.cli`."""

from __future__ import annotations

from torrcast.domain._series import _Series
from torrcast.ports.journal import journal
from torrcast.usecases.choice import first_alive, fitness
from torrcast.usecases.discover import _ask, _asked_kind, _no_budget
from torrcast.usecases.rank import gate_open, last_hope, rank_releases

__all__ = [
    "CAUTIOUS",
    "Episode",
    "Picture",
    "Profile",
    "Release",
    "_as_is",
    "_ceiling_hides_name",
    "_ceiling_reinforce",
    "_foreign_note",
    "_lacks_season",
    "_leading",
    "_plan_for",
    "_season_reinforce",
    "_timed",
    "_topup",
    "_twin",
    "_voice_reinforce",
    "catalog_has_name",
    "franchise_key",
    "menu_order",
    "minutes_of",
    "recodes_whole",
    "replace",
    "same_name",
    "same_picture",
    "slugify",
    "split_franchise_index",
    "transliterate",
    "voiceless_pool",
]

from dataclasses import replace
from typing import TYPE_CHECKING, Any, TypeAlias

from torrcast.domain.catalog_has_name import catalog_has_name
from torrcast.domain.episode import Episode
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.minutes_of import minutes_of
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.same_name import same_name
from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.menu_order import menu_order
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.recodes_whole import recodes_whole
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.domain.transliterate import transliterate
from torrcast.ports.passport_source import PassportSource
from torrcast.ports.torrent_catalogue import IndexerClient, RawRow, TorrentCatalogue

if TYPE_CHECKING:
    Args: TypeAlias = Any
    Config: TypeAlias = Any
    Facts: TypeAlias = Any
    Progress: TypeAlias = Any
    _Plan: TypeAlias = Any

KIN_SHOWN = 3
#: Каталог раздач и справка о картинах - единственное, что у добора снаружи. Ставит их
#: фасад :mod:`torrcast.reinforce`: только он видит и :mod:`torrcast.search`, и
#: :mod:`torrcast.facts`, которые по слоям ещё не разложены.
#:
#: ⚠️ Имена тут длиннее очевидных нарочно. Плоский namespace прежнего монолита
#: (:mod:`torrcast.cli`) вписывает в КАЖДУЮ свою часть globals всех остальных, и короткое
#: ``_passport`` тут же затирается одноимённой функцией отбора
#: (:func:`torrcast.usecases.choice._passport`) - справка молча превращается в чужую
#: функцию, и добор падает на первом же вопросе о годе.
_catalogue: TorrentCatalogue
_passport_source: PassportSource


def configure(catalogue: TorrentCatalogue, passport: PassportSource) -> None:
    """Передать сценарию каталог раздач и справку о картинах."""
    global _catalogue, _passport_source
    _catalogue, _passport_source = catalogue, passport


def _as_is(
    raw: list[RawRow], found: list[Picture], about: Origin, progress: Progress
) -> tuple[list[RawRow], list[Picture], list[Picture]]:
    """Добора не было - остаётся то, что нашёл русский запрос. И сказать, если год спорит.

    🔴 **Право у гейта года ровно одно - не ДОБАВИТЬ своё. ОТНЯТЬ найденное русским
    запросом он не вправе.** Раньше отнимал: справка знает «Крестьян» 1935 года, в
    каталоге под этим именем лежит картина 2023-го, и живой BDRip 1080p выбрасывался
    целиком - человек читал «ничего не нашлось» при существующей картине. Честный отказ
    там, где кино есть, это не осторожность, а брак: спорить о годе можно, только пока
    есть о чём спорить, а после отказа человеку не остаётся вообще ничего.

    Расхождение при этом не замалчивается - оно печатается строкой. Слово справки против
    слова каталога решает человек: имя он назвал сам, картину под этим именем видит в
    меню вместе с её годом, а мы говорим ровно то, что знаем, и ничего за него не решаем.

    ⚠️ Спорный год - это ещё не подмена. Настоящие подмены («Восхождение» Шепитько против
    китайского ``The Climbers``) ловит гейт ДОБОРА: там чужая картина именно ДОБАВЛЯЕТСЯ
    к найденному, и вот её-то брать нельзя (:func:`_second_language`, :func:`_vouched`).
    Здесь же добавлять нечего - добора не было вовсе.

    ⚠️ Условия узкие нарочно. Строка говорится про ОДНУ картину - ту, что нашлась под этим
    именем в единственном числе. Во франшизе справка отвечает про первую часть, а в
    каталоге может лежать вторая: на «моане 2» широкий вариант этой сверки ругался бы на
    честную выдачу. Не знает года справка, картин несколько, годы сходятся - молчим.
    """
    from torrcast.domain.cluster import cluster

    if about.name and not about.title:
        for picture in found:
            if same_name(picture.title, about.name):
                picture.native = True
    stays = (raw, cluster(_catalogue.to_releases(raw)), found)
    if about.year is None or len(found) != 1 or found[0].year is None:
        return stays
    if abs(found[0].year - about.year) <= 1:
        return stays
    # Тот же оригинал - ремейк, а не другая картина: справка знает «Fruits Basket» 2006, в
    # каталоге ремейк 2019, и это одна и та же вещь. Чужой оригинал год по-прежнему разводит.
    if found[0].original and slugify(found[0].original) == slugify(about.title):
        return stays
    progress.phase("")  # вердикт - итог уже законченного круга, и печатается после него
    progress.note(
        f"под этим именем в каталоге лежит картина {found[0].year} года, "
        f"а не {about.year} - другой там нет"
    )
    return stays


def _ceiling_hides_name(
    client: IndexerClient, name: str, pictures: list[Picture], found: list[Picture]
) -> bool:
    """Выдача упёрлась в потолок индексера, а картины с именем запроса в ней нет.

    Третий повод второго круга рядом с тощим и негодным пулом
    (:func:`worth_asking_original`): пул густой и годный, но обрезан СВЕРХУ. Замер по
    сохранённым выдачам: 46 запросов из 100 хотя бы один индексер закрыл ровно сотней
    строк (у RuTor это его собственный потолок - с ``limit=400`` он отдаёт те же 100).
    Пока имя запроса в выдаче есть, обрезан хвост - досадно, но жить можно. А вот когда
    имени нет вовсе, потолок прячет САМУ картину: по запросу «девять» 21 раздача картины
    «Девять» (2009) лежит за сотней, каталог её не видит, и в меню человек получает
    «Девять ярдов» - при том что пул тощим не считается и ни один добор не запускается.

    Пустой ``found`` сюда не доходит: там пул тощий по определению, и первым отвечает
    добор вторым языком (:func:`_second_language`).
    """
    return (
        bool(found) and bool(getattr(client, "capped", ())) and not catalog_has_name(name, pictures)
    )


def _ceiling_reinforce(
    client: IndexerClient,
    name: str,
    args: Args,
    raw: list[RawRow],
    pictures: list[Picture],
    found: list[Picture],
    progress: Progress,
    *,
    passport: PassportSource | None = None,
) -> tuple[list[RawRow], list[Picture], list[Picture]]:
    """Второй круг с УТОЧНЁННЫМ запросом «имя + год из справки». Не помогло - как было.

    Голое имя индексер закрыл потолком, поэтому спрашиваем точнее: год сужает выдачу
    так, что нужная картина влезает под потолок (по «девять» - сотня чужих строк, по
    «девять 2009» - 22 строки, и «Девять» (2009) среди них). Год берётся только из
    справки: выдача года не знает, а выдумывать его нечем.

    Ограждения - те же, что у добора вторым языком (:func:`_second_language`):

    * круг платится из остатка цели (:func:`_no_budget`);
    * имя, за которое справка не ручается (:attr:`~torrcast.facts.Origin.guessed`),
      ничего не решает - уточнения не бывает (гейт TC-253);
    * берутся только картины, подписанные ТОЧНО спрошенным именем
      (:func:`~torrcast.parse.catalog_has_name`), и только тех, чей год не спорит со
      справкой. Ничего такого не приехало - остаётся прежняя выдача, хуже не бывает.

    ⚠️ Тип картины справке подсказывает вожак пула - ровно как в доборе вторым языком
    (:func:`_asked_kind`). Он сосед по подстроке, а не сама картина, и без подсказки
    справка уходит в режим «оба типа, верить согласию»: по «девять» путь сериала
    притаскивает лишь похожее имя («Девять совсем незнакомых людей»), согласия с
    фильмом нет - и паспорт пуст при живой статье «Девять (фильм)». Подмену тут держит
    не тип, а гейт ниже: берутся только картины, подписанные ТОЧНО спрошенным именем,
    и только тех лет, что назвала справка.

    Строка итога - после строки самого круга (о порядке - :func:`_second_language`), и
    картины с именем запроса встают ВПЕРЕДИ соседей по подстроке: спрошенное имя точнее
    вхождения. Подмена при этом не молчаливая - она и есть содержание строки.
    """
    from torrcast.domain.cluster import cluster

    if (spare := _no_budget(client, f"уточнение по «{name}»", progress)) is None:
        return raw, pictures, found
    about = (passport or _passport_source)(
        name, series=_asked_kind(_leading(found), args), budget=spare
    )
    if about.guessed or about.year is None:
        return raw, pictures, found
    refined = f"{name} {about.year}"
    progress.phase(f"поиск «{refined}»")
    merged = _catalogue.merge(raw, _ask(client, refined, progress))
    progress.phase("")
    if len(merged) == len(raw):
        return raw, pictures, found
    wider = cluster(_catalogue.to_releases(merged))
    vouched = [
        p
        for p in wider
        if catalog_has_name(name, [p]) and (p.year is None or abs(p.year - about.year) <= 1)
    ]
    if not vouched:
        return raw, pictures, found
    kept = [p for p in found if p.key not in {q.key for q in vouched}]
    first = vouched[0]
    progress.note(
        f"по «{name}» выдача упёрлась в потолок каталога, а самой картины в ней нет - "
        f"добрал по «{refined}»: «{first.title}» ({first.year or 'год не назван'})"
    )
    return merged, wider, vouched + kept


def _lacks_season(found: list[Picture], args: Args) -> bool:
    """Сериал найден, а раздач нужного сезона в нём нет ни по одному имени.

    Ровно тот случай, где отбор упирался в «раздач с сезоном N нет»: TC-6 берёт сезон-пак,
    КОГДА он есть в выдаче, но у части западных сериалов («Ангел») русский запрос не
    приносит ни одной раздачи с нужным сезоном - пак лежит под оригинальным именем со
    строкой сезона (``Angel S01``), до которой русское слово не достаёт. Проверяем по
    именам (:meth:`Release.covers`), без похода в рой: имя пака сезон называет само.
    """
    tv = [p for p in found if p.kind == "tv"]
    if not tv:
        return False
    want = args.episode or Episode(1, 1)
    return not any(r.covers(want.season) for p in tv for r in p.releases)


def _season_reinforce(
    client: IndexerClient,
    query: str,
    args: Args,
    raw: list[RawRow],
    found: list[Picture],
    progress: Progress,
    titled: bool = False,
    *,
    passport: PassportSource | None = None,
) -> tuple[list[RawRow], list[Picture], list[Picture]]:
    """Добрать сезон-пак сезонной строкой по оригиналу, прежде чем честно отказать.

    Родня транслит-добору (:func:`_second_language`), но повод другой: там пул тощий и
    добираем ЛЮБЫЕ раздачи, здесь пул может быть и полным, а не хватает раздач ровно
    нужного СЕЗОНА. Индексер ищет по имени раздачи, поэтому сезон-пак «Angel [S01-05]»
    русское «ангел» не приносит - его находит строка ``Angel S01`` по оригиналу.

    🔴 **Гейт против подмены.** Добор не пересобирает выдачу как попало: из ответа сезонной
    строки берутся ТОЛЬКО раздачи, у которых оригинал совпадает с оригиналом найденного
    сериала И имя которых называет нужный сезон. Без этого «Angel S01» натащил бы десяток
    чужих аниме («The Angel Next Door ... S01»): у них другой оригинал, и фильтр их
    отсекает. Сама картина после этого выбирается прежним :func:`~torrcast.parse.pick_franchise`.

    Один лишний круг по индексерам, и только когда сезона в выдаче не было вовсе
    (:func:`_lacks_season`): на счастливом пути добора нет. Ничего не подошло - остаётся
    прежний результат, дальше честное «раздач с сезоном N нет».

    🔴 Оригинала у вожака нет - опора только справка, и её ДОГАДКА
    (:attr:`~torrcast.facts.Origin.guessed`) ключом фильтра быть не вправе: имя, лишь
    признанное похожим, бывает чужой картиной под тем же русским словом, и тогда её
    раздачи сшиваются с вожаком по русскому имени - подмена мимо гейта TC-253. Догадка
    берётся ровно с тем же вторым признаком, что и в доборе вторым языком: справка сама
    называет найденную картину тем же словом, что спросили.

    ⚠️ ``titled`` - каталог уже сказал, что хвостовая цифра это часть НАЗВАНИЯ, а не номер
    части (:func:`_titled_number`). Тогда строку делить повторно нельзя: обрубок «бен»
    уводит и справку, и сезонную строку за чужой картиной, как и в доборе вторым языком
    (:func:`_second_language`).
    """
    from torrcast.domain.cluster import cluster
    from torrcast.domain.pick_franchise import pick_franchise

    name, _index = (query, None) if titled else split_franchise_index(query)
    want = args.episode or Episode(1, 1)
    lead = max((p for p in found if p.kind == "tv"), key=lambda p: len(p.releases), default=None)
    if lead is None:
        return raw, cluster(_catalogue.to_releases(raw)), found
    # Сезонная строка - такой же второй круг, как и добор вторым языком, и цель тратит
    # так же (TC-228). Остатка нет - честнее отказать сразу, чем платить полный круг.
    if (spare := _no_budget(client, f"добор сезона {want.season}", progress)) is None:
        return raw, cluster(_catalogue.to_releases(raw)), found
    # 🔴 Оригинала у вожака нет - опора только справка, и её догадка (Origin.guessed)
    # ключом фильтра быть не вправе: имя, лишь признанное похожим, бывает чужой
    # картиной под тем же русским словом. Второй признак тот же, что у гейта добора
    # (:func:`_second_language`): справка сама зовёт найденную картину тем же словом,
    # что спросили, - тогда это описка, а не чужая статья. Нет признака - остаётся
    # транслит: свои слова запроса чужой картины не принесут.
    hint = ""
    if not lead.original:
        about = (passport or _passport_source)(name, series=True, budget=spare)
        if about.title and (not about.guessed or (about.name and same_name(name, about.name))):
            hint = about.title
    base = (lead.original or hint or transliterate(name)).strip()
    season_query = f"{base} S{want.season:02d}" if base else ""
    # Тем же именем второй раз ходить незачем: если оригинала нет и транслит совпал с
    # запросом, сезонная строка это тот же круг по индексерам ради той же выдачи.
    if not base or slugify(season_query) == slugify(name):
        return raw, cluster(_catalogue.to_releases(raw)), found
    progress.phase(f"поиск «{season_query}»")
    extra = _ask(client, season_query, progress)
    progress.phase("")
    want_orig = slugify(lead.original or base)
    # Берём лишь раздачи ТОГО ЖЕ оригинала и ровно нужного сезона: чужое одноимённое
    # (аниме «The Angel Next Door») по оригиналу не проходит.
    keep = [
        row
        for row, rel in zip(extra, _catalogue.to_releases(extra), strict=True)
        if rel.original and slugify(rel.original) == want_orig and rel.covers(want.season)
    ]
    merged = _catalogue.merge(raw, keep) if keep else raw
    if len(merged) == len(raw):
        return raw, cluster(_catalogue.to_releases(raw)), found
    pictures = cluster(_catalogue.to_releases(merged))
    wider = pick_franchise(query, pictures)
    progress.note(f"сезона {want.season} в выдаче не было - добрал по «{season_query}»")
    return merged, pictures, wider


def voiceless_pool(
    found: list[Picture], args: Args, config: Config, profile: Profile = CAUTIOUS
) -> Picture | None:
    """Картина, у которой русская дорожка обещана только в неиграбельных раздачах.

    🔴 Русская дорожка - часть «включилось», а не предпочтение (TC-178): релиз без неё
    показу не годится, и очередь на нём не кончается, а идёт дальше. Значит картина,
    у которой дубляж лежит ровно там, куда отбор не ходит, - это не «выбор победнее»,
    а вечер, которого не будет, и повод переспросить он ровно такой же, как негодный пул
    (:func:`unfit_pool`). Живые случаи - обе «Тачки»: у первой части русские раздачи
    оказались образами DVD, у второй дубляж обещан 38-гигабайтным 4К-ремуксом и
    56-гигабайтным двухдисковым изданием, и то и другое отбор не берёт по делу.

    Условия ДВА, и второе не менее важно первого:

    * ни одна играбельная раздача русского не обещает. «Играбельная» - то же самое слово,
      что и в :func:`fitness`: годна воротами, жива и не старьё;
    * а НЕИГРАБЕЛЬНАЯ - обещает. Без этого условия круг платили бы за любую выдачу,
      чьи имена о звуке просто МОЛЧАТ, - а молчание вполне может скрывать дубляж, его
      рассудит ffprobe (:func:`sound_step` о том же). Здесь же каталог сказал прямо:
      русская дорожка у картины есть, и лежит она не там, где мы ищем.

    Спрашивается по имени раздачи (:attr:`~torrcast.parse.Release.dubbed`), то есть до
    всякого ffprobe и без единого похода в рой.

    Картина берётся не любая из найденных, а ТА, ЧТО СЫГРАЕТ (:func:`first_alive`): на
    франшизе «тачки» это первая часть, а не самая обсиженная третья, и добирать надо
    именно ей. Без оригинала или года точной строки не собрать - тогда ``None``.

    ⚠️ Сериал сюда не заходит, и это не забывчивость. «Оригинал + год» - приём КАТАЛОГА
    ПОЛНОМЕТРАЖНОГО КИНО: у фильма год стоит в имени каждой раздачи и разводит выдачу, а
    сезон-пак подписан годом первого сезона или вилкой лет, и точной строкой его не
    вытащить - его вытаскивает своя, сезонная (:func:`_season_reinforce`).

    Замер по ста сохранённым выдачам говорит и про цену: круг сработал бы в 13 из 99, а
    без сериалов - в 5 из 99. Это один лишний круг по индексерам там, где иначе показа
    нет, и платится он из остатка цели (:func:`_no_budget`), как и оба соседних добора.
    """
    plans = [
        plan
        for plan in (_plan_for(p, args, config, profile) for p in menu_order(found))
        if plan.ranked
    ]
    if not plans:
        return None
    plan = plans[first_alive(plans) - 1]
    # Тип самого плана назвать пока нечем: у отбора он свой в каждом из двух фасадов
    # (`torrcast.selection` и `torrcast.usecases.select`), и до их сведения `_Plan`
    # остаётся `Any`. А вот картина у плана - обычная доменная :class:`Picture`, и
    # наружу она уходит под своим именем, а не безымянной.
    picture: Picture = plan.picture
    if picture.kind == "tv" or not picture.original or not picture.year:
        return None
    if fitness(plan, dubbed=True) or not any(r.dubbed for r in plan.ranked):
        return None
    return picture


def _voice_reinforce(
    client: IndexerClient,
    query: str,
    lead: Picture,
    raw: list[RawRow],
    found: list[Picture],
    progress: Progress,
    titled: bool = False,
) -> tuple[list[RawRow], list[Picture], list[Picture]]:
    """Добрать точной строкой «оригинал + год», когда русской дорожки нет ни у кого.

    🔴 Третий добор, и повод у него свой. Тощий пул добирают вторым языком
    (:func:`_second_language`), нехватку сезона - сезонной строкой
    (:func:`_season_reinforce`), а здесь раздач может быть сколько угодно, и все они
    негодны по одной причине: играть картину не на чем по-русски.

    Живые случаи, ради которых написано, - обе «Тачки»:

    * «тачки» - все русские раздачи первой части оказались образами DVD (играть в них
      нечего), и единственным кандидатом остался англоязычный ``Cars 2006 BluRay 1080p``
      на 66 сид. Добор вторым языком сюда уже сходил и принёс ровно его;
    * «тачки 2» - кандидатами стоят 0.4-гигабайтный HDRip «фильм о фильме» и ремукс на
      27 ГБ, о звуке молчащий, а дубляж лежит в 38-гигабайтном 4К-ремуксе, который
      потолок битрейта не пускает по делу.

    Обычный запрос обеих не спасает, и вот почему: индексер отдаёт первую сотню строк
    на слово, и по слову ``Cars`` в неё попадают «Тачки 3», «Cars on the Road», гоночные
    симуляторы и десяток англоязычных рипов, а русский ``BDRip 1080p | D`` - нет. ГОД в
    строке эту сотню и разводит: по ``Cars 2006`` приезжает «Тачки / Cars (2006) BDRip
    1080p | D» на 61 сид, по ``Cars 2 2011`` - «Тачки 2 / Cars 2 (2011) BDRip 1080p» на
    11 сид. Обе - честный 1080p с дубляжом, обе легче пяти гигабайт.

    🔴 **Однофамильца этот круг не приносит.** Из ответа берутся только раздачи, у
    которых ОРИГИНАЛ совпадает с оригиналом картины, за которой шли, и год сходится с её
    годом (±1 - разница проката и производства). Новых картин добор не открывает вовсе:
    он пополняет ту, что уже нашлась, и меню от него не растёт. Ничего не подошло -
    остаётся прежняя выдача целиком.

    Один лишний круг по индексерам, и только там, где иначе показа нет: пока у картины
    есть живая раздача с обещанным русским звуком, сюда не заходят (:func:`voiceless_pool`).
    Круг платит из остатка цели, как и оба соседних добора (:func:`_no_budget`).

    ⚠️ ``titled`` - каталог уже сказал, что хвостовая цифра это часть НАЗВАНИЯ, а не номер
    части (:func:`_titled_number`). Тогда строку делить повторно нельзя: обрубок «бен»
    уводит точную строку за чужой картиной, как и в доборе вторым языком
    (:func:`_second_language`).
    """
    from torrcast.domain.cluster import cluster
    from torrcast.domain.pick_franchise import pick_franchise

    name, _index = (query, None) if titled else split_franchise_index(query)
    exact = f"{lead.original} {lead.year}"
    # Тем же именем второй раз ходить незачем: это тот же круг ради той же выдачи.
    if slugify(exact) == slugify(name):
        return raw, cluster(_catalogue.to_releases(raw)), found
    if _no_budget(client, f"добор по «{exact}»", progress) is None:
        return raw, cluster(_catalogue.to_releases(raw)), found
    progress.phase(f"поиск «{exact}»")
    extra = _ask(client, exact, progress)
    progress.phase("")
    want_orig = slugify(lead.original or "")
    keep = [
        row
        for row, rel in zip(extra, _catalogue.to_releases(extra), strict=True)
        if rel.original
        and slugify(rel.original) == want_orig
        and rel.year is not None
        and lead.year is not None
        and abs(rel.year - lead.year) <= 1
    ]
    merged = _catalogue.merge(raw, keep) if keep else raw
    if len(merged) == len(raw):
        return raw, cluster(_catalogue.to_releases(raw)), found
    pictures = cluster(_catalogue.to_releases(merged))
    wider = pick_franchise(query, pictures)
    was = sum(len(p.releases) for p in found)
    now = sum(len(p.releases) for p in wider)
    if now <= was:
        # Прибавка ушла мимо картины - тогда второго захода как будто и не было.
        return raw, cluster(_catalogue.to_releases(raw)), found
    progress.note(
        f"«{lead.title}» по-русски есть только там, где играть нечем - "
        f"добрал по «{exact}»: раздач стало {now}"
    )
    return merged, pictures, wider


def _leading(pictures: list[Picture]) -> Picture | None:
    """Картина, за которой идут: самая полная из найденных.

    Именно она - дефолт меню и она же играет, когда терминала нет. Гейт добора смотрит на
    неё, а не на список целиком: список одноимённых картин от добора и должен пополняться,
    а вот вожак меняться не должен.
    """
    return max(pictures, key=lambda p: len(p.releases), default=None)


def _twin(pictures: list[Picture], about: Origin, before: Picture | None) -> Picture | None:
    """Кого из приехавших после добора сверять с той картиной, за которой шли.

    Не самого многолюдного: добор по русскому имени приносит ФРАНШИЗУ целиком, и вожаком
    в ней становится самая раздаваемая часть. На «cars» это «Тачки 3» (14 раздач против
    четырёх у «Тачек» 2006 года), гейт читал 2017 против 2006 как подмену и выбрасывал
    ровно ту выдачу, за которой ходил: человек оставался с одной мёртвой англоязычной
    раздачей при живых русских.

    Поэтому сверяется картина ТОГО ЖЕ ГОДА - года справки, а её нет, так года той картины,
    за которой шли. Нет среди приехавших картины нужного года - сверять идёт вожак.

    🔴 Зовётся это только на ДОКАЗАННОМ имени добора (справка), и в этом вся его
    безопасность: справка отвечает про ту самую картину, поэтому вопрос к добору один -
    доехала ли она. Имя, подобранное из выдачи, не доказывает ничего: под ним приезжает
    однофамилец («Восхождение» - и фильм Шепитько, и китайский ``The Climbers``), и там
    сверяется вожак, то есть тот, кто станет ответом.
    """
    year = about.year if about.year is not None else (before.year if before else None)
    if year is not None:
        near = [p for p in pictures if p.year is not None and abs(p.year - year) <= 1]
        if near:
            return max(near, key=lambda p: len(p.releases))
    return _leading(pictures)


def same_picture(
    before: Picture | None, after: Picture | None, about: Origin, proven: bool
) -> bool:
    """Та же ли картина возглавляет выдачу после добора.

    Год из справки - последнее слово: она отвечает про картину, которую спросили, и если
    вожак после добора другого года, значит приехал однофамилец. Справки нет - сверяем с
    годом того, за кем шли. Годов не назвал никто (сериалы часто без года) - остаётся
    франшиза: подмену она не ловит, но и врать не будет, а без года подменять по сути
    нечего - раздачи неотличимы, и кластер всё равно свёл бы их в одну картину.

    Год ± 1 - это не послабление, а разница между годом производства и годом проката:
    её раздачи путают постоянно, и на ней гейт спотыкался бы о честный добор.

    Отдельный случай - ``before is None``: русский запрос не нашёл ни одной картины, и
    сверять добор не с чем. Тогда решает происхождение названия (``proven``): справка и
    транслит говорят о том, что спросили, а вот непроверенному оригиналу из выдачи в
    пустоту веры нет - «не нашлось» честнее наугад взятого однофамильца.

    ⚠️ TC-253. Слово справки на этом пути стоит ровно столько, сколько стоит само имя, а
    сюда оно приходит уже проверенным: догадку по сходству имён («Все мы незнакомцы» →
    «Все мы убийцы») отсеивает :func:`_second_language` ДО второго захода. Здесь её
    ловить нечем - сравнить не с чем, и в этом вся суть случая.
    """
    if after is None:
        return False
    # Ремейк или переиздание с тем же оригиналом - та же картина, хоть годы и врозь:
    # справка знает «Fruits Basket» 2006, а у индексеров ремейк 2019, и это добор, а не
    # подмена. Спорит с годом только совпадение самого ОРИГИНАЛА: русское имя картину не
    # определяет, а чужой оригинал («The Climbers» против «The Ascent») год по-прежнему
    # разводит - дыру для настоящих подмен это не открывает.
    if about.title and after.original and slugify(after.original) == slugify(about.title):
        return True
    if about.year is not None and after.year is not None:
        return abs(after.year - about.year) <= 1
    if before is None:
        return proven
    if before.year is not None and after.year is not None:
        return abs(after.year - before.year) <= 1
    return franchise_key(before.title) == franchise_key(after.title)


def _plan_for(
    picture: Picture,
    args: Args,
    config: Config,
    profile: Profile = CAUTIOUS,
    runtime: float = 0.0,
) -> _Plan:
    """План по одной картине: пул релизов в порядке отбора и цель для сериала.

    ``runtime`` — настоящая длительность картины, секунды (из справки, :func:`_timed`).
    Ноль — её не назвал никто, и в знаменатель битрейта идёт прикидка
    (:data:`torrcast.stream.RUNTIME_GUESS`).
    """
    from torrcast.domain.runtime_guess import RUNTIME_GUESS

    series = _Series(want=args.episode or Episode(1, 1)) if picture.kind == "tv" else None
    known = runtime > 0
    runtime = runtime if known else RUNTIME_GUESS.get(picture.kind, 7200.0)
    pool = picture.releases
    if series is not None:
        pool = [r for r in pool if r.covers(series.want.season)]
    # Потолок отбора - уже не потолок декодера. Тяжёлые куски перекодируются
    # (:mod:`torrcast.recode`), поэтому честный тяжёлый 1080p теперь берётся, а отбраковывает
    # только то, что перекодированием не спасти, - ``bitrate_hard_mbit``. Перекодирование
    # выключено - потолком снова становится прежний ``bitrate_warn_mbit``.
    # Выше ``bitrate_hard_mbit`` перекодированием спасается не всё, а только то, что
    # перекодируется ЦЕЛИКОМ одним прогоном (``bitrate_recode_mbit``): аниме-BD-ремуксы
    # на 28-37 Мбит/с - ровно этот случай, и отказывать им незачем.
    ceiling = config.bitrate_hard_mbit if config.recode else config.bitrate_warn_mbit
    hard = ceiling
    if config.recode:
        ceiling = max(ceiling, config.bitrate_recode_mbit)
    want = series.want if series else None
    copy_hevc = profile.plays_copy("hevc", profile.copy_depth)
    loose = gate_open(pool, runtime, ceiling, want, hard_mbit=hard, copy_hevc=copy_hevc)
    # Ворота последней надежды открываются при двух условиях сразу, и оба - не про пул.
    # Первое: перекодирование включено. Играть HEVC умеет ровно сплошной перекод, и без
    # него пускать такой релиз в очередь значило бы обещать показ, которого не будет.
    # Второе: HEVC для ЭТОГО приёмника и правда тяжёлый путь - спрашивается там же, где
    # об этом спрашивают показ и прогрев (:func:`torrcast.stream.recodes_whole`), чтобы
    # отбор не судил по чужим числам. Приёмник, который берёт HEVC копией, в последней
    # надежде не нуждается вовсе: у него это обычный релиз, и место ему в воротах,
    # которым передан ответ профиля, а не здесь.
    heavy_hevc = recodes_whole("hevc", profile.copy_depth, profile)
    last = (
        config.recode
        and heavy_hevc
        and last_hope(pool, runtime, ceiling, want, loose, hard, copy_hevc=copy_hevc)
    )
    ranked = rank_releases(
        pool,
        runtime,
        ceiling,
        want=want,
        loose=loose,
        hard_mbit=hard,
        last=last,
        copy_hevc=copy_hevc,
    )
    return _Plan(
        picture=picture,
        ranked=ranked,
        runtime=runtime,
        runtime_known=known,
        off_season=len(picture.releases) - len(pool),
        warn_mbit=ceiling,
        series=series,
        recode_at=config.recode_at_mbit if config.recode else 0.0,
        loose=loose,
        last_resort=last,
        copy_hevc=copy_hevc,
        hard_mbit=hard,
        asked_series=args.episode is not None,
    )


def _timed(
    plan: _Plan, facts: Facts | None, args: Args, config: Config, profile: Profile = CAUTIOUS
) -> _Plan:
    """Пересобрать план на НАСТОЯЩЕЙ длительности картины, как только её назвала справка.

    🔴 TC-185. Битрейт релиза отбор считает делением размера раздачи на длительность
    (:func:`bitrate_of`), а длительности до ffprobe он не знает и берёт прикидку «фильм
    это два часа». Прикидка не нейтральна: у «Интерстеллара» (2 ч 49 мин) она завышает
    битрейт в 1.41 раза, у «Форреста Гампа» (2 ч 22 мин) — в 1.18, и честный 1080p,
    лежащий под потолком, отсекался потолком, которого он не переходил. Молча: отказ
    арифметики строки не печатает.

    Потолки при этом не двигаются ни на знак — чинится ЗНАМЕНАТЕЛЬ.

    Лишнего запроса тут нет ни одного: хронометраж уже приехал в справке к меню
    («2 ч 49 мин» печатается рядом с рейтингом), и спрашивается он у той же
    :class:`~torrcast.facts.Facts`, которую меню уже дождалось. Поэтому и зовётся это
    ПОСЛЕ меню: до меню справки ещё нет, а ждать её на пути старта нельзя.

    Справка молчит (нет статьи, нет сети, картины нет в выгрузке) — план остаётся на
    прикидке, и это решение не молчаливое: событие ``runtime`` уходит в недельный след
    (:func:`torrcast.trace.emit`) с тем же числом, которым считался битрейт.
    """
    fact = facts.get(plan.picture.title, plan.picture.year) if facts is not None else Fact()
    minutes = minutes_of(fact.runtime)
    if minutes <= 0:
        journal().emit(
            "select", "runtime", secs=round(plan.runtime), src="guess", title=plan.picture.title
        )
        return plan
    fresh = _plan_for(plan.picture, args, config, profile, runtime=minutes * 60.0)
    fresh.kin = plan.kin
    journal().emit(
        "select",
        "runtime",
        secs=round(fresh.runtime),
        src="facts",
        title=plan.picture.title,
        was=round(plan.runtime),
    )
    return fresh


def _topup(
    plan: _Plan,
    args: Args,
    config: Config,
    profile: Profile,
    progress: Progress,
    menu: frozenset[str] = frozenset(),
) -> _Plan:
    """Долить опоздавший индексер в пул УЖЕ выбранной картины (TC-118).

    🔴 Круг индексеров уходит по кворуму (:data:`~torrcast.search.QUORUM_INDEXERS`), и
    опоздавший доезжает, когда список картин человек уже прочитал. Место вызова выбрано
    ровно по одному правилу: **менять то, на что человек смотрит, нельзя**. Поэтому
    долив зовётся ПОСЛЕ ответа на меню, и права у него ровно одно - пополнить пул той
    картины, которую и выбрали:

    * список картин, их порядок и дефолт долив не трогает вовсе - меню уже напечатано,
      и подменить в нём номер или первую живую часть значило бы соврать задним числом;
    * картина, которой в меню не было, из долива в него не попадает - её и предложить
      уже некому. Но и молча она не пропадает (TC-238): её называет одна честная
      строка (:func:`_foreign_note`), как и всякое авто-решение;
    * а вот верх ОТБОРА долив поменять вправе - выбирали картину, а не раздачу, - но
      молча этого не делает: строка ниже называет и опоздавшего, и то, что верх другой.

    Пул при этом только растёт: старые раздачи остаются теми же объектами, и прогрев,
    пущенный под меню, переезжает на новые номера (:meth:`_Bench.reorder`), а не
    выбрасывается. Долив пустой или ничего не добавил - план возвращается прежним.
    """
    from torrcast.domain.cluster import cluster

    rows = plan.late()
    if not rows:
        return plan
    extra = _catalogue.to_releases(rows)
    have = {r.magnet for r in plan.picture.releases}
    # Кластер тут - судья принадлежности, а не сборщик: спрашиваем у него, какие из
    # приехавших раздач относятся к ТОЙ ЖЕ картине, и берём только их. Сам пул собираем
    # заменой поля, чтобы прежние релизы остались прежними объектами - по ним прогрев и
    # ищет своё новое место.
    grown = next(
        (p for p in cluster([*plan.picture.releases, *extra]) if p.key == plan.picture.key), None
    )
    mine = {r.magnet for r in grown.releases} if grown is not None else set()
    add = [r for r in extra if r.magnet in mine and r.magnet not in have]
    # Чужая картина (TC-238): в меню её внести нельзя, но и пропасть молча она не
    # должна - строка печатается независимо от того, был ли долив в свою картину.
    _foreign_note([r for r in extra if r.magnet not in mine], menu, progress)
    if not add:
        return plan
    fresh = _plan_for(
        replace(plan.picture, releases=[*plan.picture.releases, *add]), args, config, profile
    )
    if not fresh.ranked:  # отнимать уже показанное долив не вправе
        return plan
    fresh.kin = plan.kin
    who = ", ".join(sorted({r.indexer for r in add if r.indexer})) or "опоздавший индексер"
    changed = bool(plan.ranked) and fresh.ranked[0].magnet != plan.ranked[0].magnet
    progress.note(
        f"«{who}» доехал после списка: раздач {len(fresh.picture.releases)}"
        f" вместо {len(plan.picture.releases)}" + (", верх отбора другой" if changed else "")
    )
    return fresh


def _foreign_note(foreign: list[Release], menu: frozenset[str], progress: Progress) -> None:
    """Честная строка про картину опоздавшего индексера, которой в меню не было (TC-238).

    Меню напечатано и отвечено, поэтому внести туда новую картину долив не вправе
    никогда - но молчаливых пропаж у нас нет: человек узнаёт, что опоздавший источник
    привёз ещё одну картину, и что в отбор она не пойдёт. Раздачи картин, которые в
    меню ЕСТЬ (``menu`` - ключи показанного списка), строки не получают: сказать про
    них «в списке её не было» значило бы соврать.
    """
    from torrcast.domain.cluster import cluster

    guests = [p for p in cluster(foreign) if p.key not in menu]
    if not guests:
        return
    who = (
        ", ".join(sorted({r.indexer for p in guests for r in p.releases if r.indexer}))
        or "опоздавший индексер"
    )
    names = ", ".join(f"«{p.title}» ({p.year or '?'})" for p in guests[:KIN_SHOWN])
    if len(guests) > KIN_SHOWN:
        names += f" и ещё {len(guests) - KIN_SHOWN}"
    progress.note(
        f"«{who}» доехал после списка: привёз {names} - "
        + (
            "в списке её не было, в отбор она не пойдёт"
            if len(guests) == 1
            else "в списке их не было, в отбор они не пойдут"
        )
    )


__all__ = [name for name in globals() if not name.startswith("__")]
