"""Строка «год · длительность · рейтинг» карточки: договор текстом, JS-рантайма в гейте
нет (см. :mod:`tests.web.test_episode_release_chain`).

TC-1321 («0 min»): скелет карточки шлёт ``runtime: 0.0`` буквально, пока круг поиска не
ответил (:mod:`web.preview`). ``TCTime.runtimeWords(0)`` - непустая строка «0 min», и
старый отбор по НЕЙ пропускал заглушку в вывод как настоящую длительность.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "web" / "static"
CARD_JS = (STATIC / "card.js").read_text(encoding="utf-8")


def _movie_meta() -> str:
    body = CARD_JS.split("  _movieMeta(data) {", 1)[1]
    return body.split("\n  },", 1)[0]


def test_a_skeleton_runtime_of_zero_is_not_drawn_as_a_duration() -> None:
    """Отбор смотрит на исходное число ``data.runtime``, а не на слова ``runtimeWords``."""
    meta = _movie_meta()

    assert "if (data.runtime) {" in meta
    assert "if (runtime) bits.push" not in meta


def test_a_real_runtime_still_reaches_the_line() -> None:
    """Отбор не роняет настоящую длительность вместе со скелетом - жив весь путь до слов."""
    meta = _movie_meta()

    assert re.search(r"runtimeWords\(data\.runtime\)", meta)
    assert "data.runtime_estimated ? '~' + runtime : runtime" in meta
