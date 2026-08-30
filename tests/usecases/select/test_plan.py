"""Зеркало плана картины: очередь отбора, её хвост и то, что в неё не попало."""

from __future__ import annotations

import pytest

from tests.usecases.select.world import parsed, plan, release
from torrcast.domain._series import _Series
from torrcast.domain.args import Args
from torrcast.domain.episode import Episode
from torrcast.domain.info_hash import info_hash
from torrcast.domain.not_found_error import NotFoundError


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские отказы плана по номеру релиза вне очереди."""

_ASKED = Args(query=["кино"])
#: Названный 1080p H.264: именной кандидат, ворота его пускают.
_NAMED = release(seeders=66)
#: Дубляж без слова о качестве: ворота его не пустят, пока играет именной.
_DUBBED = release("Кино (1999) WEBRip | Дубляж", quality="", codec="", size_gb=4.4, seeders=3)


def test_the_queue_takes_every_release_that_passed_the_gate() -> None:
    """Обрезать очередь тут нечем: сколько успеет разобрать показ, решают его часы."""
    pool = [release(seeders=n) for n in (90, 80, 70)]

    assert plan(*pool).candidates(_ASKED) == [1, 2, 3]


def test_a_dubbed_release_the_gate_refused_becomes_the_tail() -> None:
    """🔴 TC-195. Голова кончилась, а рядом лежит дубляж, которого никто не спрашивал."""
    queue = plan(_NAMED, _DUBBED).candidates(_ASKED)

    assert queue == [1, 2], "хвост идёт ПОСЛЕ головы и порядка её не меняет"


def test_a_release_named_by_hand_is_the_whole_queue() -> None:
    """Номер назвал человек - судить его воротами нечего, очередь из него одного."""
    queue = plan(_NAMED, _DUBBED).candidates(Args(query=["кино"], release=2))

    assert queue == [2]


def test_a_number_out_of_the_pool_names_the_picture_it_belongs_to() -> None:
    """🔴 TC-446. Счёт относится к ЭТОЙ картине, и отказ обязан её назвать."""
    with pytest.raises(NotFoundError, match="у «Кино» релизов 1, номера 5 нет"):
        plan(_NAMED).candidates(Args(query=["кино"], release=5))


def test_a_release_named_by_hash_is_found_in_the_new_pool() -> None:
    """Поздняя выдача меняет места, но не имеет права менять названную раздачу."""
    mine = release(magnet=f"magnet:?xt=urn:btih:{'a' * 40}", seeders=66)
    other = release(magnet=f"magnet:?xt=urn:btih:{'b' * 40}", seeders=10)
    asked = Args(query=["кино"], release=1, release_hash=info_hash(mine))

    assert plan(other, mine).candidates(asked) == [2]


def test_a_hash_that_left_the_pool_is_a_refusal_with_a_word() -> None:
    """Раздача из показанной таблицы исчезла - об этом говорят, а не подставляют соседа."""
    asked = Args(query=["кино"], release=1, release_hash="0" * 40)

    with pytest.raises(NotFoundError, match="показанного релиза 1"):
        plan(_NAMED).candidates(asked)


def test_the_releases_without_the_asked_episode_are_skipped_not_hidden() -> None:
    """Отбраковка не молчаливая: кого выкинули по имени, план и печатает."""
    right = parsed("Кино / Movie (1999) WEB-DL 1080p | 1 сезон, 1-10 из 10")
    wrong = parsed("Кино / Movie (1999) WEB-DL 1080p | 2 сезон, 1-10 из 10", seeders=40)
    built = plan(right, wrong, series=_Series(want=Episode(1, 9)))

    assert built.want == Episode(1, 9)
    assert [r.raw_name for r in built.skipped] == [wrong.raw_name]
    assert built.candidates(_ASKED) == [1], "огрызков в очереди нет вовсе"


def test_a_release_that_did_not_play_drops_out_of_the_queue_and_is_not_demoted() -> None:
    """🔴 TC-571. Раздача, которая в этом запуске не сыграла, ВЫБЫВАЕТ, а не понижается.

    Пул тут длиной один - ровно тот случай, ради которого выбирали между понижением и
    исключением: понижение вернуло бы её же первой, и зритель получил бы ту же темноту
    второй раз подряд, уже зная её причину.
    """
    only = release()
    asked = Args(query=["кино"])
    asked.bury(only.magnet)

    assert plan(only).candidates(asked) == []


def test_burying_one_release_leaves_the_rest_of_the_queue_in_place() -> None:
    """Хоронится одна названная раздача, а не очередь: порядок остальных не меняется ни на знак."""
    dead = release(magnet="magnet:?xt=мертво")
    alive = release(magnet="magnet:?xt=живо", seeders=40)
    asked = Args(query=["кино"])
    asked.bury(dead.magnet)

    assert plan(dead, alive).candidates(asked) == [2]
    assert plan(dead, alive).candidates(_ASKED) == [1, 2], "без похорон очередь прежняя"
