"""Проводка показа: после неё в слотах показа стоят настоящий медиатракт и приёмник."""

from __future__ import annotations

import torrcast.usecases.playback._show_state as _show_state
from torrcast.adapters.chromecast.cast.make_receiver import make_receiver
from torrcast.adapters.recode.recoder import Recoder
from torrcast.adapters.system_clock import CLOCK
from torrcast.runtime.wire_show import wire_show


def test_the_show_gets_the_real_media_pipeline_and_the_real_receiver() -> None:
    """Приёмник, кодировщик и часы в слотах - те самые классы, а не однофамильцы.

    Живое приложение проводит показ на запуске (``tests.conftest._wired``), поэтому
    повторный вызов тут только подтверждает: слоты берут своё значение отсюда.
    """
    wire_show()

    assert _show_state.make_receiver is make_receiver
    assert _show_state.Recoder is Recoder
    assert _show_state.CLOCK is CLOCK
    assert _show_state.RECODE_DIR and callable(_show_state.grid_for)
