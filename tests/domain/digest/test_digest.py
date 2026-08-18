"""Зеркало :mod:`torrcast.domain.digest`: разбор ленты следа в человеческий текст.

Событийные строки и их числа сторожит набор следа (``tests/test_trace.py``). Здесь - то,
что делает разбор разбором: сеансы отделены друг от друга, свежий стоит первым, потолок
режет старые, а не новые, и итог сеанса считает по своей ленте, а не по всей неделе.
"""

from __future__ import annotations

from typing import Any

from torrcast.domain.digest import digest

HOUR = 3600.0


def rebuffer(sid: str, at: float) -> dict[str, Any]:
    """Один ребуфер сеанса ``sid``: событие, которое печатается в итоге всегда."""
    return {"at": at, "sid": sid, "phase": "show", "event": "buffering"}


def segment(sid: str, at: float, source: str) -> dict[str, Any]:
    """Отданный приёмнику кусок с названным источником: из упаковки или из прогретого."""
    return {"at": at, "sid": sid, "phase": "show", "event": "segment", "src": source}


def test_each_session_gets_its_own_block_instead_of_one_running_tape() -> None:
    """Сеанс - это все записи с одним идентификатором, и в выжимке он свой блок.

    Слипнись два сеанса в один - счётчики итога сложились бы, и вчерашний фильм с двумя
    ребуферами вместе с сегодняшним чистым показом читались бы как один плохой вечер.
    """
    rows = [rebuffer("вчера", 1.0), rebuffer("сегодня", HOUR), rebuffer("вчера", 2.0)]

    blocks = digest(rows, limit=0).split("\n\n")

    assert len(blocks) == 2
    by_sid = {block.splitlines()[0]: block for block in blocks}
    assert any("вчера" in head for head in by_sid)
    assert any("сегодня" in head for head in by_sid)
    older = next(block for head, block in by_sid.items() if "вчера" in head)
    assert "ребуферов 2" in older, "итог сеанса считается по его собственным записям"


def test_a_change_of_source_is_counted_in_the_summary_and_a_steady_one_is_not() -> None:
    """Стык источника - это СМЕНА, а не всякий кусок: считается переход, а не лента.

    Стыки читают затем, что ребуфер на границе прогретого и упакованного - отдельная
    болезнь показа. Посчитай вместо переходов сами куски - и любой ровный показ обвинялся
    бы в десятках стыков; не считай вовсе - и настоящая склейка терялась бы в итоге. Первый
    кусок сеанса переходом не считается: у него нет предыдущего источника.
    """
    steady = digest([segment("ровный", 1.0, "warm"), segment("ровный", 2.0, "warm")])
    once = digest([segment("склейка", 1.0, "warm"), segment("склейка", 2.0, "pack")])
    twice = digest(
        [
            segment("метания", 1.0, "warm"),
            segment("метания", 2.0, "pack"),
            segment("метания", 3.0, "pack"),
            segment("метания", 4.0, "warm"),
        ]
    )

    assert "стыков источника" not in steady, "источник не менялся - и стыка не было"
    assert "стыков источника 1" in once
    assert "стыков источника 2" in twice, "считаются все переходы, а не факт того, что был"


def test_the_freshest_session_is_the_one_a_human_reads_first() -> None:
    """Порядок - от свежих: разбирают обычно то, что случилось только что.

    Лента лежит по возрастанию времени, и печатай выжимка её как есть - последний показ
    оказался бы в самом низу, за неделей чужих сеансов.
    """
    rows = [rebuffer("первый", 1.0), rebuffer("второй", HOUR), rebuffer("третий", 2 * HOUR)]

    heads = [block.splitlines()[0] for block in digest(rows, limit=0).split("\n\n")]

    assert "третий" in heads[0]
    assert "второй" in heads[1]
    assert "первый" in heads[2]


def test_the_limit_drops_the_old_sessions_and_never_the_new_ones() -> None:
    """Потолок числа сеансов режет с хвоста - иначе он прятал бы то, ради чего его открыли.

    ``0`` при этом значит «все»: неделю целиком тоже надо уметь показать, и путать это с
    «ни одного» нельзя.
    """
    rows = [rebuffer("первый", 1.0), rebuffer("второй", HOUR), rebuffer("третий", 2 * HOUR)]

    trimmed = digest(rows, limit=1)

    assert "третий" in trimmed
    assert "второй" not in trimmed and "первый" not in trimmed
    assert len(digest(rows, limit=0).split("\n\n")) == 3


def test_a_clean_show_says_zero_rebuffers_out_loud() -> None:
    """Ноль ребуферов - тоже новость, и молчать о нём нельзя.

    Пропусти выжимка нулевой счётчик - чистый показ и показ, про который лента ничего не
    знает, выглядели бы одинаково, а это ровно тот вопрос, ради которого след и читают.
    """
    quiet = digest([{"at": 1.0, "sid": "тихий", "phase": "show", "event": "session_end"}])

    assert "ребуферов 0" in quiet


def test_an_empty_trace_is_a_sentence_and_not_an_empty_screen() -> None:
    """Пустая лента - это ответ, а не отсутствие ответа.

    Верни разбор пустую строку - человек решил бы, что сломалась сама команда, и пошёл бы
    чинить инструмент вместо того, чтобы включить след.
    """
    assert digest([]).strip()
