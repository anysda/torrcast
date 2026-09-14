"""Запуск полки открытой карточки."""

from types import SimpleNamespace

from web.request import Request
from web.start_related import start_related


class _Facts:
    def of(self, *_args: object) -> "_Facts":
        return self

    def ready(self, *_args: object) -> SimpleNamespace:
        return SimpleNamespace(entity="Q104905")


class _Related:
    asked: tuple[str, bool, str] | None = None

    def retry(self, title: str, series: bool, entity: str) -> None:
        self.asked = title, series, entity


def test_an_opened_tile_reuses_its_fact_qid() -> None:
    request = Request(
        method="GET",
        path="/api/card/movie:wall-e:2008",
        query={"title": "ВАЛЛ-И", "year": "2008", "kind": "movie"},
        body={},
    )
    related = _Related()

    hint = start_related(request, _Facts(), related)

    assert hint == ("ВАЛЛ-И", 2008, "movie")
    assert related.asked == ("ВАЛЛ-И", False, "Q104905")
