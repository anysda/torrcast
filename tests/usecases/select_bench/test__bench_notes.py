"""Зеркало строк перед стартом и запасного хода, когда русской нет ни у кого."""

from __future__ import annotations

import pytest

from tests.usecases.select_bench.world import RUNTIME, Torrents, plan, probes, rel
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench.bench import Bench


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские строки перед стартом и запасного хода."""


GB = 1024**3


def _prep(media: Media, number: int = 1, size_gb: float = 8.0, name: str | None = None) -> _Prep:
    prep = _Prep(number=number, release=rel() if name is None else rel(name=name))
    prep.media = media
    prep.video = TorrFile(0, "movie.mkv", int(size_gb * GB))
    return prep


def test_a_whole_recode_is_never_silent(capsys: pytest.CaptureFixture[str]) -> None:
    """Молчаливых подмен нет: перекод целиком - решение показа, и человек его слышит."""
    bench = Bench(Torrents(), prober=probes([]))
    hevc = _prep(Media(RUNTIME, (), "hevc", height=1080, width=1920))

    bench._announce(plan([rel()]), hevc, [1], {}, 1)

    assert "recod" in capsys.readouterr().out.casefold()


def test_a_copy_playable_release_needs_no_word_at_all(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Играется копией и ступень не снижена - говорить не о чем."""
    bench = Bench(Torrents(), prober=probes([]))
    plain = _prep(Media(RUNTIME, (), "h264", height=1080, width=1920))

    bench._announce(plan([rel()]), plain, [1], {}, 1)

    assert capsys.readouterr().out == ""


def test_the_last_hope_of_the_mute_fallback_is_loud(capsys: pytest.CaptureFixture[str]) -> None:
    """🔴 TC-178. Русской нет ни у кого - играем то, что есть, и говорим об этом вслух."""
    bench = Bench(Torrents(), prober=probes([]))
    japanese = _prep(
        Media(RUNTIME, (AudioTrack(index=0, language="jpn"),), "h264", height=1080, width=1920)
    )

    played = bench._mute_fallback(plan([rel()]), japanese, [1, 2], {}, 1, tried=2)

    assert played is japanese
    assert "русской озвучки нет ни в одной из проверенных раздач (2)" in capsys.readouterr().out


def test_the_release_name_does_not_soften_the_fallback_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-741. Строку запасного хода пишет паспорт, а не имя раздачи.

    «Дубляж» в имени русской дорожки не гарантирует (TC-191), и мягкой формулировки под
    него не заводится: играет то, что ffprobe прочитал, и зовётся оно тем же словом.
    Прежде имя покупало отдельную строку «имя релиза обещает русский» - обещание вместо
    факта, ровно там, где про факт ничего не известно.
    """
    bench = Bench(Torrents(), prober=probes([]))
    unnamed = _prep(
        Media(RUNTIME, (AudioTrack(index=0),), "h264", height=1080, width=1920),
        name="Кино / Movie (1999) BDRip 1080p | Дубляж",
    )

    bench._mute_fallback(plan([rel()]), unnamed, [1], {}, 1, tried=1)

    said = capsys.readouterr().out
    assert "включаю релиз 1, звук не назван" in said
    assert "обещает русский" not in said
