"""Второй круг уточнённым запросом «имя + год из справки»; зовёт сценарий поиска."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalog_has_name import catalog_has_name
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.ports.passport_source import PassportSource
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.choice._named import _title
from torrcast.usecases.discover._ask import _ask
from torrcast.usecases.discover._asked_kind import _asked_kind
from torrcast.usecases.discover._no_budget import _no_budget
from torrcast.usecases.reinforce._leading import _leading
from torrcast.usecases.reinforce.configure import _catalogue_port, _passport_port

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.ports.progress.progress import Progress


def _ceiling_reinforce(
    client: IndexerClient,
    name: str,
    args: Args,
    raw: list[RawResult],
    pictures: list[Picture],
    found: list[Picture],
    progress: Progress,
    *,
    passport: PassportSource | None = None,
) -> tuple[list[RawResult], list[Picture], list[Picture]]:
    """Второй круг с УТОЧНЁННЫМ запросом «имя + год из справки». Не помогло - как было.

    Голое имя индексер закрыл потолком, поэтому спрашиваем точнее: год сужает выдачу
    так, что нужная картина влезает под потолок (по «девять» - сотня чужих строк, по
    «девять 2009» - 22 строки, и «Девять» (2009) среди них). Год берётся только из
    справки: выдача года не знает, а выдумывать его нечем.

    Ограждения - те же, что у добора вторым языком (:func:`_second_language`):

    * круг платится из остатка цели (:func:`_no_budget`);
    * имя, за которое справка не ручается (:attr:`~torrcast.domain.facts.origin.Origin.guessed`),
      ничего не решает - уточнения не бывает (гейт TC-253);
    * берутся только картины, подписанные ТОЧНО спрошенным именем
      (:func:`~torrcast.domain.catalog_has_name.catalog_has_name`), и только тех, чей год не спорит
      со справкой. Ничего такого не приехало - остаётся прежняя выдача, хуже не бывает.

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

    reason = phrase("reinforce.refine_reason", name=name)
    if (spare := _no_budget(client, reason, progress)) is None:
        return raw, pictures, found
    about = (passport or _passport_port())(
        name, series=_asked_kind(_leading(found), args), budget=spare
    )
    if about.guessed or about.year is None:
        return raw, pictures, found
    refined = f"{name} {about.year}"
    progress.phase(phrase("reinforce.search_phase", name=refined))
    merged = _catalogue_port().merge(raw, _ask(client, refined, progress))
    progress.phase("")
    if len(merged) == len(raw):
        return raw, pictures, found
    wider = cluster(_catalogue_port().to_releases(merged))
    vouched = [
        p
        for p in wider
        if catalog_has_name(name, [p]) and (p.year is None or abs(p.year - about.year) <= 1)
    ]
    if not vouched:
        return raw, pictures, found
    kept = [p for p in found if p.key not in {q.key for q in vouched}]
    first = vouched[0]
    year = str(first.year) if first.year is not None else phrase("reinforce.year_unknown")
    progress.note(
        phrase("reinforce.ceiling_note", name=name, refined=refined, title=_title(first), year=year)
    )
    return merged, wider, vouched + kept
