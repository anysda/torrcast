"""Стык серий: прогрев гаснет, а уже идущий перекод старта следующей серии доляжет."""

from __future__ import annotations

from torrcast.usecases.warm.warmer_state import _State


def _hand_over(warmer: _State, within: float) -> None:
    """Погасить прогрев показа, дав перекоду старта следующей серии лечь на диск.

    Оборванный перекод следующая серия делает заново сама, и кадр ждёт его целиком
    (замер: 7.6 с от конца серии до кадра). Ждём не дольше ``within``, потом гасим, как
    обычный стоп: ffmpeg без хозяина не остаётся. Второго перекода того же куска нет:
    показ следующей серии стартует после конца этого, когда кусок уже лёг с меткой
    (:attr:`_State.landing` выставляется после неё) или его перекод уже снят.
    Остальную работу следующей серии стоп гасит, как и раньше.
    """
    after, warmer.after = warmer.after, None
    warmer.stop()
    warmer.after = after
    if after is None:
        return
    if after.landing is not None:
        after.landing.wait(within)
    after.stop()
