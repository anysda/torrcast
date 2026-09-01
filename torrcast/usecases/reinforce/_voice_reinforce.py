"""Круг добора точной строкой «оригинал + год», когда русской дорожки нет ни у кого."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.choice._named import _title
from torrcast.usecases.discover._ask import _ask
from torrcast.usecases.discover._no_budget import _no_budget
from torrcast.usecases.reinforce.configure import _catalogue_port

if TYPE_CHECKING:
    from torrcast.ports.progress.progress import Progress


def _voice_reinforce(
    client: IndexerClient,
    query: str,
    lead: Picture,
    raw: list[RawResult],
    found: list[Picture],
    progress: Progress,
    titled: bool = False,
) -> tuple[list[RawResult], list[Picture], list[Picture]]:
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
        return raw, cluster(_catalogue_port().to_releases(raw)), found
    if _no_budget(client, phrase("reinforce.voice_reason", exact=exact), progress) is None:
        return raw, cluster(_catalogue_port().to_releases(raw)), found
    progress.phase(phrase("reinforce.search_phase", name=exact))
    extra = _ask(client, exact, progress)
    progress.phase("")
    want_orig = slugify(lead.original or "")
    keep = [
        row
        for row, rel in zip(extra, _catalogue_port().to_releases(extra), strict=True)
        if rel.original
        and slugify(rel.original) == want_orig
        and rel.year is not None
        and lead.year is not None
        and abs(rel.year - lead.year) <= 1
    ]
    merged = _catalogue_port().merge(raw, keep) if keep else raw
    if len(merged) == len(raw):
        return raw, cluster(_catalogue_port().to_releases(raw)), found
    pictures = cluster(_catalogue_port().to_releases(merged))
    wider = pick_franchise(query, pictures)
    was = sum(len(p.releases) for p in found)
    now = sum(len(p.releases) for p in wider)
    if now <= was:
        # Прибавка ушла мимо картины - тогда второго захода как будто и не было.
        return raw, cluster(_catalogue_port().to_releases(raw)), found
    progress.note(phrase("reinforce.voice_note", title=_title(lead), exact=exact, now=now))
    return merged, pictures, wider
