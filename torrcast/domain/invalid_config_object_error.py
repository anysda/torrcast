"""Ошибка настройки, верхним слоям которой нужен путь отдельно от текста."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.torrcast_error import TorrcastError

if TYPE_CHECKING:
    from pathlib import Path


class InvalidConfigObjectError(TorrcastError, ValueError):
    """Настройка прочиталась как JSON, но не как объект.

    ``path`` лежит рядом с готовой строкой нарочно: жалобу собирает тот, кто читал
    файл, и собирает языком ПРОДУКТА, а битая настройка - это ровно тот случай, когда
    язык продукта взять неоткуда и он вырождается в английский
    (:func:`torrcast.adapters.filesystem.state.chosen_language.chosen_language`).
    Телеграм-бот называет эту же беду заново (:func:`tgbot.i18n._failure_detail`) -
    а собрать её заново можно только из пути, не из чужого готового текста.

    ``ValueError`` в предках сохраняет прежний договор ``tgbot.config.Config._stored``:
    запись поверх неразобранного файла роняли именно им, и ловившие это места не
    переписываются.
    """

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(message)
