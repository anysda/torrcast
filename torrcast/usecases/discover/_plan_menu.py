"""Планы меню поиска: порядок картин, память и добор сведены в один шаг."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.menu_order import menu_order
from torrcast.ports.journal.slot import journal
from torrcast.ports.state_store.slot import store as watch_store
from torrcast.usecases.discover._catalog_note import _catalog_note
from torrcast.usecases.discover.kin_line import _kin
from torrcast.usecases.discover.season_gaps import season_gaps
from torrcast.usecases.reinforce._leading import _leading
from torrcast.usecases.reinforce.plan_for import plan_for
from torrcast.usecases.select._measured_runtime import _measured_runtime
from torrcast.usecases.select._studio_seen import _studio_seen

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.config import Config
    from torrcast.domain.picture import Picture
    from torrcast.domain.profile import Profile
    from torrcast.ports.progress.progress import Progress
    from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
    from torrcast.usecases.select.plan import Plan


def _plans(
    found: list[Picture],
    pictures: list[Picture],
    args: Args,
    config: Config,
    profile: Profile,
    name: str,
    client: IndexerClient,
    progress: Progress,
) -> tuple[list[Picture], list[Plan]]:
    """Собрать планы меню и метаданные, которые понадобятся каждому из них."""
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
    for picture in found:
        # 🔴 TC-819. Знаменатель битрейта сперва спрашивается у паспорта файла - у уже
        # начатой картины он лежит в записи состояния, и прикидке по типу («серия это
        # 45 минут») верить рядом с замером незачем: на «Киберпанке» она занизила вес
        # релиза вдвое, и ворота пустили его как «под потолком приёмника» в сплошной
        # перекод на весь показ. Молчит и паспорт - прикидка идёт в дело под своим
        # именем: источник знаменателя у каждого плана уходит в след.
        measured = _measured_runtime(seen, picture.key, remembered)
        plan = plan_for(
            picture,
            args,
            config,
            profile,
            runtime=measured,
            studio=_studio_seen(seen, picture.key, remembered),
        )
        journal().emit(
            "search",
            "runtime",
            title=picture.title,
            secs=round(plan.runtime),
            src="guess" if plan.runtime_estimated else "passport",
        )
        if plan.ranked:
            plans.append(plan)
    if plans and (note := _catalog_note(name, plans, args)):
        progress.note(note)
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
    return found, plans
