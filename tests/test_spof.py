"""Страховки на единые точки отказа справки в ПУТИ ПОИСКА.

Меню (класс :class:`~torrcast.usecases.facts.Facts`) уже прикрыто своими тестами: источник
лёг - строка печатается прежней, бюджет не превышен. А вот :func:`~torrcast.facts.origin`
- это отдельный вход к той же справке, которым ходит ВТОРОЙ ЯЗЫК поиска
(:func:`torrcast.cli._second_language`). Ограждение у него то же самое: справка не вправе
ни ронять поиск, ни задерживать его сверх бюджета, а когда её нет - запрос латиницей всё
равно собирается (из выдачи, а в пределе транслитом).

Сломай fallback - и эти тесты покраснеют:
* убери ``contextlib.suppress`` / поток в :class:`~torrcast.usecases.passport.Passport` -
  тест на мёртвую справку начнёт видеть исключение или зависание (он живёт в
  ``tests/usecases/test_passport.py``);
* урежь транслит-ветку :func:`~torrcast.domain.alt_query.alt_query` - тест на второй язык потеряет
  «brat» и вернёт пусто, то есть второй заход поиска умрёт вместе со справкой.
"""

from __future__ import annotations

from tests.fakes.article_source import FakeArticleSource
from tests.fakes.date_source import FakeDateSource
from tests.fakes.name_catalogue import FakeNameCatalogue
from tests.fakes.origin_store import FakeOriginStore
from torrcast.domain.alt_query import alt_query
from torrcast.domain.facts.origin import Origin
from torrcast.domain.transliterate import transliterate
from torrcast.usecases.passport import Passport


def test_the_second_language_query_survives_a_dead_reference() -> None:
    """Справка легла И в выдаче нет латиницы - второй язык поиска всё равно собран транслитом.

    Это сквозная проверка «справка легла -> поиск живёт»: сперва мёртвая справка отдаёт
    пустой паспорт (``known=""``), затем :func:`alt_query` без единой раздачи с оригиналом
    честно берёт транслит запроса - именно этим именем :func:`_second_language` идёт на
    второй круг по индексерам.
    """

    def dead(title: str, series: bool, timeout: float) -> Origin:
        raise OSError("getaddrinfo: сети нет")

    passport = Passport(
        FakeArticleSource(dead), FakeNameCatalogue(), FakeOriginStore(), FakeDateSource()
    )

    known = passport.of("Брат").title
    assert known == "", "мёртвая справка не даёт оригинала"
    # Выдачи с латинским оригиналом нет - остаётся только сам запрос латиницей.
    assert alt_query("Брат", [], known=known) == transliterate("Брат") == "brat"
