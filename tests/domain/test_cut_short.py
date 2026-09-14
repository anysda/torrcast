"""Урезанный круг: ноль опорного по отсечке переходника отличается от честного нуля."""

import importlib.util
from pathlib import Path

from torrcast.domain.circle_budget import FIRST_CIRCLE_TIMEOUT
from torrcast.domain.cut_short import ADAPTER_CUT, cut_short


def test_a_waited_source_empty_at_the_adapter_cut_cuts_the_circle() -> None:
    """🔴 «Тачки» 4 раздачи вместо 32: JacRed сдался на отсечке и отдал ноль."""
    counts = {"JacRed": 0, "Knaben": 0, "RuTor": 12, "YTS": 0}
    spent = {"JacRed": 5040, "Knaben": 310, "RuTor": 700, "YTS": 5900}

    assert cut_short(counts, spent) == ("JacRed",)
    assert cut_short({**counts, "JacRed": 72}, spent) == ()
    assert cut_short(counts, {**spent, "JacRed": 980}) == ()


def test_the_adapter_cut_is_the_adapters_own_and_fits_the_first_circle() -> None:
    """Отсечка названа дважды, переходником и кругом: разойдись они, ноль снова врёт."""
    spec = importlib.util.spec_from_file_location(
        "jacred_indexer", Path(__file__).parents[2] / "scripts/jacred-indexer.py"
    )
    assert spec and spec.loader
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

    assert adapter.TIMEOUT == ADAPTER_CUT
    assert 4.7 < ADAPTER_CUT < FIRST_CIRCLE_TIMEOUT
