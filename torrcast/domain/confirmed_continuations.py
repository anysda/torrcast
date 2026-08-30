"""Правило confirmed continuations; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.menu_order import menu_order
from torrcast.domain.picture import Picture
from torrcast.domain.unmarked import _unmarked


def confirmed_continuations(
    groups: dict[str, list[Picture]], key: str, franchise: list[Picture]
) -> list[Picture]:
    """Картины соседних групп, чьё латинское имя подтверждает ту же франшизу.

    🔴 TC-901. Русский ключ группы правило пускало с любым хвостом, а латинский корень
    требовало совпадающим ЦЕЛИКОМ, - и на этой несимметрии терялись «Моб Психо 100 ТВ-1..3»
    и «Токийский Гуль ТВ-1»: маркер вида приставал к обоим именам сразу, разводя один
    сериал по разным ключам.

    Поэтому хвост группы читается: если русский ключ отличается от ключа франшизы ТОЛЬКО
    маркером вида (:func:`~torrcast.domain.unmarked._unmarked`), латинскому имени разрешено
    продолжать корень, а не совпадать с ним. Ослабление держится ровно на закрытом списке
    маркеров: снаружи него по началу имени неотличимы «Оно приходит ночью» от «Оно» и
    «Титаник 666» от «Титаника», и раскрывать их нельзя.

    Год у такой картины бывает не назван вовсе, и якорь о ней не говорит ничего: пустой
    год это «неизвестно», а не «раньше базы». У картины с маркером он больше не приговор,
    у картины без маркера остаётся прежним требованием.
    """
    base = [p for p in franchise if p.kind != "other"]
    roots = {franchise_key(p.original) for p in base if p.original}
    roots.discard("")
    anchor = min((p.year for p in base if p.year is not None), default=None)
    if not roots or anchor is None:
        return []
    found: list[Picture] = []
    for grouped_key, items in groups.items():
        if grouped_key == key or not grouped_key.startswith(f"{key}-"):
            continue
        if grouped_key.startswith(f"{key}-и-"):
            continue
        marked = _unmarked(grouped_key) == key
        found += [p for p in items if _confirmed(p, roots, anchor, marked=marked)]
    if not found:
        return []
    was = menu_order(base)[0].key
    while found:
        top = menu_order(base + found)[0].key
        if top == was:
            break
        trimmed = [p for p in found if p.key != top]
        if len(trimmed) == len(found):
            return []
        found = trimmed
    return found


def _confirmed(picture: Picture, roots: set[str], anchor: int, *, marked: bool) -> bool:
    """Одна картина: подтверждает ли её латинское имя корень франшизы."""
    if picture.kind == "other" or not picture.original:
        return False
    if picture.year is None and not marked:
        return False
    if picture.year is not None and picture.year < anchor:
        return False
    original = franchise_key(picture.original)
    if original in roots:
        return True
    return marked and _rooted(original, roots)


def _rooted(original: str, roots: set[str]) -> bool:
    """Латинское имя продолжает корень: «tokyo-ghoul-a-tv» и «ova-tokyo-ghoul» это «tokyo-ghoul»."""
    return any(
        name == root or name.startswith(f"{root}-")
        for root in roots
        for name in (original, _unmarked(original))
    )


__all__ = ["confirmed_continuations"]
