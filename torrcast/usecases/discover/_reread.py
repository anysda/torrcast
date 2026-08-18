"""Второй заход по той же строке: забытая раскладка, цифра в названии и номер сезона.

Зовёт их круг поиска (:func:`torrcast.usecases.discover._search._search`) - каждый ровно
там, где иначе человек уже читал бы отказ. Живут они рядом с ним, а не в команде показа:
честный импорт из команды дал бы настоящий цикл - показ и сам зовёт круг поиска.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.cluster import cluster
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.domain.reads_season import reads_season
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.domain.unswap_layout import unswap_layout
from torrcast.ports.progress import Progress
from torrcast.ports.torrent_catalogue import IndexerClient, RawRow
from torrcast.usecases.discover._ask import _ask
from torrcast.usecases.discover._no_budget import _no_budget

if TYPE_CHECKING:
    from torrcast.ports.choice_types import Args


def _relayout(
    client: IndexerClient, query: str, name: str, index: int | None, progress: Progress
) -> tuple[str, str, int | None, list[RawRow]]:
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
    client: IndexerClient, query: str, name: str, raw: list[RawRow], progress: Progress
) -> tuple[list[RawRow], list[Picture], list[Picture]]:
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
    if _no_budget(client, f"поиск «{query}» целиком", progress) is None:
        return raw, cluster(_search_state._search_catalogue.to_releases(raw)), []
    progress.phase(f"поиск «{query}»")
    merged = _search_state._search_catalogue.merge(raw, _ask(client, query, progress))
    progress.phase("")
    if len(merged) == len(raw):
        return raw, cluster(_search_state._search_catalogue.to_releases(raw)), []
    pictures = cluster(_search_state._search_catalogue.to_releases(merged))
    found = pick_franchise(query, pictures)
    if not found:
        return raw, cluster(_search_state._search_catalogue.to_releases(raw)), []
    progress.note(f"по «{name}» картины не нашлось - искал «{query}» целиком")
    return merged, pictures, found


def _season_asked(found: list[Picture], name: str, pictures: list[Picture]) -> bool:
    """Номер запроса просит СЕЗОН сериала, а не часть франшизы (TC-363).

    Спрашивается ровно то же, что решил разбор (:func:`~torrcast.parse.reads_season`), и
    сверяется его ответом: номер отдан сериалам франшизы, а не картине по счёту. Двух
    правил тут нет - есть одно, и cli лишь читает, чем оно кончилось: номер должен
    доехать до сезонной машинерии, а знает про сезоны она, а не разбор.
    """
    if not found or any(picture.kind != "tv" for picture in found):
        return False
    # Голое имя: номер снят выше, поэтому пополнение меню продолжениями сюда доехало бы
    # молча и переспорило бы разбор (:func:`~torrcast.parse.pick_franchise`).
    return reads_season(pick_franchise(name, pictures, join_continuations=False))


def _season_reread(
    args: Args, name: str, index: int | None, found: list[Picture], pictures: list[Picture]
) -> Args | None:
    """Перечитать номер запроса сезоном: запрос «имя N» → «имя sNe1» (TC-363).

    Само правило - в :func:`_season_asked`; тут второй его половина: во что именно
    переписывается запрос, когда правило сработало. ``None`` - номер остался номером
    части, запрос не трогаем.

    Обе половины стоят рядом и зовутся ОДНОЙ функцией не для красоты. Читателей у выдачи
    двое - показ (:func:`~torrcast.cli._search`) и офлайн-переигровка
    (``scripts/poolreplay.py``, TC-397), - и пока прочтение было переписано в щупе своей
    копией, он строил планы по первому сезону там, где показ строил их по второму. Щуп,
    который меряет собственную копию правила, не меряет ничего.
    """
    if index is None or not _season_asked(found, name, pictures):
        return None
    return replace(args, query=[*name.split(), f"s{index}e1"])
