"""Сколько CLI ждёт первой картинки: сумма сроков всех фаз старта.

Слагаемые лежат в домене и в соседних сценариях; здесь они складываются, потому что
ждёт эту сумму сам сценарий показа (:func:`torrcast.usecases.playback._play`).
"""

from torrcast.domain.hls_wait import KEYS_WAIT, PILOT_TIMEOUT
from torrcast.domain.start_settings import START_SLACK
from torrcast.domain.start_timeout import START_TIMEOUT
from torrcast.domain.worker_settings import WORKER_DUR, WORKER_META

#: **Бюджет старта показа: столько CLI ждёт картинку на экране** (:func:`_await_playing`).
#:
#: Число не выбирается на глаз и не «берётся с запасом»: это сумма потолков всех фаз,
#: которые юнит проходит от запуска до первого ``PLAYING``, - метаданные раздачи, ffprobe
#: длительности, ожидание чужой карты опорных кадров, пробный прогон упаковки и терпение
#: приёмника к молчаливому ``IDLE``. Пока CLI ждал меньше суммы (120 с против 60 + 90 +
#: 60), он гасил `stop_play_unit`'ом показ, который вот-вот начался бы.
#:
#: Ждать так долго не страшно и не молчаливо:
#: :class:`~torrcast.adapters.console.console.Progress` всё это время показывает живую
#: фазу, а любая честная неудача убивает юнит раньше - CLI видит
#: это по :func:`unit_active` и печатает причину из журнала, не досиживая до конца.
START_BUDGET = WORKER_META + WORKER_DUR + KEYS_WAIT + PILOT_TIMEOUT + START_SLACK + START_TIMEOUT
