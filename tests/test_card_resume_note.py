"""Слот под кнопками карточки держит ровно одну строку (TC-1303, хвост).

Закладка ушла из выдачи, языка зрителя не нашлось или продолжение (сериал по `label`,
фильм по `pos`, TC-1281) - все четыре ветки делят один слот, и приоритет между ними
проверяется здесь, а не глазами на стенде. Сторож смотрит на КЛЮЧ фразы (`TC.say`
подменён на возврат имени ключа), а не на её текст: слова на решении владельца (TC-1376).

Раскладка - в ``tests/web_js/card_resume_note.js``, настоящий ``card.js`` в node поверх
игрушечного DOM.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "card_resume_note.js"


@pytest.fixture(scope="module")
def slots() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож слота карточки исполняет card.js", pytrace=False)
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, Any] = json.loads(done.stdout)
    return said


def test_nothing_special_leaves_the_slot_empty(slots: dict[str, Any]) -> None:
    assert slots["nothing"] is None, slots["nothing"]


def test_no_releases_takes_the_slot_over_everything_else(slots: dict[str, Any]) -> None:
    assert "web.detail.no_releases" in slots["noReleases"], slots["noReleases"]


def test_a_series_resume_note_names_the_resumes_key(slots: dict[str, Any]) -> None:
    assert slots["resumeSeries"] == "web.detail.resumes", slots["resumeSeries"]


def test_a_movie_resume_note_names_the_resumes_here_key(slots: dict[str, Any]) -> None:
    """TC-1281. Фильм не несёт `label`: место продолжения говорится другим ключом,
    тем же, каким уже подписана серия в списке серий (`card-series.js`)."""
    assert slots["resumeMovie"] == "web.detail.resumes_here", slots["resumeMovie"]


def test_a_resumable_movie_without_a_position_shows_nothing(slots: dict[str, Any]) -> None:
    assert slots["movieResumableNoPos"] is None, slots["movieResumableNoPos"]


def test_bookmark_gone_outranks_both_resume_notes(slots: dict[str, Any]) -> None:
    assert slots["bookmarkGoneOverSeriesResume"] == "web.detail.bookmark_gone"
    assert slots["bookmarkGoneOverMovieResume"] == "web.detail.bookmark_gone"


def test_voice_fallback_outranks_the_movie_resume_note(slots: dict[str, Any]) -> None:
    assert slots["voiceFallbackOverMovieResume"] == "web.detail.voice_fallback_note"


def test_bookmark_gone_outranks_the_voice_fallback_note(slots: dict[str, Any]) -> None:
    assert slots["bookmarkGoneOverVoiceFallback"] == "web.detail.bookmark_gone"


def test_voice_fallback_alone_shows_its_own_note(slots: dict[str, Any]) -> None:
    assert slots["voiceFallbackAlone"] == "web.detail.voice_fallback_note"
