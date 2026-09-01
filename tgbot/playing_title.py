"""Человеческая шапка из структурированного снимка показа."""

from torrcast.runtime.playback_session import playback_session


def playing_title() -> str:
    """Взять название, год и серию из состояния живого юнита."""
    session = playback_session()
    shown = session.snapshot(session.key() if session.active() else "")
    if shown is None:
        return ""
    year = f" ({shown.year})" if shown.year else ""
    return shown.title + year + (f" {shown.label}" if shown.label else "")
