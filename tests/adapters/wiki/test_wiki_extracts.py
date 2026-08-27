"""Проверяет выделенную единицу пакетного запроса статей."""

from tests.articles import wiki_reply
from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.wiki_extracts import wiki_extracts


def test_the_wave_names_the_picture_whose_whole_request_answered() -> None:
    key = ("Тачки", 2006)

    candidates, _payload, answered = wiki_extracts(
        FakeJsonClient(lambda host, path, params: wiki_reply()), [key], 1.0
    )

    assert candidates[key][0] == "Тачки"
    assert answered == {key}
