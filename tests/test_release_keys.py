"""Карточка говорит до «Играть», что раздачи закладки нет в живой выдаче."""

from __future__ import annotations

from tests.usecases.rank.releases import media
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.heard import Heard
from web.release_keys import release_keys


def _gone_card() -> tuple[Plan, Release]:
    pooled = Release(raw_name="Show S02", title="Show", magnet="magnet:?xt=urn:btih:" + "a" * 40)
    picture = Picture(title="Show", year=2013, kind="tv", releases=[pooled])
    kept = Release(raw_name="Show", title="Show", magnet="magnet:?xt=urn:btih:" + "e" * 40)
    return Plan(picture=picture, ranked=[pooled], runtime=1500.0, warn_mbit=12.0), kept


def test_a_bookmark_release_missing_from_a_live_pool_is_said_before_play() -> None:
    """Раздачи закладки нет в живой выдаче: карточка говорит, что «Играть» возьмёт другую."""
    plan, kept = _gone_card()

    keys = release_keys(plan, kept, None, live=True)

    assert keys == {"release": "e" * 40, "bookmark_gone": True, "voice_fallback": False}
    assert release_keys(plan, plan.ranked[0], None, live=True)["bookmark_gone"] is False


def test_a_pool_from_disk_does_not_call_the_bookmark_release_gone() -> None:
    """В записи с диска не было строк JacRed: ec1be32a «пропала», хотя живой пул её держал."""
    plan, kept = _gone_card()

    assert release_keys(plan, kept, None, live=False)["bookmark_gone"] is False


def test_a_voiceless_fallback_is_said_before_play() -> None:
    """🔴 TC-1303. Языка зрителя не нашлось ни у кого - карточка говорит это явно.

    Тихой подмены звука не бывает: то же самое поле, которым карточка предупреждает про
    пропавшую раздачу закладки (:func:`test_a_bookmark_release_missing_from_a_live_pool_
    is_said_before_play`), несёт и признак запасного хода (:attr:`web.heard.Heard.
    fallback`), взятый прямо из отбора (:attr:`torrcast.usecases.select._prep._Prep.
    voice_fallback`).
    """
    plan, kept = _gone_card()
    fallen = Heard(media(), native=False, studios=(), fallback=True)
    quiet = Heard(media(), native=False, studios=(), fallback=False)

    assert release_keys(plan, kept, fallen, live=False)["voice_fallback"] is True
    assert release_keys(plan, kept, quiet, live=False)["voice_fallback"] is False
    assert release_keys(plan, kept, None, live=False)["voice_fallback"] is False
