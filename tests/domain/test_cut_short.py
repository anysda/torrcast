"""Урезанный круг: ноль опорного по отсечке переходника отличается от честного нуля."""

from torrcast.domain.circle_budget import FIRST_CIRCLE_TIMEOUT
from torrcast.domain.cut_short import ADAPTER_CUT, cut_short


def test_a_waited_source_empty_at_the_adapter_cut_cuts_the_circle() -> None:
    """🔴 «Тачки» 4 раздачи вместо 32: JacRed сдался на отсечке и отдал ноль."""
    counts = {"JacRed": 0, "Knaben": 0, "RuTor": 12, "YTS": 0}
    spent = {"JacRed": 5040, "Knaben": 310, "RuTor": 700, "YTS": 5900}

    assert cut_short(counts, spent) == ("JacRed",)
    assert cut_short({**counts, "JacRed": 72}, spent) == ()
    assert cut_short(counts, {**spent, "JacRed": 980}) == ()


def test_the_adapter_cut_fits_the_first_circle() -> None:
    """The local adapter has no network timeout; the circle budget still must fit."""
    assert 4.7 < ADAPTER_CUT < FIRST_CIRCLE_TIMEOUT
