"""Проверяет переключение справки по языку продукта и что кладётся на полку пустым."""

from __future__ import annotations

from typing import Any

from tests.articles import UTENA
from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.spoken_blurbs import spoken_blurbs

UTENA_KEY = ("Юная революционерка Утэна", 1997)
CARS_KEY = ("Тачки", 2006)
LINK = "Revolutionary Girl Utena"


def _silent() -> FakeJsonClient:
    """Источник, который на всё отвечает пустотой: статей на чужом языке у него нет."""
    return FakeJsonClient(lambda host, path, params: {"query": {"pages": []}})


def test_the_russian_product_asks_the_second_source_nothing_at_all(_russian_product: None) -> None:
    """🔴 Под русским языком справка обязана остаться той же - и не стоить ни запроса."""
    client = _silent()
    about: dict[tuple[str, int | None], Any] = {UTENA_KEY: UTENA}
    spoken, answered = spoken_blurbs(client, about, {UTENA_KEY: LINK}, {UTENA_KEY}, 0.5)
    assert spoken == {UTENA_KEY: UTENA}
    assert answered == {UTENA_KEY}
    assert client.calls == []


def test_a_defect_is_not_remembered_empty_but_an_honest_absence_is(_english: None) -> None:
    """Сломанный разбор на полку не ложится: иначе он молчал бы неделю после починки.

    У «Утэны» ссылка названа, а статьи по ней нет - это дефект, и запомнить его пустым
    значит спрятать его на неделю (:data:`EMPTY_TTL`) уже после починки. У «Тачек» ссылки
    нет вовсе - это честное «статьи на этом языке нет», и оно от починки не изменится.
    """
    keys = [UTENA_KEY, CARS_KEY]
    _spoken, answered = spoken_blurbs(
        _silent(), dict.fromkeys(keys, UTENA), {UTENA_KEY: LINK}, set(keys), 0.5
    )
    assert answered == {CARS_KEY}


def test_a_missing_article_leaves_the_viewer_without_a_blurb_and_not_with_a_russian_one(
    _english: None,
) -> None:
    """🔴 Русское описание под английским языком не показывается ни с оговоркой, ни без.

    Отрицательная проба к этому - подмешать прежние описания к добытым: тогда картина без
    английской статьи вернулась бы с русским текстом, и зритель прочитал бы чужой язык.
    """
    spoken, _ = spoken_blurbs(_silent(), {CARS_KEY: UTENA}, {}, {CARS_KEY}, 0.5)
    assert spoken == {}
