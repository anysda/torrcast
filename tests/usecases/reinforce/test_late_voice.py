"""Зеркало :mod:`torrcast.usecases.reinforce.late_voice`: трата отложенного добора.

🔴 TC-770. Ранние доборы решают, идти ли им, по ИМЕНИ раздачи, а приговор «русской
дорожки нет» выносит ffprobe по дорожкам. Круг стоит между ними и тратит то, что сторож
раннего добора отложил: своей сети у него нет вовсе, и на счастливом пути он не стоит
ничего.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

import torrcast.usecases.discover._search_state as _search_state
from tests.usecases.reinforce.stand import Said, pictures, releases, row
from torrcast.domain.args import Args
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS
from torrcast.usecases.reinforce.late_voice import late_voice
from torrcast.usecases.reinforce.plan_for import plan_for

#: Пул, собранный обычным кругом по «врата штейна ONA»: одна раздача, и русской
#: дорожки ffprobe в ней не нашёл.
_ONE = [row("Врата Штейна / Steins;Gate [S01 + Specials + ONA] (2011-2014) BDRip", "a", seeders=40)]
#: То, что привёз ранний добор по «Steins;Gate» и что сторож отложил, не пустив в меню.
_DUBBED = [row("Steins;Gate - AniLiberty.TOP [BDRip 1080p][HEVC][1-25]", "b", seeders=61)]


@pytest.fixture
def untouched() -> Iterator[list[str]]:
    """Слот боевого поиска, помнящий КАЖДЫЙ заход: у круга своей сети быть не должно."""
    went: list[str] = []
    keep = _search_state._search_indexers

    def fake(url: str, _key: str) -> Any:
        went.append(url)
        raise AssertionError("поздний круг ходил к индексерам")

    _search_state._search_indexers = fake
    yield went
    _search_state._search_indexers = keep


def _late(aside: list[Any]) -> tuple[Any, Said]:
    picture = max(pictures(_ONE), key=lambda p: len(p.releases))
    picture.aside = list(releases(aside))
    args = Args(query=["врата", "штейна", "ONA"])
    config = Config(prowlarr_apikey="k", prowlarr_url="http://x")
    said = Said()
    plan = plan_for(picture, args, config, CAUTIOUS)
    return late_voice(plan, args, config, said, CAUTIOUS), said


def test_the_pocket_left_by_the_guard_is_spent_when_no_russian_was_proven(
    untouched: list[str],
) -> None:
    """🔴 Живой случай замера: добор по «Steins;Gate» ранний сторож отбросил целиком.

    Отбросил он его мерой «привёз больше картин», и мера эта защищает МЕНЮ. Здесь меню
    уже отвечено, картина названа человеком, и защищать нечего - а раздачи её собственные.
    """
    late, said = _late(_DUBBED)

    assert late is not None, "отложенная русская раздача была"
    assert [r.raw_name for r in late.ranked] == [_DUBBED[0].title]
    assert said.text == phrase("reinforce.late_voice_note", now=1)
    assert untouched == [], "круг не стоил ни одного захода в сеть"


def test_only_the_fresh_releases_go_into_the_late_plan(untouched: list[str]) -> None:
    """Про прежние раздачи отбор уже всё узнал: второй ffprobe по ним - плата за известное."""
    late, _said = _late(_ONE + _DUBBED)

    assert late is not None
    assert [r.raw_name for r in late.ranked] == [_DUBBED[0].title], "старьё в план не вернулось"


def test_the_releases_promising_russian_are_asked_first(untouched: list[str]) -> None:
    """🔴 Отбор проверяет голову очереди, а не всю: круг за русским и спрашивает русских.

    Живой замер (стенд .66, замороженный пул, «эксперименты лейн»): карман отдал 81
    раздачу, отбор успел проверить ДВЕ, обе японские - при 12 обещающих русский. Упор был
    в порядок, а не в пул.
    """
    quiet = row("Steins;Gate [BDRip 2160p][HEVC] RAW", "c", seeders=900)
    late, _said = _late([*_DUBBED, quiet])

    assert late is not None
    names = [r.raw_name for r in late.ranked]
    assert names == [_DUBBED[0].title], "молчащее имя вперёд обещанного дубляжа не лезет"


def test_without_a_single_promise_the_whole_pocket_is_spent(untouched: list[str]) -> None:
    """Русского не обещает никто - идёт всё отложенное: имя молчит, а дорожка бывает."""
    quiet = row("Steins;Gate [BDRip 2160p][HEVC] RAW", "c", seeders=900)
    late, _said = _late([quiet])

    assert late is not None
    assert [r.raw_name for r in late.ranked] == [quiet.title]


def test_an_empty_pocket_ends_the_circle_without_a_word(untouched: list[str]) -> None:
    """Сторож ничего не откладывал - круга нет: это «добавить нечего», а не беда."""
    late, said = _late([])

    assert late is None and said.notes == []
