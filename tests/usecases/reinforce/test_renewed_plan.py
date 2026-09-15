"""Зеркало :mod:`torrcast.usecases.reinforce.renewed_plan`: круг из сети вместо круга с диска.

🔴 После рестарта показ с карточки берёт круг с диска. У «Рик и Морти» s2e1 в пуле трёхчасовой
давности не было единственной играющей раздачи: 9 раздач сезона отпали, показа не было.
"""

from __future__ import annotations

from dataclasses import replace

from tests.usecases.choice.world import film, plan
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.release import Release
from torrcast.usecases.reinforce.renewed_plan import renewed_plan

_ARGS = Args(query=["кино"])


def _release(name: str, magnet: str) -> Release:
    return replace(film(f"Кино 2020 WEB-DL 1080p {name}"), magnet=magnet)


_OLD = _release("старая", "magnet:?xt=urn:btih:AAAA&dn=old")
_GONE = _release("молчит", "magnet:?xt=urn:btih:bbbb")
_NEW = _release("новая", "magnet:?xt=urn:btih:cccc")


def test_only_the_releases_the_disk_pool_lacked_are_selected_again() -> None:
    """Про прежние раздачи отбор уже всё узнал: второй заход стоил бы тех же ожиданий роя."""
    disk = plan(pool=[_OLD, _GONE])
    live = plan(pool=[_GONE, _NEW, replace(_OLD, magnet="magnet:?xt=urn:btih:aaaa&tr=x")])

    renewed = renewed_plan(disk, live, _ARGS, Config(), CAUTIOUS)

    assert renewed is not None
    assert [release.magnet for release in renewed.ranked] == [_NEW.magnet]
    assert renewed.runtime == disk.runtime


def test_a_circle_that_already_came_from_the_network_renews_nothing() -> None:
    disk = plan(pool=[_OLD, _NEW])

    assert renewed_plan(disk, plan(pool=[_NEW, _OLD]), _ARGS, Config(), CAUTIOUS) is None
    assert renewed_plan(disk, None, _ARGS, Config(), CAUTIOUS) is None


def test_releases_without_an_info_hash_are_told_apart_by_the_magnet_itself() -> None:
    disk = plan(pool=[film("Кино 2020 WEB-DL 1080p а")])
    live = plan(pool=[film("Кино 2020 WEB-DL 1080p а"), film("Кино 2020 WEB-DL 1080p б")])

    renewed = renewed_plan(disk, live, _ARGS, Config(), CAUTIOUS)

    assert renewed is not None and [r.raw_name for r in renewed.ranked] == [
        "Кино 2020 WEB-DL 1080p б"
    ]
