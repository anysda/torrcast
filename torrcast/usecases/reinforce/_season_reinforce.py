"""Круг добора сезон-пака сезонной строкой по оригиналу; зовёт сценарий поиска."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.episode import Episode
from torrcast.domain.facts.same_name import same_name
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.domain.transliterate import transliterate
from torrcast.ports.passport_source import PassportSource
from torrcast.ports.torrent_catalogue import IndexerClient, RawRow
from torrcast.usecases.discover._ask import _ask
from torrcast.usecases.discover._no_budget import _no_budget
from torrcast.usecases.reinforce.configure import _catalogue_port, _passport_port

if TYPE_CHECKING:
    from torrcast.ports.choice_types import Args
    from torrcast.ports.progress import Progress


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
        return raw, cluster(_catalogue_port().to_releases(raw)), found
    # Сезонная строка - такой же второй круг, как и добор вторым языком, и цель тратит
    # так же (TC-228). Остатка нет - честнее отказать сразу, чем платить полный круг.
    if (spare := _no_budget(client, f"добор сезона {want.season}", progress)) is None:
        return raw, cluster(_catalogue_port().to_releases(raw)), found
    # 🔴 Оригинала у вожака нет - опора только справка, и её догадка (Origin.guessed)
    # ключом фильтра быть не вправе: имя, лишь признанное похожим, бывает чужой
    # картиной под тем же русским словом. Второй признак тот же, что у гейта добора
    # (:func:`_second_language`): справка сама зовёт найденную картину тем же словом,
    # что спросили, - тогда это описка, а не чужая статья. Нет признака - остаётся
    # транслит: свои слова запроса чужой картины не принесут.
    hint = ""
    if not lead.original:
        about = (passport or _passport_port())(name, series=True, budget=spare)
        if about.title and (not about.guessed or (about.name and same_name(name, about.name))):
            hint = about.title
    base = (lead.original or hint or transliterate(name)).strip()
    season_query = f"{base} S{want.season:02d}" if base else ""
    # Тем же именем второй раз ходить незачем: если оригинала нет и транслит совпал с
    # запросом, сезонная строка это тот же круг по индексерам ради той же выдачи.
    if not base or slugify(season_query) == slugify(name):
        return raw, cluster(_catalogue_port().to_releases(raw)), found
    progress.phase(f"поиск «{season_query}»")
    extra = _ask(client, season_query, progress)
    progress.phase("")
    want_orig = slugify(lead.original or base)
    # Берём лишь раздачи ТОГО ЖЕ оригинала и ровно нужного сезона: чужое одноимённое
    # (аниме «The Angel Next Door») по оригиналу не проходит.
    keep = [
        row
        for row, rel in zip(extra, _catalogue_port().to_releases(extra), strict=True)
        if rel.original and slugify(rel.original) == want_orig and rel.covers(want.season)
    ]
    merged = _catalogue_port().merge(raw, keep) if keep else raw
    if len(merged) == len(raw):
        return raw, cluster(_catalogue_port().to_releases(raw)), found
    pictures = cluster(_catalogue_port().to_releases(merged))
    wider = pick_franchise(query, pictures)
    progress.note(f"сезона {want.season} в выдаче не было - добрал по «{season_query}»")
    return merged, pictures, wider
