"""Страховки на единые точки отказа справки в ПУТИ ПОИСКА.

Меню (класс :class:`~torrcast.facts.Facts`) уже прикрыто своими тестами: источник
лёг - строка печатается прежней, бюджет не превышен. А вот :func:`~torrcast.facts.origin`
- это отдельный вход к той же справке, которым ходит ВТОРОЙ ЯЗЫК поиска
(:func:`torrcast.cli._second_language`), и на него тестов не было. Ограждение у него то же
самое: справка не вправе ни ронять поиск, ни задерживать его сверх бюджета, а когда её
нет - запрос латиницей всё равно собирается (из выдачи, а в пределе транслитом).

Сломай fallback - и эти тесты покраснеют:
* убери ``contextlib.suppress`` / поток в :func:`origin` - тест на мёртвую справку
  начнёт видеть исключение или зависание;
* урежь транслит-ветку :func:`~torrcast.parse.alt_query` - тест на второй язык потеряет
  «brat» и вернёт пусто, то есть второй заход поиска умрёт вместе со справкой.
"""

from __future__ import annotations

import time
from typing import Any

from torrcast import facts as facts_mod
from torrcast.facts import Origin, origin
from torrcast.parse import alt_query, transliterate


def test_origin_yields_empty_when_the_reference_raises(monkeypatch: Any) -> None:
    """Справка (Википедия/Wikidata) отвечает ошибкой - паспорт пуст, поиск не падает."""
    monkeypatch.setattr(facts_mod, "_cached_origin", lambda title, series: None)

    def dead(*_a: Any, **_k: Any) -> Origin:
        raise OSError("getaddrinfo: сети нет")

    monkeypatch.setattr(facts_mod, "origin_now", dead)
    # Ключевое: НЕ исключение наружу, а пустой паспорт. Иначе упал бы весь поиск.
    assert origin("Восхождение") == Origin()


def test_origin_never_blocks_past_budget_when_the_reference_hangs(monkeypatch: Any) -> None:
    """Справка молчит (залипший сокет) - origin уходит по бюджету, а не держит поиск."""
    monkeypatch.setattr(facts_mod, "_cached_origin", lambda title, series: None)

    def never(*_a: Any, **_k: Any) -> Origin:
        time.sleep(30)
        return Origin(title="Ascension")

    monkeypatch.setattr(facts_mod, "origin_now", never)
    started = time.monotonic()
    found = origin("Восхождение", budget=0.3)
    elapsed = time.monotonic() - started
    assert found == Origin(), "залипшая справка не должна протащить свой ответ"
    assert elapsed < 3.0, "origin обязан вернуться по бюджету, а не ждать сокет"


def test_the_second_language_query_survives_a_dead_reference(monkeypatch: Any) -> None:
    """Справка легла И в выдаче нет латиницы - второй язык поиска всё равно собран транслитом.

    Это сквозная проверка «справка легла -> поиск живёт»: сперва мёртвая справка отдаёт
    пустой паспорт (``known=""``), затем :func:`alt_query` без единой раздачи с оригиналом
    честно берёт транслит запроса - именно этим именем :func:`_second_language` идёт на
    второй круг по индексерам.
    """
    monkeypatch.setattr(facts_mod, "_cached_origin", lambda title, series: None)
    monkeypatch.setattr(facts_mod, "origin_now", lambda *_a, **_k: (_ for _ in ()).throw(OSError()))

    known = origin("Брат").title
    assert known == "", "мёртвая справка не даёт оригинала"
    # Выдачи с латинским оригиналом нет - остаётся только сам запрос латиницей.
    assert alt_query("Брат", [], known=known) == transliterate("Брат") == "brat"
