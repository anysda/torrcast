"""Выдача, когда добора не было: сказать, если год справки спорит с каталогом."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.proven_native import proven_native
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.domain.slugify import slugify
from torrcast.usecases.reinforce._aside import _aside
from torrcast.usecases.reinforce.configure import _catalogue_port

if TYPE_CHECKING:
    from torrcast.ports.progress.progress import Progress


def _as_is(
    raw: list[RawResult],
    found: list[Picture],
    about: Origin,
    progress: Progress,
    wide: Sequence[Picture] = (),
) -> tuple[list[RawResult], list[Picture], list[Picture]]:
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

    🔴 TC-770. ``wide`` - широкая выдача добора, который сторож
    :func:`~torrcast.usecases.discover._widened_subject._widened_subject` только что
    отверг за расширение предмета поиска. В меню, в очередь и в порядок отбора она не
    идёт - за это сторож и стоит, - но раздачи СВОЕЙ картины из неё больше не гибнут:
    их откладывает :func:`~torrcast.usecases.reinforce._aside._aside`, и спрашиваются они
    ровно там, где иначе человек услышал бы «русской дорожки не нашлось».

    ⚠️ Условия узкие нарочно. Строка говорится про ОДНУ картину - ту, что нашлась под этим
    именем в единственном числе. Во франшизе справка отвечает про первую часть, а в
    каталоге может лежать вторая: на «моане 2» широкий вариант этой сверки ругался бы на
    честную выдачу. Не знает года справка, картин несколько, годы сходятся - молчим.
    """
    from torrcast.domain.cluster import cluster

    for picture in found:
        if proven_native(about, picture.title):
            picture.native = True
    stays = (raw, cluster(_catalogue_port().to_releases(raw)), found)
    if wide:
        aside = [release for picture in wide for release in picture.releases]
        _aside(stays[1], aside)
        _aside(found, aside)
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
        phrase("reinforce.year_mismatch", found_year=found[0].year, about_year=about.year)
    )
    return stays
