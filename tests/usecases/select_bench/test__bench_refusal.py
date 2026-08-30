"""Зеркало отказа отбора: молчание роя и «годного нет» - это разные отказы и разные ходы."""

from __future__ import annotations

import pytest

from tests.usecases.select_bench.world import plan, rel
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.usecases.select_bench._bench_refusal import _bench_refusal


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские строки отказа обхода очереди отбора."""

_RANKED = [rel(name=f"r{n}", seeders=100 - n) for n in range(3)]


def test_a_queue_that_only_kept_silent_is_named_a_silent_swarm() -> None:
    """Ни один тронутый релиз не дошёл до приговора - врать «годного нет» тут нельзя."""
    tried = ["1 - не дождались за 20 с", "2 - не дождались за 20 с"]

    with pytest.raises(NotFoundError) as refusal:
        _bench_refusal(plan(_RANKED), [1, 2, 3], tried, silents=2, exhausted=False, picked=None)

    assert "раздач в выдаче 3, потрогали 2" in str(refusal.value)


def test_a_verdict_among_the_tried_makes_it_a_refusal_of_the_selection() -> None:
    """Хоть один приговор - и это уже отказ отбора, а не молчание роя."""
    tried = ["1 - тяжелее потолка", "2 - не дождались за 20 с"]

    with pytest.raises(NotFoundError, match="годного релиза нет"):
        _bench_refusal(plan(_RANKED), [1, 2, 3], tried, silents=1, exhausted=False, picked=None)


def test_an_unfinished_queue_offers_a_manual_choice() -> None:
    """Очередь не исчерпана - непроверенные раздачи рядом, и ход у человека есть."""
    with pytest.raises(NotFoundError, match="выбери руками"):
        _bench_refusal(
            plan(_RANKED), [1, 2, 3], ["1 - тяжелее потолка"], 0, exhausted=False, picked=None
        )


def test_a_named_release_turns_the_move_into_another_one() -> None:
    """Релиз человек назвал сам - ход у него «выбери другой», а не «выбери»."""
    with pytest.raises(NotFoundError, match="выбери другой релиз"):
        _bench_refusal(
            plan(_RANKED), [1, 2, 3], ["1 - тяжелее потолка"], 0, exhausted=False, picked=1
        )


def test_an_exhausted_whole_pool_offers_another_name_instead() -> None:
    """Спрошена вся выдача до последней - ручной выбор врал бы надеждой."""
    tried = [f"{n} - тяжелее потолка" for n in (1, 2, 3)]

    with pytest.raises(NotFoundError, match="назови картину иначе"):
        _bench_refusal(plan(_RANKED), [1, 2, 3], tried, silents=0, exhausted=True, picked=None)


def test_living_kin_is_offered_instead_of_a_bare_dead_end() -> None:
    """Соседи по франшизе живы - строка предлагает их, а не тупик."""
    kin = [Picture(title="Кино 2", year=2001, releases=[rel(name="кино 2")])]
    tried = [f"{n} - тяжелее потолка" for n in (1, 2, 3)]

    with pytest.raises(NotFoundError, match="в каталоге есть Кино 2"):
        _bench_refusal(
            plan(_RANKED, kin=kin), [1, 2, 3], tried, silents=0, exhausted=True, picked=None
        )


def test_a_refusal_where_every_miss_was_the_voice_says_so_by_name() -> None:
    """🔴 TC-741. Забраковал звук - отказ говорит про звук, а не «годного релиза нет».

    Раздачи-то годные: и кадр, и кодек, и вес - всё на месте, нет ровно того, ради чего
    человек и включал. «Годного релиза нет» прятало бы это за общим словом, а ход у
    человека от него не меняется - очередь не кончилась, значит выбор руками.
    """
    tried = [f"{n} - без русской озвучки" for n in (1, 2)]

    with pytest.raises(NotFoundError) as refusal:
        _bench_refusal(
            plan(_RANKED), [1, 2, 3], tried, silents=0, exhausted=False, picked=None, voiceless=2
        )

    said = str(refusal.value)
    assert "русской озвучки нет ни в одной из проверенных раздач (2)" in said
    assert "годного релиза нет" not in said
    assert "выбери руками" in said


def test_a_single_miss_of_another_kind_keeps_the_general_refusal() -> None:
    """Забраковал не только звук - и причина отказа снова общая, без подмены имени."""
    tried = ["1 - без русской озвучки", "2 - тяжелее потолка"]

    with pytest.raises(NotFoundError, match="годного релиза нет"):
        _bench_refusal(
            plan(_RANKED), [1, 2, 3], tried, silents=0, exhausted=False, picked=None, voiceless=1
        )
