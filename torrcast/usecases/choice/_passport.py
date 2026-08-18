"""Фоновый паспорт дефолтной картины: пускается до меню, забирается перед стартом."""

from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING

from torrcast.domain.picture import Picture
from torrcast.usecases.choice.configure import _environment_port

if TYPE_CHECKING:
    from torrcast.ports.choice_types import Origin, _Plan


class _Passport:
    """Фоновый паспорт дефолтной картины: :func:`_passport` пускает, :meth:`get` забирает.

    Справка (:func:`~torrcast.usecases.passport.Passport.of`) - независимое слово для гейта года
    выбранной картины (:func:`year_note`). Нужна она лишь к последней строке перед стартом, поэтому
    едет фоном, ровно в те секунды, что уходят на меню и прогрев. :meth:`get` дожидается её сам
    добор бюджетом ограничил, так что путь до меню она не держит.
    """

    def __init__(self, picture: Picture | None) -> None:
        self._picture = picture
        self._box: list[Origin] = []
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._picture is None:  # меню не было - и сверять нечего
            return
        self._thread = threading.Thread(target=self._work, daemon=True)
        self._thread.start()

    def _work(self) -> None:
        # Тип картины известен из выдачи (:attr:`Picture.kind`), и его подсказать надо:
        # у сериала и фильма разные статьи. Год выдачи - нет: см. :func:`year_note`.
        with contextlib.suppress(Exception):
            picture = self._picture
            if picture is None:
                return
            self._box.append(_environment_port().origin(picture.title, series=picture.kind == "tv"))

    def get(self) -> Origin:
        thread = self._thread
        if thread is not None:
            thread.join()
        return self._box[0] if self._box else _environment_port().empty_origin()


def _passport(plans: list[_Plan]) -> _Passport:
    """Пустить фоном добор паспорта верхней картины меню (:func:`year_note`).

    Только на меню из нескольких картин: одна картина - выбора не было, сверять нечего, и
    лишнего похода к справке на счастливом однокартинном пути не случается.
    """
    default = plans[0].picture if len(plans) >= 2 else None
    holder = _Passport(default)
    holder.start()
    return holder
