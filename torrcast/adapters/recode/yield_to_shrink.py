"""Заход замирает, пока выкладка ужимает тяжёлый кусок на месте, и отдаёт ей процессор.

Зовёт это заход кодировщика (:func:`_run`), и только он."""

from __future__ import annotations

import contextlib
import signal
import time
from typing import TYPE_CHECKING, Any, Final

from torrcast.domain.hls_settings import SHRINK_DIR
from torrcast.ports.journal import journal

if TYPE_CHECKING:
    from torrcast.adapters.recode.recoder_state import _State


#: Насколько свежим должен быть файл в рабочем каталоге ужатия, чтобы считать ужатие
#: живым (:meth:`Recoder._shrink_running`), секунды. Ужатие пишет свой сегмент сплошным
#: потоком, и пока оно идёт, метка времени файла обновляется непрерывно; полторы секунды -
#: запас в семь раз к шагу опроса выкладки (0.2 с) и в пять к шагу опроса захода (0.3 с).
SHRINK_FRESH: Final = 1.5


def _shrink_touched(state: _State) -> float:
    """Когда в рабочем каталоге ужатия последний раз что-то писали (стенные секунды)."""
    newest = 0.0
    with contextlib.suppress(OSError):
        for path in (state.spare / SHRINK_DIR).glob("*.ts"):
            with contextlib.suppress(OSError):
                newest = max(newest, path.stat().st_mtime)
    return newest


def _shrink_running(state: _State) -> bool:
    """Ужимает ли выкладка кусок прямо сейчас - по её же рабочему каталогу.

    Заявку ставит :meth:`_hold_bulky` (:attr:`shrinking`), а живость подтверждает
    факт, а не таймер: ужатие пишет свой сегмент в ``spare/<SHRINK_DIR>``
    (:meth:`torrcast.stream.Feed._shrink`), и пока метка времени файла свежее
    :data:`SHRINK_FRESH`, второй кодировщик на машине работает. Один таймер тут врал
    бы в обе стороны: ужатие бывает и мгновенным (перекод доехал сам, пока ждали
    замок), и долгим до :attr:`over_wait`.

    Пока ffmpeg ужатия поднимается (:attr:`startup`), каталог пуст не потому, что всё
    кончилось, - эту фору держим по заявке.
    """
    at = state.shrinking
    if at is None:
        return False
    slot, since = at
    waited = time.monotonic() - since
    if waited < state.startup:
        return True
    fresh = time.time() - _shrink_touched(state) < SHRINK_FRESH
    if fresh and waited < state.over_wait and state.ready(slot) is None:
        return True
    state.shrinking = None
    return False


def _yield_to_shrink(state: _State, packer: Any) -> float:
    """Замереть, пока выкладка ужимает кусок на месте. Возвращает, сколько простояли.

    Кто кому уступает, решается не вежливостью, а тем, кого ждут. Ужатие на месте
    идёт по нужде: на его куске выкладка СТОИТ, и пока он не готов, приёмник не
    получает ни его, ни всего, что за ним. Заход же работает впрок - его кусок нужен
    через десятки секунд, и опоздание на пять ему ничего не стоит.

    Замер на стенде, ради которого это написано (4 vCPU, 1080p H.264 16 Мбит/с на
    входе, кусок 14.3 с, медиана из трёх): рядом с ужатием живой заход идёт
    ``veryfast`` 0.46× вместо 1.41×, ``superfast`` 0.70× вместо 2.24×, ``ultrafast``
    0.95× вместо 3.09×. Потеря одна и та же - две трети - на всех трёх пресетах, то
    есть это не «немного медленнее», а «вдвое-втрое», и оба кодировщика ползут разом.
    Для сравнения, второй половиной той же гипотезы был прогрев: он в своём обычном
    виде (копия, ``nice 19``, темп 4) стоит заходу 3 %, то есть ничего.

    Именно ``SIGSTOP``, а не «снять и начать заново» и не ``nice``: процессор у ffmpeg
    отбирает только пауза (заголовок :mod:`torrcast.warm`), а снятый заход выбросил бы
    уже посчитанные секунды. Пауза короткая по определению - ужатие это один кусок.
    """
    if not _shrink_running(state):
        return 0.0
    began = time.monotonic()
    slot = state.shrinking[0] if state.shrinking is not None else -1
    with contextlib.suppress(OSError, ProcessLookupError, AttributeError):
        packer.proc.send_signal(signal.SIGSTOP)
    journal().mark("заход уступил ужатию", слот=slot)
    try:
        while not state.stopped and _shrink_running(state):
            time.sleep(0.2)
    finally:
        with contextlib.suppress(OSError, ProcessLookupError, AttributeError):
            packer.proc.send_signal(signal.SIGCONT)
    return time.monotonic() - began
