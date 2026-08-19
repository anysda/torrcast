"""Цель перекода, посчитанная под потолки приёмника: вес куска и его битрейт.

Спрашивает её :meth:`torrcast.adapters.recode.encode.Encode.fit`, и только он."""

from __future__ import annotations

from torrcast.adapters.recode.encode_settings import FIT_FLOOR, FIT_SLACK, MAXRATE_GAIN
from torrcast.domain.media import AUDIO_MBIT, TS_OVERHEAD


def fit_mbit(mbit: float, span: float, cap: float, cap_mbit: float = 0.0) -> float:
    """Цель перекода, Мбит/с, посчитанная под потолки ПРИЁМНИКА.

    🔴 Единственное место, где цель перекода считается из потолков. Спрашивают его
    двое - фоновый кодировщик (:meth:`Recoder._run`) и ужатие на месте
    (:meth:`torrcast.usecases.feed_pack.feed.Feed._shrink`), - и разойдись они хоть в одном
    знаке, в проекте появился бы третий источник правды о потолке.

    Потолков два, и они разной природы. ``cap`` - **вес** куска в байтах
    (:attr:`torrcast.domain.profile.Profile.max_segment_bytes`): сегмент тяжелее его приёмник
    не доигрывает, а выбрасывает буфер и качает заново. Сколько мегабит в секунду в
    такой вес влезает, зависит от ДЛИНЫ куска, а она у сетки по опорным кадрам
    доходит до 20 секунд: прибитые 9 Мбит/с кладут в такой кусок 23 МБ при потолке 16,
    и не влезает сам перекод, а не только копия (TC-483). ``cap_mbit`` - **битрейт**,
    который приёмник тянет (:attr:`torrcast.domain.profile.Profile.recode_at_mbit`): выше него
    он спотыкается независимо от веса. Ноль - про этот потолок не спрашивали.

    Считается от того, что получит приёмник, а не от голого видео: сверху лягут наш
    AAC (:data:`torrcast.domain.delivered_mbit.AUDIO_MBIT`) и оверхед mpegts
    (:data:`torrcast.domain.delivered_mbit.TS_OVERHEAD`), а сам кодер вправе идти до
    :attr:`Encode.maxrate`. Отсюда же и запас :data:`FIT_SLACK`.

    Вверх не перекодируем: цель не может стать выше той, что уже стоит (``mbit``), -
    потолок умеет только опустить её.
    """

    def room(delivered: float) -> float:
        """Сколько Мбит/с ВИДЕО просить, чтобы сегмент не вышел за ``delivered``."""
        return max(0.0, (delivered / TS_OVERHEAD - AUDIO_MBIT) / MAXRATE_GAIN)

    want = room(cap * 8 / (max(span, 0.1) * 1e6))
    if cap_mbit > 0:
        want = min(want, room(cap_mbit))
    return max(FIT_FLOOR, min(mbit, want * FIT_SLACK))
