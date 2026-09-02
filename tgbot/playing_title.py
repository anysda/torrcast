"""Человеческая шапка из структурированного снимка показа."""

from torrcast.runtime.playback_session import playback_session


def playing_title() -> str:
    """Взять название, год и серию из состояния живого юнита."""
    session = playback_session()
    if not session.active():
        return ""
    shown = session.snapshot(session.key())
    if shown is None:
        return ""
    year = f" ({shown.year})" if shown.year else ""
    return shown.spoken + year + (f" {shown.label}" if shown.label else "")
