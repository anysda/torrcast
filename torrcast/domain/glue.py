"""Правило glue; используют модели и фасады разбора имён."""

from __future__ import annotations

import re

from torrcast.domain._name_data.data_2 import _ALTERNATIVE_PICTURE_RE, _ALTERNATIVE_TITLE_RE, _ROMAN
from torrcast.domain.about_the_picture import _about_the_picture
from torrcast.domain.adaptationless import _adaptationless
from torrcast.domain.compose import _compose
from torrcast.domain.editionless import _editionless
from torrcast.domain.formless import _formless
from torrcast.domain.glued_kind import _glued_kind
from torrcast.domain.glued_year import _glued_year
from torrcast.domain.in_digits import in_digits
from torrcast.domain.kin_pairs import _kin_pairs
from torrcast.domain.kind import Kind
from torrcast.domain.link import _link
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify


def glue(pictures: list[Picture]) -> list[Picture]:
    parent = list(range(len(pictures)))

    def identity(name: str) -> str:
        plain = re.sub("(?:-)?(?:в-)?3[дd]$", "", slugify(name)).rstrip("-")
        return re.sub(
            "(?<=-)(?:часть|part)-([ivx]{1,4})$",
            lambda match: (
                match.group(0)[: match.group(0).rfind("-") + 1]
                + str(_ROMAN.get(match.group(1), match.group(1)))
            ),
            plain,
        )

    def one_name(name: str) -> str:
        # Слово формы снимается ТОЛЬКО там, где вид уже сошёлся: в ведре он стоит ключом.
        # Между видами оно не шум, а единственная улика: «Naruto Shippuuden Movie» отличает
        # от сериала «Naruto Shippuuden» ровно слово «Movie», и сняв его, склейка увела бы
        # фильм в пул сериала - подмену, а не двойника.
        #
        # Хвост издания снимается ПЕРЕД словом формы: «Gekijouban X. Полное издание»
        # должно дойти до голого «x», а порядок наоборот оставил бы слово формы
        # прикрытым хвостом и до него бы не добрался.
        #
        # Примета экранизации («The Animation») снимается ЗДЕСЬ ЖЕ, но по своему списку:
        # о виде она не говорит, и потому её же снимает ключ франшизы. Слово формы там
        # снимать нельзя, а тут - нужно, и поэтому списка два, а не один.
        return _adaptationless(_formless(_editionless(identity(name))))

    def alternative_release(release: Release) -> bool:
        title = release.raw_name.split(" / ", 1)[0]
        return bool(
            _ALTERNATIVE_PICTURE_RE.search(release.raw_name) or _ALTERNATIVE_TITLE_RE.search(title)
        )

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = (root(a), root(b))
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    alternative = [
        bool(p.releases) and all(alternative_release(r) for r in p.releases) for p in pictures
    ]
    disputed = {
        (picture.kind, slugify(picture.title), picture.year)
        for picture in pictures
        if picture.original
        and len(
            {
                slugify(other.original)
                for other in pictures
                if other.original
                and other.kind == picture.kind
                and (other.year == picture.year)
                and (slugify(other.title) == slugify(picture.title))
            }
        )
        > 1
        and any(
            len(slugify(other.original)) == 1
            for other in pictures
            if other.original
            and other.kind == picture.kind
            and (other.year == picture.year)
            and (slugify(other.title) == slugify(picture.title))
        )
    }
    named: dict[tuple[Kind, str, bool], list[int]] = {}
    for i, picture in enumerate(pictures):
        contested = (picture.kind, identity(picture.title), picture.year) in disputed
        names = set() if contested else {one_name(picture.title)}
        if picture.original:
            names.add(one_name(picture.original))
        if not contested:
            names |= {in_digits(name) for name in names if name}
        for name in names:
            if name:
                named.setdefault((picture.kind, name, alternative[i]), []).append(i)
    for same in named.values():
        _link(pictures, same, union)
    lone: dict[tuple[Kind, str, bool], list[int]] = {}
    for i, picture in enumerate(pictures):
        if picture.original:
            continue
        for name in {(slug := one_name(picture.title)), in_digits(slug)}:
            if name:
                lone.setdefault((picture.kind, name, alternative[i]), []).append(i)
    for i, picture in enumerate(pictures):
        # Псевдоним спрашивается ТОЙ ЖЕ нормализацией, что и ключ ведра: ведро заведено
        # по one_name(), а псевдоним лежит голым слагом, и без выравнивания сторон
        # «Chainsaw Man - The Movie: Reze Arc» перестал бы узнавать своё же ведро.
        for alias in {one_name(a) for a in picture.aliases}:
            for name in (alias, in_digits(alias)):
                if (
                    bucket := lone.get((picture.kind, name, alternative[i]))
                ) is not None and i not in bucket:
                    bucket.append(i)
    for same in lone.values():
        _link(pictures, same, union)

    def subtitle(name: str) -> str:
        head, colon, tail = name.partition(":")
        return identity(tail) if colon and head.strip() else ""

    def one_picture_two_kinds(a: Picture, b: Picture) -> bool:
        # Вид тут и есть весь спор: одно имя, один год, а каталог развёл фильм и сериал.
        # Сойтись им мало имени - «Трансформеры» 2007 года это и фильм, и мультсериал
        # «Transformers: Animated», - поэтому спрашивается оригинал: он либо тот же, либо
        # стоит подзаголовком у соседа («Mater's Tall Tales» в «Cars Toon: Mater's Tall
        # Tales»). Приставка соседом не считается: ею и отличается «Animated».
        if a.kind == b.kind or "other" in (a.kind, b.kind) or not (a.original and b.original):
            return False
        # Оригинал у бонуса стоит от самой картины, и отличает стороны только русское имя:
        # «Евангелион Нового Поколения: дополнительные материалы» это работа О картине, и
        # в её пуле ему места нет - как и `_editionless` такой хвост снимать не смеет.
        if _about_the_picture(a.title) is not _about_the_picture(b.title):
            return False
        mine, theirs = identity(a.original), identity(b.original)
        return mine == theirs or mine == subtitle(b.original) or theirs == subtitle(a.original)

    def two_kinds_one_bare_name(a: Picture, b: Picture) -> bool:
        # Оригинала нет ни у одной стороны, и спросить его, как выше, не у кого: всё, что
        # о картине сказано, - русское имя и год. Совпали оба буквально - это одна работа,
        # разведённая каталогом по виду: «Место встречи изменить нельзя» 1979 года стоял в
        # меню фильмом и сериалом сразу, и раздачи одной картины лежали в двух пулах.
        #
        # Вид «other» - ведро «ни фильм, ни сериал», и лежит в нём не-видео: единственная
        # раздача под ним у «Семнадцати мгновений весны» 1973 года это «Михаил Таривердиев
        # OST (1973) APE», саундтрек. Пустив его, продукт подсунул бы зрителю APE-рип
        # вместо кино, - поэтому вид спрашивается дважды: он разный, и он не «other».
        return (
            a.kind != b.kind and "other" not in (a.kind, b.kind) and not (a.original or b.original)
        )

    # Сторона без года идёт вторым заходом: к этому времени стороны с годом уже сведены,
    # и «одна ли картина стоит под этим оригиналом» - вопрос с ответом, а не гадание.
    for undated in (False, True):
        for i, j in _kin_pairs(pictures, identity, root, named=True, undated=undated):
            if one_picture_two_kinds(pictures[i], pictures[j]):
                union(i, j)
    for i, j in _kin_pairs(pictures, identity, root, named=False):
        if two_kinds_one_bare_name(pictures[i], pictures[j]):
            union(i, j)
    groups: dict[int, list[int]] = {}
    for i in range(len(pictures)):
        groups.setdefault(root(i), []).append(i)
    out: list[Picture] = []
    for members in groups.values():
        if len(members) == 1:
            out.append(pictures[members[0]])
            continue
        merged = sorted(
            (pictures[i] for i in members),
            key=lambda p: (-len(p.releases), p.title, p.original or ""),
        )
        releases = [r for p in merged for r in p.releases]
        kind = _glued_kind(merged)
        year = _glued_year(kind, merged, releases)
        fresh = _compose(kind, year, releases)
        fresh.also = next((p.title for p in merged if slugify(p.title) != slugify(fresh.title)), "")
        out.append(fresh)
    return out


__all__ = ["glue"]
