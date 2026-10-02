"""Проверяет, какое соединение хранится для следующего запроса, а какое закрывается."""

from __future__ import annotations

from torrcast.adapters.wiki.kept_connections import (
    FRESH_FOR,
    KEPT_PER_HOST,
    USES,
    KeptConnections,
)


class _Connection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Answer:
    def __init__(self, will_close: bool = False, read: bool = True) -> None:
        self.will_close = will_close
        self.read = read

    def isclosed(self) -> bool:
        return self.read


def test_a_finished_keep_alive_answer_leaves_its_connection_for_the_next_request() -> None:
    kept, connection = KeptConnections(), _Connection()

    kept.give("ru.wikipedia.org", connection, _Answer())

    assert kept.take("en.wikipedia.org") is None, "соединение ушло к чужому хосту"
    assert kept.take("ru.wikipedia.org") is connection
    assert kept.take("ru.wikipedia.org") is None, "одно соединение выдано двоим"
    assert not connection.closed


def test_a_closing_or_unread_answer_closes_its_connection() -> None:
    kept = KeptConnections()
    closing, unread, unknown = _Connection(), _Connection(), _Connection()

    kept.give("host", closing, _Answer(will_close=True))
    kept.give("host", unread, _Answer(read=False))
    kept.give("host", unknown, object())

    assert closing.closed and unread.closed and unknown.closed
    assert kept.take("host") is None


def test_a_connection_idle_too_long_is_closed_not_reused() -> None:
    now = [0.0]
    kept, connection = KeptConnections(lambda: now[0]), _Connection()
    kept.give("host", connection, _Answer())

    now[0] = FRESH_FOR + 1.0

    assert kept.take("host") is None
    assert connection.closed


def test_no_more_than_the_host_limit_is_kept() -> None:
    kept = KeptConnections()
    connections = [_Connection() for _ in range(KEPT_PER_HOST + 1)]

    for connection in connections:
        kept.give("host", connection, _Answer())

    assert connections[-1].closed
    assert not any(connection.closed for connection in connections[:-1])


#: Последний ответ, который соединение с подсказчиком IMDb отдавало из дома: затык ловился на
#: 9-10-м запросе соединения (стенд 02-10-2026, 30 затыков на 360 запросов, все там).
_LAST_SAFE_ANSWER = 8


def test_a_connection_retires_before_the_answer_its_home_route_stalls_on() -> None:
    """Соединение к IMDb закрывается не позже 8-го ответа и на 9-й запрос не идёт."""
    ((host, _),) = USES.items()
    kept, connection = KeptConnections(), _Connection()
    answered = 0
    while answered < _LAST_SAFE_ANSWER:
        answered += 1
        kept.give(host, connection, _Answer())
        if kept.take(host) is None:
            break
    else:
        stalls = _LAST_SAFE_ANSWER + 1
        raise AssertionError(f"соединение пошло на {stalls}-й запрос, где оно глохнет")
    assert connection.closed, f"отслужившее соединение после {answered}-го ответа не закрыто"
    assert answered > 1, "соединение не держится и на второй запрос"


def test_a_host_without_a_term_keeps_its_connection() -> None:
    """У CDN затык на НОВОМ соединении: смена после шести ответов там множила бы затыки."""
    kept, connection = KeptConnections(), _Connection()
    for _ in range(3 * max(USES.values())):
        kept.give("m.media-amazon.com", connection, _Answer())
        assert kept.take("m.media-amazon.com") is connection
    assert not connection.closed
