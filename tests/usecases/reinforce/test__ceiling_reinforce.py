"""Второй круг уточнённым запросом «имя + год из справки», когда потолок прячет картину."""

from __future__ import annotations

from typing import Any

from tests.usecases.reinforce.stand import Indexer, Said, franchise, pictures, row
from torrcast.domain.args import Args
from torrcast.domain.facts.origin import Origin
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.reinforce._ceiling_reinforce import _ceiling_reinforce

#: Выдача запроса «девять»: сотня строк про соседей по подстроке, самой картины нет.
_YARDS = [row("Девять ярдов / The Whole Nine Yards (2000) BDRip 1080p", "a")]
#: То, что лежит за потолком и приезжает только на уточнённый запрос.
_NINE = [row("Девять / Nine (2009) BDRip 1080p | D", "b", size_gb=9.0, seeders=7)]


def _refined(
    about: Origin, rows: list[RawResult], *, spare: float = 9.0
) -> tuple[Indexer, Said, tuple[list[Any], list[Picture], list[Picture]]]:
    client = Indexer(rows, spare=spare, capped=("RuTor",))
    said = Said()
    outcome = _ceiling_reinforce(
        client,
        "девять",
        Args(query=["девять"]),
        _YARDS,
        pictures(_YARDS),
        franchise("девять", _YARDS),
        said,
        passport=lambda *_a, **_k: about,
    )
    return client, said, outcome


def test_the_ceiling_hid_the_picture_and_the_refined_query_gets_it_out() -> None:
    """🔴 TC-331. По «девять» - сотня чужих строк, по «девять 2009» - сама картина."""
    client, said, (raw, _pictures, found) = _refined(
        Origin(title="Nine", year=2009, name="Девять"), _NINE
    )

    assert client.asked == ["девять 2009"], "второй круг - уточнённым запросом"
    assert [picture.title for picture in found] == ["Девять", "Девять ярдов"]
    assert len(raw) == 2, "выдачи склеиваются, а не заменяются"
    assert "упёрлась в потолок каталога" in said.text, "подмена не молчаливая"


def test_a_name_without_a_vouch_orders_no_circle() -> None:
    """🔴 Гейт TC-253: имя, лишь признанное похожим, второго круга не заказывает."""
    about = Origin(title="Nine", year=2009, name="Девять", guessed=True)
    client, _said, (raw, _pictures, found) = _refined(about, _NINE)

    assert client.asked == []
    assert [picture.title for picture in found] == ["Девять ярдов"]
    assert len(raw) == 1


def test_without_a_year_there_is_nothing_to_refine_with() -> None:
    """Год берётся только из справки: выдача его не знает, а выдумывать нечем."""
    client, _said, (_raw, _pictures, found) = _refined(Origin(title="Nine", name="Девять"), _NINE)

    assert client.asked == []
    assert [picture.title for picture in found] == ["Девять ярдов"]


def test_a_spent_goal_cancels_the_circle_and_says_so() -> None:
    """Круг платится из остатка цели, и отказ его не молчаливый."""
    client = Indexer(_NINE, spare=0.0, capped=("RuTor",))
    client.over_goal = True
    said = Said()

    _raw, _pictures, found = _ceiling_reinforce(
        client,
        "девять",
        Args(query=["девять"]),
        _YARDS,
        pictures(_YARDS),
        franchise("девять", _YARDS),
        said,
        passport=lambda *_a, **_k: Origin(title="Nine", year=2009, name="Девять"),
    )

    assert client.asked == []
    assert [picture.title for picture in found] == ["Девять ярдов"]
    assert said.text == (
        "not doing уточнение по «девять»: the search already spent the goal at 10s"
    )


def test_a_stranger_from_the_refined_circle_is_not_taken() -> None:
    """Берутся только картины, подписанные ТОЧНО спрошенным именем, - иначе прежняя выдача."""
    alien = [row("Девять жизней / Nine Lives (2016) BDRip 1080p", "c")]
    client, _said, (raw, _pictures, found) = _refined(
        Origin(title="Nine", year=2009, name="Девять"), alien
    )

    assert client.asked == ["девять 2009"]
    assert [picture.title for picture in found] == ["Девять ярдов"], "подмены не случилось"
    assert raw is _YARDS, "прежняя выдача остаётся целиком"
