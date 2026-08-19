"""Умолчания сухого приёмника: терпение, перезаборы куска, обида на 404 и подъём.

Наследует их :class:`torrcast.adapters.chromecast.mock.mock_receiver.MockReceiver`."""

from __future__ import annotations

from torrcast.domain.profile import CAUTIOUS


class _Settings:
    """Повадки приёмника умолчанием: все они - **осторожный профиль**.

    Живой показ берёт их из профиля своего приёмника (``self.profile``): у приставки
    Android TV и терпение к темноте, и перезаборы куска измерены совсем другими.
    """

    #: Сколько приёмник терпит стоящую картинку, прежде чем умрёт медиасессия. Замер
    #: 09-08-2026 на живом Q70D (рапорт приёмника + tcpdump): 23.5 с. Прежние «около
    #: четырёх минут» склеивали этот срок со сроком жизни приложения на экране
    #: (:attr:`torrcast.domain.profile.Profile.app_patience`) и не равны ни одному из них.
    #: Терпение задаётся и в конструкторе: тест не обязан выжидать даже эти секунды.
    PATIENCE = CAUTIOUS.patience
    #: Сколько раз приёмник САМ перезабирает пропавший кусок, прежде чем сдаться.
    #: У Q70D их два, у приставки Android TV - ни одного
    #: (:attr:`torrcast.domain.profile.Profile.segment_retries`).
    SEGMENT_RETRIES = CAUTIOUS.segment_retries
    #: Сколько приёмник не берёт LOAD вовсе, поймав 404.
    SULK = CAUTIOUS.sulk
    #: Сколько ждём картинку, поднимая погасший показ (:meth:`replay`) - как у живого
    #: приёмника: попытка тут не одна, интервалы держит зовущий.
    WAKE_TIMEOUT = 60.0
