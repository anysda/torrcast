"""🔴 Перебор очереди кино не доходит до раздачи другого года: это другая картина.

«Оно» 2017 года: две раздачи промолчали пирами, а в том же имени лежит «Оно приходит за
тобой / It Follows» 2014 года, живая. Сыграть её - подменить картину; своих нет - отказ.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.usecases.select_bench._bench_queue import _bench_queue
from torrcast.usecases.select_bench.bench import Bench


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Отбор под русской ручкой: годна подтверждённая русская дорожка."""


_ASKED = Args(query=["кино"])
_RUS = Media(RUNTIME, (AudioTrack(index=0, language="rus"),), "h264", height=1080, width=1920)
#: Свои раздачи картины 1999 года: верх ранжира.
_OWN = [rel(name=f"Кино / Movie (1999) r{n} | Дубляж", seeders=100 - n) for n in range(2)]
#: Однофамилец 2004 года в том же пуле, живой и с русской дорожкой.
_OTHER = replace(rel(name="Кино / Other Movie (2004) BDRip | Дубляж", seeders=90), year=2004)


class _Asked(Torrents):
    """Служба раздач, которая помнит, кого из пула отбор вообще спрашивал."""

    def __init__(self, dead: set[str]) -> None:
        super().__init__(dead=dead)
        self.asked: list[str] = []

    def add(self, magnet: str) -> str:
        self.asked.append(magnet)
        return super().add(magnet)


def test_a_film_release_of_another_year_never_stands_in_the_queue() -> None:
    """Очередь кино - только свои годы; соседний год (фестиваль) и год без имени - свои."""
    festival = replace(rel(name="Кино / Movie (2000) WEB-DL 1080p"), year=2000)
    unnamed = replace(rel(name="Кино WEB-DL 1080p"), year=None)

    assert _bench_queue(plan([*_OWN, _OTHER, festival, unnamed]), _ASKED) == [1, 2, 4, 5]


def test_silent_own_releases_end_in_a_refusal_not_in_the_namesake_of_another_year() -> None:
    """Обе свои раздачи молчат пирами, живой однофамилец не спрашивается вовсе."""
    pool = [*_OWN, _OTHER]
    torrents = _Asked(dead={f"hash-{release.magnet}" for release in _OWN})
    bench = Bench(torrents, prober=probes(pool, _RUS, _RUS, _RUS), meta_budget=1.0)

    with pytest.raises(NotFoundError):
        bench.resolve(plan(pool), _ASKED, Said())

    assert _OTHER.magnet not in torrents.asked, "раздачу другой картины подняли из роя"
    assert set(torrents.asked) <= {release.magnet for release in _OWN}
