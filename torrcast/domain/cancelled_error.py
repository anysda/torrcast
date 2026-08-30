"""Ошибка CancelledError; ею человек снимает свой же вопрос."""

from torrcast.domain.torrcast_error import TorrcastError


class CancelledError(TorrcastError):
    """Человек отменил вопрос сам: работы не было, отказа тоже нет. Код выхода 3.

    🔴 TC-926. Отдельный род, а не :class:`~torrcast.domain.not_found_error.NotFoundError`:
    «не нашли» и «передумал» - разные события, и склеить их значит соврать дважды. В
    консоли отказ печатается в stderr и уезжает в след ошибкой, а отменивший вопрос
    ничего не ломал; в чате же на отказ уходит строка «Каст не начался», и владелец
    увидел бы её на своё же нажатие кнопки.

    Наследуемся от :class:`~torrcast.domain.torrcast_error.TorrcastError`, чтобы
    раскрутка шла ровно тем же путём, каким шла раньше, - через ``finally`` в отборе, где
    снимается прогретое (:mod:`torrcast.usecases.cast_command._choose`). Меняется только
    вывеска на выходе: отмена - не авария.
    """
