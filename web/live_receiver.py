"""Настоящий приёмник ТВ для «На ТВ» и шаг, которым держатель каста его спрашивает.

Держателю каста (:mod:`web.tv_session`) нужен сам приёмник, а pychromecast страница
тянет лишь в миг нажатия «На ТВ» - тем же приёмом, что и в :mod:`hass.volume`.
"""

from __future__ import annotations

from torrcast.domain.profile import Profile
from torrcast.ports.receiver import Receiver

#: Как часто держатель спрашивает приёмник, пока каст на ТВ идёт. Тот же шаг, что и у
#: обычного показа (:mod:`torrcast.adapters.chromecast.cast.position`, «раз в две
#: секунды»), и не для красоты: без опроса ``current_time`` у pychromecast застревает на
#: значении первой картинки и не сдвигается сам - замерено на живом стенде ``.104``
#: (``ChromecastReceiver.position()`` через 19.5 с показа отдал 0.2 с вместо ожидаемых
#: ~15 с). «На комп» без опроса вернул бы зрителя почти в начало вместо настоящего места.
POLL_SECONDS = 2.0


def live_receiver(address: str, profile: Profile) -> Receiver:
    """Настоящий Chromecast; импорт внутри функции - чтобы страница не тянула pychromecast,
    пока никто не нажал «На ТВ» (тем же приёмом, что и в :mod:`hass.volume`)."""
    from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver

    return ChromecastReceiver(address, profile=profile)
