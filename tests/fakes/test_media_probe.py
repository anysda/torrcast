"""Зеркало :mod:`tests.fakes.media_probe`."""

from tests.fakes.media_probe import RUNTIME, FakeMediaProbe


def test_fake_answers_by_the_fragment_of_the_url_and_records_every_ask() -> None:
    fake = FakeMediaProbe({"hash-a/": "jpn"})

    japanese = fake("http://ts/hash-a/1.mkv")
    russian = fake("http://ts/hash-b/1.mkv")

    assert japanese.tracks[0].language == "jpn"
    assert russian.tracks[0].language == "rus"
    assert japanese.duration == RUNTIME
    assert fake.asked == ["http://ts/hash-a/1.mkv", "http://ts/hash-b/1.mkv"]


def test_fake_lets_the_test_name_the_language_of_the_rest() -> None:
    fake = FakeMediaProbe(default="eng")

    assert fake("http://ts/hash-a/1.mkv").tracks[0].language == "eng"
