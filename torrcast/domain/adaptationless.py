"""Правило adaptationless; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data.data_2 import _ADAPTATION_WORDS


def _adaptationless(key: str) -> str:
    """Ключ без слова-приметы экранизации: «X The Animation» и «X» - одна работа.

    🔴 Номер за словом тут НЕ трогается, и этим правило отличается от
    :func:`~torrcast.domain.formless._formless`. За словом формы стоит номер ЧАСТИ
    («Naruto Movie 3»), и снять его - подменить картину; за словом экранизации стоит
    номер СЕРИИ («Sakusei Byoutou The Animation - 10»), и он к имени картины не
    относится вовсе - его снимает разбор серий, а не эта стрижка.

    Пустой остаток не отдаётся: ключ «the-animation» это всё, что о картине сказано.
    """
    parts = key.split("-")
    for start in range(len(parts) - 1):
        if "-".join(parts[start : start + 2]) not in _ADAPTATION_WORDS:
            continue
        kept = parts[:start] + parts[start + 2 :]
        return "-".join(kept) if kept else key
    return key


__all__ = ["_adaptationless"]
