"""Строки подсказчика IMDb: сверка года и рода, картинка строки, ужатый адрес.

Правила одной строки ответа собраны отдельно от цепочки (:mod:`~torrcast.adapters.wiki.
imdb_poster`): она рассуждает о путях к картине (карта, имя, id), а тут - только то, что
можно спросить у одной строки, не зная, откуда она приехала.
"""

from __future__ import annotations

import re
from typing import Any, Final

from torrcast.adapters.wiki.poster_files import POSTER_WIDTH
from torrcast.domain.facts.ask import Ask
from torrcast.domain.facts.lying_down import lying_down
from torrcast.domain.slugify import slugify

#: Какие роды IMDb считаются нашими двумя. Серия сериала, игра и клип - не картины вовсе,
#: и обложка игры под именем одноимённого фильма была бы ровно той чужой картинкой.
KINDS: Final = {
    "movie": frozenset({"movie", "tvMovie", "tvSpecial", "short", "video"}),
    "tv": frozenset({"tvSeries", "tvMiniSeries"}),
}


def _fits(ask: Ask, row: dict[str, Any]) -> bool:
    """Годится ли эта картина IMDb под просьбу: род и год сверены точно.

    Год сверяется РОВНО, без допуска. Допуск стоил бы дороже, чем даёт: у сериала
    подсказчик называет год начала, и «сдвинуться на единицу» означало бы пустить соседний
    сезон чужой картины, а такая ошибка человеку видна, в отличие от пропущенной картинки.
    """
    return bool(
        str(row.get("id", "")).startswith("tt")
        and _image(row)
        and str(row.get("qid", "")) in KINDS[ask.kind]
        and row.get("y") == ask.year
    )


def _image(row: dict[str, Any] | None) -> str:
    """Адрес картинки этой картины; её нет или она лежачая - пустая строка.

    🔴 Подсказчик отдаёт стороны картинки тем же полем: у «Desperate Housewives:
    Oprah Winfrey Is the New Neighbor» это 1242x866, кадр шоу, а не обложка. Wikipedia
    такую лежачую картинку уже отсеивала (:mod:`torrcast.domain.facts.poster_address`),
    а IMDb, второй источник, - нет; пустота тут читается зовущим как «картинки нет»,
    и он пробует второй путь, каким находит постер без картинки по id
    (:meth:`~torrcast.adapters.wiki.imdb_poster.ImdbPoster._by_id`).
    """
    picture = row.get("i") if isinstance(row, dict) else None
    found = picture.get("imageUrl") if isinstance(picture, dict) else None
    if not isinstance(found, str) or not found:
        return ""
    if isinstance(picture, dict) and lying_down(picture.get("width"), picture.get("height")):
        return ""
    return found


def _sized(address: str) -> list[str]:
    """Тот же постер шириной с остальные, а следом - как есть.

    Сырой адрес отдаёт исходник в несколько мегабайт: столько к человеку в список едет
    десяток раз. Ширину просят прямо в имени файла, и оба адреса называются по порядку -
    ужатый отдельно не существует, но правило имён у чужого хоста может и смениться.
    """
    small = re.sub(r"\._V1_[^/]*\.jpg$", f"._V1_UX{POSTER_WIDTH}_.jpg", address)
    return list(dict.fromkeys(one for one in (small, address) if one))


def _same_name(text: str, row: dict[str, Any]) -> bool:
    """Источник назвал картину ровно тем именем, каким спросили."""
    return slugify(str(row.get("l") or "")) == slugify(text)


def _otherwise_named(text: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Строки-ТЕЗКИ по другому имени: подсказчик сводит и альтернативные названия.

    «Un dramma borghese» он разрешает в «Mimi», а «Enfrentados Marfil» - в «Drawn
    Together»: итальянское и испанское имена записаны у него вторыми названиями этих же
    картин, и единственный ответ с совпавшими годом и родом на ПОЛНОЕ имя - это она.
    Однословному запросу тут не верим: «Brat» подсказчик сшивает текстово с чужим
    «Father Mother Sister Brother», и год с родом такую сшивку не различают. Имени,
    вложенному в спрошенное (или наоборот), тоже: «Paradise» это не «Paradise Hills».
    """
    if len(text.split()) < 2:
        return []
    wanted = slugify(text)
    return [row for row in rows if not _nested(wanted, slugify(str(row.get("l") or "")))]


def _nested(first: str, second: str) -> bool:
    """Один слаг внутри другого: признак соседки с добавленным словом, а не тёзки."""
    return first in second or second in first


__all__ = ["KINDS", "_fits", "_image", "_otherwise_named", "_same_name", "_sized"]
