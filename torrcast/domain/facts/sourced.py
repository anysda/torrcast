"""Подпись ответа справки его источником; зовёт сценарий паспорта."""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.facts.origin import Origin


def sourced(found: Origin, source: str) -> Origin:
    """Отметить, чем отвечена справка, - если она вообще ответила и ещё не подписана.

    Подписывает тот, кто ЗНАЕТ источник, то есть место вызова: сам по себе паспорт
    рассказать этого не может. Уже подписанное не переподписывается - иначе ответ карты,
    пришедший из :func:`origin_now` последним шагом, выдал бы себя за Википедию.
    """
    if not found or found.source:
        return found
    return replace(found, source=source)
