"""Q-коды опубликованной полки родни и фоновая очередь родни её плиток."""

from collections.abc import Callable

from torrcast.domain.facts.kin import Kin
from web.kin_ahead import BATCH, QUEUE, KinAhead


def _later(jobs: list[Callable[[], None]]) -> Callable[[Callable[[], None]], None]:
    return jobs.append


def test_a_published_tile_is_known_by_its_name_and_year_and_namesakes_are_not() -> None:
    """Плитка родни открывается по своему Q-коду; тёзки одного года - не тождество."""
    ahead = KinAhead()
    ahead.offer([Kin("Q1", "Тайна Коко", 2017), Kin("Q2", "Дом", 2015)])
    ahead.offer([Kin("Q3", "Дом", 2015)])

    assert ahead.entity("Тайна Коко", 2017) == "Q1"
    assert ahead.entity("Тайна Коко", 2018) == ""
    assert ahead.entity("Дом", 2015) == "", "два Q-кода под одним именем выдали бы чужую полку"


def test_the_newest_shelf_is_fetched_first_in_batches_and_a_failure_is_asked_again() -> None:
    """Свежая полка встаёт перед старым хвостом; упавшая пачка вернётся со следующей полкой."""
    asked: list[list[str]] = []
    jobs: list[Callable[[], None]] = []

    def fetch(chunk: list[str], _timeout: float) -> None:
        asked.append(chunk)
        if "Q9" in chunk:
            raise OSError("HTTP 429")

    ahead = KinAhead(fetch, _later(jobs))
    ahead.offer([Kin(f"Q{n}", f"Старая {n}", 2000) for n in range(100, 100 + BATCH + 1)])
    ahead.offer([Kin("Q9", "Свежая", 2001)])
    for job in list(jobs):
        job()

    assert asked == [
        ["Q9", *(f"Q{n}" for n in range(100, 99 + BATCH))],
        [f"Q{99 + BATCH}", f"Q{100 + BATCH}"],
    ]
    assert len(jobs) == 2, "полос фона больше двух - карточке не хватит Wikimedia"
    ahead.offer([Kin("Q9", "Свежая", 2001), Kin(f"Q{100 + BATCH}", "Старая", 2000)])
    jobs[-1]()
    assert asked[-1] == ["Q9"], "снятая родня спрошена заново или упавшая забыта"


def test_the_queue_forgets_the_old_tail_so_it_can_be_offered_again() -> None:
    """Отпавший хвост очереди не помечен снятым: его полка встанет в очередь снова."""
    asked: list[list[str]] = []
    jobs: list[Callable[[], None]] = []
    ahead = KinAhead(lambda chunk, _timeout: asked.append(chunk), _later(jobs))
    tail = f"Q{999 + QUEUE}"
    ahead.offer([Kin(f"Q{n}", f"Плитка {n}", 2000) for n in range(1000, 1000 + QUEUE)])
    ahead.offer([Kin("Q1", "Свежая", 2000)])
    jobs[0]()

    assert asked[0][0] == "Q1"
    assert tail not in {entity for chunk in asked for entity in chunk}
    ahead.offer([Kin(tail, "Хвост", 2000)])
    jobs[-1]()
    assert asked[-1] == [tail]
