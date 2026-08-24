"""Второй заход тем же названием на латинице: добор по оригиналу картины."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.alt_query import alt_query
from torrcast.domain.cluster import cluster
from torrcast.domain.facts.origin import Origin
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.domain.transliterate import transliterate
from torrcast.ports.progress.progress import Progress
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover._asked_kind import _asked_kind
from torrcast.usecases.discover._passport_pick import _passport_pick
from torrcast.usecases.discover._query_note import _query_note
from torrcast.usecases.discover._second_budget import _second_budget
from torrcast.usecases.discover._second_circle import _second_circle
from torrcast.usecases.discover._second_hearsay import _second_hearsay
from torrcast.usecases.discover._second_origin import _second_origin
from torrcast.usecases.discover._second_wider import _second_wider
from torrcast.usecases.reinforce._as_is import _as_is
from torrcast.usecases.reinforce._leading import _leading
from torrcast.usecases.reinforce._twin import _twin
from torrcast.usecases.reinforce.same_picture import same_picture

if TYPE_CHECKING:
    from torrcast.domain.args import Args


def _second_language(
    client: IndexerClient,
    query: str,
    args: Args,
    raw: list[RawResult],
    found: list[Picture],
    progress: Progress,
    titled: bool = False,
    *,
    passport: Callable[..., Origin] | None = None,
) -> tuple[list[RawResult], list[Picture], list[Picture]]:
    """Русский запрос дал пусто или тощий пул - переспросить тем же названием на латинице.

    Индексер ищет по имени раздачи, поэтому «Психо» приносит десяток русских имён, а
    сорок раздач ``Psycho.1960.*`` остаются за бортом - и человек либо смотрит 576p, либо
    (как на «Птицах») не получает ни одного годного релиза. Догадываться, что надо
    набрать латиницей, он не обязан: название на латинице лежит в первой же выдаче,
    :func:`~torrcast.domain.alt_query.alt_query` его оттуда и достаёт.

    Второй заход стоит ещё одного круга по индексерам, поэтому он не всегда, а только на
    тощем пуле: на полной выдаче (порог :data:`~torrcast.domain.thin_pool.THIN_POOL`) поиск остаётся
    ровно таким, каким был. Цена круга - обычно 0.5-1.5 с, но ровно та же, что у первого:
    если индексер молчит, круг стоит его личного бюджета
    (:data:`~torrcast.domain.indexer_budget.QUORUM_TIMEOUT`), и тогда добор виден человеку секундами
    ожидания. Обещать «1-3 с» тут нельзя: замеры на живом стенде давали и 101.6-102.1 с -
    столько круг стоил, пока молчание одного индексера ждали общим запросом.

    🔴 TC-386. **Отмены по бюджету у добора нет** (:func:`_second_budget`): пол бюджета
    круга - целая цель (:attr:`~torrcast.adapters.prowlarr.prowlarr.Prowlarr.cap_floor`), а
    съеденный остаток не отменяет заход, а объявляется строкой.

    Запросы идут последовательно, а не парой: второе имя достаётся из ПЕРВОЙ выдачи, до
    неё его просто нет. И уж точно не тем же именем: на латинском запросе оригинал из
    выдачи совпадает с самим запросом, и круг уходил целиком впустую - на живом стенде
    это стоило 102 секунды до меню.

    Строка вердикта печатается ПОСЛЕ строки того круга, о котором она говорит: ``note``
    выходит сразу, а строка фазы - только когда фазу закрыли, и в прежнем порядке «не
    беру» стояло перед «поиск… 102.1 с». Читалось это как противоречие: сначала отказ,
    а следом будто бы удавшийся второй поиск, из которого и выросло меню.

    Выдачи склеиваются, а не заменяются: русские имена несут озвучки и оригинал, по
    которому кластер и сшивает оба языка в одну картину. Если добор ничего не дал или
    картину после него не нашли, остаётся прежний результат - хуже стать не может.

    🔴 **Гейт: добор не вправе подменить картину.** Русское имя картину не определяет.
    «Восхождение» - это и фильм Шепитько 1977 года, и китайский 2019-го, подписанный
    тем же словом; оригинал ``The Climbers`` лежал прямо в русской выдаче, добор
    переспрашивал им и приносил два десятка раздач чужого кино с дорожкой ``und``.
    Раздач становилось больше, прежней проверке этого хватало, и человек молча получал
    не тот фильм. Поэтому мало «стало больше» - сверяется САМА КАРТИНА
    (:func:`same_picture`), а привязку приехавшего к спрошенной картине держит
    :func:`_second_wider`. Расхождение или сомнение - добора не было: честное
    «не нашлось» лучше чужого фильма.

    ⚠️ Право у гейта ровно одно - НЕ ДОБАВИТЬ своё. Выбросить то, что нашёл первый,
    русский запрос, он не вправе: отказ от добора возвращает прежнюю выдачу целиком
    (:func:`_as_is`), а не пустоту.

    🔴 TC-253. **Пустая русская выдача - гейт остаётся без опоры.** Сверять добор не с
    чем: картины до него не было, и :func:`same_picture` вырождается в вопрос о
    ПРОИСХОЖДЕНИИ имени, а про картину происхождение не говорит ничего. Чем тогда
    доказывается имя добора и когда за ним не идут вовсе - :func:`_second_hearsay`.

    ⚠️ ``titled`` - каталог уже сказал, что хвостовая цифра это часть НАЗВАНИЯ, а не номер
    части (:func:`_titled_number`). Тогда обрубок «бен» не годится ни справке, ни строке
    добора: по нему справка отвечает про «Бен-Гур», и второй заход уходит за чужой
    картиной. Спрашиваем всей строкой - справка знает «Бен 10» и отдаёт ``Ben 10``.
    """
    name, index = (query, None) if titled else split_franchise_index(query)
    budget = _second_budget(client, name, found, progress)
    pool = [r for p in found for r in p.releases] or _search_state._search_catalogue.to_releases(
        raw
    )
    lead = _leading(found)
    about = _second_origin(
        passport or _search_state._search_passport, name, _asked_kind(lead, args), index, budget
    )
    alt = alt_query(name, pool, about.title, about.name)
    hearsay = _second_hearsay(name, alt, about)
    if hearsay is None:
        # Справка нашла лишь похожее имя - это другая картина, и за ней не идут вовсе.
        progress.phase("")
        progress.note(
            f"по «{name}» справка нашла лишь похожее имя «{about.name}» - за чужой картиной не иду"
        )
        return _as_is(raw, found, about, progress)
    first_pictures = cluster(_search_state._search_catalogue.to_releases(raw))
    if (named := _passport_pick(first_pictures, about, found)) is not None:
        return raw, first_pictures, named
    said = _query_note(name, alt, pool, about)
    # Тем же именем второй раз ходить незачем: на «cast cars» оригинал из выдачи - «Cars»,
    # и это ещё один полный круг по всем индексерам (на живом стенде - до 102 секунд, если
    # в круге кто-то молчит) ради той же самой выдачи. Регистр и разделители имя не меняют,
    # поэтому сверяем по слагу.
    if not alt or slugify(alt) == slugify(name):
        return _as_is(raw, found, about, progress)
    merged = _second_circle(client, name, alt, index, about, found, raw, progress)
    # Круг кончился - закрываем его строку прямо здесь. Всё, что скажем дальше, это его
    # итог, а `note` печатается сразу, тогда как строка фазы ждёт закрытия фазы: без этого
    # вердикт «не беру» выходил ПЕРЕД строкой «поиск «Cars»... 102.1 с», и человек читал два
    # несвязанных сообщения как противоречие - отказ, а следом будто бы удавшийся поиск.
    progress.phase("")
    if len(merged) == len(raw):
        outcome = f"добор по «{alt}» ничего не дал"
        progress.note(f"{said}; {outcome}" if said else outcome)
        return _as_is(raw, found, about, progress)
    pictures = cluster(_search_state._search_catalogue.to_releases(merged))
    # Одна новая картина бывает второй, несклеившейся языковой половиной той же картины.
    # Всё сверх неё - оригинал расширил предмет поиска вместо уточнения.
    if len(pictures) > len(first_pictures) + 1:
        outcome = (
            f"добор по «{alt}» привёз больше картин: {len(pictures)} вместо "
            f"{len(first_pictures)} - остаюсь на выдаче по «{name}»"
        )
        progress.note(f"{said}; {outcome}" if said else outcome)
        return _as_is(raw, found, about, progress)
    # Транслит - это сами слова запроса, чужого фильма он принести не может; оригинал из
    # справки отвечает про ту самую картину. А вот оригинал из выдачи ничем не подтверждён.
    proven = bool(about.title) or alt == about.name or alt == transliterate(name)
    wider, vouched = _second_wider(pictures, query, alt, index, about, proven)
    was = sum(len(p.releases) for p in found)
    now = sum(len(p.releases) for p in wider)
    if now <= was:
        # Прибавка не в раздачах картины, а в чужих строках выдачи: широкий пул сдвинул бы
        # нумерацию франшизы («дилижанс 1» уехал бы с 1939 года на 1936) и ничего не дал
        # взамен. Тогда второго захода как будто и не было.
        outcome = f"добор по «{alt}» новых раздач картины не дал"
        progress.note(f"{said}; {outcome}" if said else outcome)
        return _as_is(raw, found, about, progress)
    # Имя добора от справки - она отвечает про ТУ САМУЮ картину, и спор идёт лишь о том,
    # доехала ли картина нужного года. Имя из выдачи ничем не подтверждено - там гейт строг
    # и сверяет вожака: именно он станет ответом.
    after = _twin(wider, about, lead) if proven else _leading(wider)
    if not vouched and not same_picture(lead, after, about, proven):
        outcome = f"по «{alt}» приехала другая картина - остаюсь на выдаче по «{name}»"
        progress.note(f"{said}; {outcome}" if said else outcome)
        return _as_is(raw, found, about, progress)
    details = []
    if hearsay:
        # Своего русского имени у статьи нет вовсе (аниме русская Википедия подписывает
        # латиницей), и подтвердить догадку справки было нечем. Выдать её за проверенное
        # молча нельзя: человек вправе знать, на чьём слове стоит эта выдача.
        details.append(f"имя «{alt}» взято со справки, сверить было не с чем")
    details.append(f"по-русски раздач {was} - добрал по «{alt}»: стало {now}")
    progress.note("; ".join(([said] if said else []) + details))
    return merged, pictures, wider
