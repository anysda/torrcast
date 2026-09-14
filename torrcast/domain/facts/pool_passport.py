"""Чей паспорт у короткого имени: статьи справки или картины, которую выдача и карта зовут им."""

from __future__ import annotations

from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.patterns import _CYRILLIC
from torrcast.domain.facts.proof_in_map import KnownPictures, proof_in_map
from torrcast.domain.facts.settings import SOURCE_MAP
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify


def pool_passport(about: Origin, name: str, found: list[Picture], imdb: KnownPictures) -> Origin:
    """Паспорт картины, которую доказали выдача и карта вместе, если статья про другую.

    🔴 Поиск Википедии по «Мы» отвечал латышской документалкой «Mēs?» (1989), а в выдаче под
    этим именем лежал «Мы» (Us, 2019): второй круг уходил за «Мы 1989», гейт отвергал его, и
    человек читал «ничего не нашлось». У справки одно свидетельство - статья, найденная по
    слову, - а у картины выдачи два независимых: точное имя с годом в раздачах и та же тройка
    «имя, тип, год» в офлайн-карте IMDb (:func:`proof_in_map`).

    Спор решает известность, как у TMDb ``search/movie`` и Radarr (имя, год, популярность):
    статья сохраняет паспорт, если год её сходится с картиной выдачи или карта знает её
    картину не хуже. «Восхождение» Шепитько (1977, 12 596 голосов) так и держит имя против
    китайского «The Climb» (2019, 5 636), даже когда в выдаче лежит только второй. Статья,
    которой карта не знает вовсе, уступает доказанной картине.

    ⚠️ Граница: карта молчит о картинах выдачи (нет года, русская картина без строки IMDb,
    выгрузка не доехала) - паспорт остаётся ровно тем, что сказала справка.
    """
    wanted = slugify(name)
    exact = [p for p in found if p.year is not None and slugify(p.title) == wanted]
    if about.year is not None and any(_near(p.year, about.year) for p in exact):
        return about
    proofs = [proof for p in exact if (proof := proof_in_map(p, imdb)) is not None and proof.votes]
    best = max(proofs, key=lambda proof: proof.votes, default=None)
    if best is None or _article_votes(about, name, imdb) >= best.votes:
        return about
    return _origin(best)


def _near(year: int | None, other: int) -> bool:
    return year is not None and abs(year - other) <= 1


def _article_votes(about: Origin, name: str, imdb: KnownPictures) -> int:
    """Голоса картины статьи по карте: то же имя и её год ± 1; года нет - сравнивать нечем."""
    if about.year is None:
        return 0
    year = about.year
    rows = [row for row in imdb(about.name or name) if _near(row.year, year)]
    return max((row.votes for row in rows), default=0)


def _origin(proof: MapPicture) -> Origin:
    latin = "" if _CYRILLIC.search(proof.original) else proof.original
    return Origin(title=latin, year=proof.year, name=proof.name, source=SOURCE_MAP)


__all__ = ["pool_passport"]
