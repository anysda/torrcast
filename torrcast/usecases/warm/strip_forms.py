"""Отдаёт место раздела, занятое своими же полками прежних форм ключа."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import torrcast.usecases.warm._state as _state
from torrcast.usecases.warm._vault_disk import _dirs, _form, _title, _touched, _weigh


class _Vault(Protocol):
    @property
    def root(self) -> Path: ...

    @property
    def key(self) -> str: ...

    @property
    def keep(self) -> frozenset[str]: ...

    @property
    def form(self) -> str: ...

    @property
    def floor(self) -> int: ...

    def free(self) -> int: ...


def strip_forms(vault: _Vault, need: int) -> int:
    """Освободить под ``need`` байт место прежних форм ключа; вернуть отданные байты.

    Сменилась форма ключа - и полка, прогретая прежней сборкой, лежит сиротой: имени, под
    которым её ищут, больше никто не назовёт, а место она держит. Замер на стенде
    05-09-2026: 10.7 ГБ прогретого прежней формы при 2.8 ГБ свободных, и прогрев стоял
    навсегда - бюджет эти гигабайты не вытеснял (полка легче бюджета), а пол свободного
    места только отказывал. Сам себя показ из этого не выводил, и лечилось это руками.

    🔴 Вытесняется тут не «что-нибудь чужое», а только то, что не найдётся больше ни по
    одному ключу ЭТОЙ сборки (:data:`torrcast.usecases.warm.key_form.KEY_FORM`). Полка,
    заведённая этой же сборкой, не трогается никогда, чем бы она ни была занята: под ней
    может идти живой показ, и его прогретое дороже нашего места. Свою и соседнюю серию
    (:attr:`torrcast.usecases.warm.vault.Vault.keep`) не трогаем тем более.

    Порог свободного места (:data:`torrcast.usecases.warm.settings.FREE_FLOOR`) при этом
    остаётся ровно там, где стоял: чинится не он, а неумение отдать сиротское место.
    """
    mine = {vault.key, *vault.keep}
    stale = sorted(
        (path for path in _dirs(vault.root) if path.name not in mine and _form(path) != vault.form),
        key=_touched,
    )
    freed = 0
    while stale and need + vault.floor > vault.free():
        gone = stale.pop(0)
        # Вес и имя снимаем ДО сноса: после него сказать, что именно и на сколько
        # освободили, уже не по чему, а в ленте это и есть вся ценность записи.
        weight = _weigh(gone)
        _state._environment.emit(
            "evict", key=gone.name, freed=weight, need=int(need), title=_title(gone)
        )
        _state._environment.remove_tree(gone)
        freed += weight
    return freed
