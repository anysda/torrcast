"""Проверяет разбор описки: подсказки Википедии и поиск по куску заголовка."""

import threading
import time
from typing import Any

from tests import thread_guard
from tests.articles import STRANGERS, SURPRISED, page
from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.wiki_spelling import WikiSpelling


def _client(suggest: list[Any], phrase: list[Any]) -> FakeJsonClient:
    """Подсказчик и поиск по куску отвечают своими списками статей."""

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        if params.get("generator") == "prefixsearch":
            return {"query": {"pages": suggest}}
        return {"query": {"pages": phrase}}

    return FakeJsonClient(answer)


def test_a_name_found_by_likeness_says_so_in_the_passport() -> None:
    """🔴 TC-253. Имя, найденное по сходству, помечается: гейту добора это не имя картины.

    Спросили «мужчина который удивил всех» - статьи с таким заголовком в Википедии нет, и
    поиск по куску приводит к «Человек, который удивил всех»: слово человек помнит не то,
    а имя за ним стоит целиком. Паспорт отдаётся (имя латиницей всё-таки лучше транслита),
    но отдаётся с отметкой ``guessed``.
    """
    close = page("Человек, который удивил всех", SURPRISED, english="The Man Who Surprised")
    spelling = WikiSpelling(_client([], [close]))

    found = spelling.look("мужчина который удивил всех", False, 1.0)

    assert found.title == "The Man Who Surprised"
    assert found.name == "Человек, который удивил всех"
    assert found.guessed, "имя лишь похоже - паспорт обязан это сказать"
    assert found.year is None


def test_a_stranger_one_word_away_is_not_offered_at_all() -> None:
    """🔴 TC-284. Чужая картина в одном слове от запроса не доезжает даже догадкой.

    Статьи «Все мы незнакомцы» в Википедии нет, и подсказчик приносит «Все мы убийцы» -
    французскую картину 1952 года. За совпавшим «Все мы» картины не стоит, и последний шаг
    справки честно остаётся ни с чем.
    """
    wrong = page("Все мы убийцы", STRANGERS)
    spelling = WikiSpelling(_client([wrong], []))

    found = spelling.look("Все мы незнакомцы", False, 1.0)

    assert not found.title, "чужой оригинал уводит добор к чужой картине"
    assert not found.name
    assert not found.guessed


def test_the_suggester_is_asked_both_in_russian_and_in_latin() -> None:
    """Аниме русская Википедия подписывает латиницей: «ре зеро» находится как ``re zero``."""
    client = _client([], [])
    WikiSpelling(client).look("ре зеро", False, 1.0)

    asked = {params.get("gpssearch") for _host, _path, params in client.calls}
    assert {"ре зеро", "re zero"} <= asked


def test_a_short_name_is_never_searched_by_a_piece_of_itself() -> None:
    """У двух слов кусок - это одно слово, а одним словом совпадает пол-Википедии."""
    client = _client([], [])
    WikiSpelling(client).look("сальтберн", False, 1.0)

    assert not [params for _host, _path, params in client.calls if "intitle" in str(params)]


def test_the_spelling_wave_is_closed_by_the_one_who_raised_it() -> None:
    """🔴 TC-723. Разбор описки закрывает за собой поднятые нитки, а не бросает доживать.

    Три способа спросить идут разом, каждый своей ниткой. Брошенная по сроку нитка не
    исчезает: она доживает свой залипший запрос уже в чужой работе - в бою это показ, в
    прогоне соседняя проба, и красным там оказывается невиновный. Мера тут не «сколько
    ждали», а «что осталось живым»: её и спрашивает сторож (:mod:`tests.thread_guard`).

    Платит закрытие нитка выборки по имени, которая сюда и позвала: человек к этой
    секунде отпущен потолком паспорта и ничего тут не ждёт.
    """
    late = threading.Event()

    def slow(host: str, path: str, params: dict[str, str]) -> Any:
        late.wait(0.5)  # Википедия отвечает, но много позже отведённого срока
        return {"query": {"pages": []}}

    before = thread_guard.alive()
    started = time.monotonic()

    WikiSpelling(FakeJsonClient(slow)).look("три слова тут", False, 0.05)

    left = thread_guard.alive() - before
    assert not left, f"нитки закрыл тот, кто их поднял, а живыми осталось {len(left)}: {left}"
    assert time.monotonic() - started >= 0.5, "ответ отдан после закрытия, а не вместо него"
