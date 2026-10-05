"""Checks the host queues' picture: who goes ahead of whom while the requests wait to leave."""

from __future__ import annotations

from torrcast.adapters.prowlarr.slot_line import SlotLine

_PACE = 2.0


def _line() -> tuple[SlotLine, SlotLine.Slot, SlotLine.Slot]:
    """A search's text at Knaben, then its name a pace behind it, both still waiting."""
    line = SlotLine(_PACE)
    text = line.draw("Knaben", 6.0, 100.0, spare=False)
    name = line.draw("Knaben", 6.0, 100.0, spare=True)
    assert text and name and (text.start, name.start) == (100.0, 102.0)
    return line, text, name


def test_the_viewers_text_goes_ahead_of_a_name_not_gone_yet() -> None:
    line, _text, name = _line()
    after = line.draw("Knaben", 6.0, 100.5, spare=False)
    assert after == SlotLine.Slot(1.5, 102.0, 3), "the next search's text takes the name's slot"
    assert line.start("Knaben", name.ticket) == 104.0, "the name moves a pace on"
    assert line.lag("Knaben", 100.5) == 5.5, "the host's queue grew by one slot"


def test_a_name_leaving_in_half_a_pace_is_already_ahead() -> None:
    line, _text, name = _line()
    after = line.draw("Knaben", 6.0, 101.0, spare=False)
    assert after and after.start == 104.0, "the name gets to Prowlarr first"
    assert line.start("Knaben", name.ticket) == 102.0


def test_a_name_gone_to_prowlarr_is_never_overtaken() -> None:
    line, _text, name = _line()
    line.leave("Knaben", name.ticket)
    after = line.draw("Knaben", 6.0, 100.5, spare=False)
    assert after and after.start == 104.0
    assert line.start("Knaben", name.ticket) is None, "its place is no longer ours"


def test_a_name_never_goes_ahead_of_anyone() -> None:
    line, text, _name = _line()
    other = line.draw("Knaben", 6.0, 100.5, spare=True)
    assert other and other.start == 104.0, "names queue behind every one drawn"
    assert line.start("Knaben", text.ticket) == 100.0


def test_a_name_given_back_moves_the_ones_behind_it_up() -> None:
    line, text, name = _line()
    after = line.draw("Knaben", 6.0, 100.0, spare=False)
    assert after and after.start == 102.0
    line.give_back("Knaben", text.ticket)
    assert line.start("Knaben", after.ticket) == 100.0
    assert line.start("Knaben", name.ticket) == 102.0
    assert line.lag("Knaben", 100.0) == 4.0, "the end of the queue moved up a pace"
    line.give_back("Knaben", text.ticket)
    assert line.lag("Knaben", 100.0) == 4.0, "a ticket comes back once"


def test_a_name_past_its_budget_behind_the_text_draws_nothing() -> None:
    line, _text, _name = _line()
    assert line.draw("Knaben", 4.0, 100.0, spare=True) is None, "it would start at the budget"
    assert line.lag("Knaben", 100.0) == 4.0
