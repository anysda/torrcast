"""Зеркало :mod:`torrcast.domain.living_part`: кто на самом деле занимает номер части."""

from torrcast.domain.living_part import _living_part
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(title: str, year: int, part: int | None = None, copies: int = 1) -> Picture:
    return Picture(
        title=title,
        year=year,
        part=part,
        releases=[Release(raw_name=title, title=title) for _ in range(copies)],
    )


LINE = [_picture("Первая", 1997, part=1)]


def test_a_newer_and_livelier_picture_takes_the_place_of_the_numbered_one() -> None:
    """Номер в названии - обещание, а не факт: живее оказалась картина без номера."""
    claimant = _picture("Названа второй", 2000, part=2, copies=1)
    rival = _picture("Настоящее продолжение", 2015, copies=20)

    assert _living_part([claimant, rival], LINE, 2, claimant) is rival


def test_the_claimant_keeps_the_place_while_nobody_is_livelier() -> None:
    claimant = _picture("Названа второй", 2000, part=2, copies=20)
    rival = _picture("Тихое продолжение", 2015, copies=1)

    assert _living_part([claimant, rival], LINE, 2, claimant) is None


def test_a_picture_older_than_the_previous_part_claims_nothing() -> None:
    """Претендент обязан быть новее предыдущей части, иначе это не продолжение."""
    claimant = _picture("Названа второй", 2000, part=2, copies=1)
    older = _picture("Старое кино", 1990, copies=20)

    assert _living_part([claimant, older], LINE, 2, claimant) is None


def test_without_a_previous_part_there_is_nothing_to_continue() -> None:
    claimant = _picture("Названа второй", 2000, part=2, copies=1)
    rival = _picture("Новьё", 2015, copies=20)

    assert _living_part([claimant, rival], [], 2, claimant) is None
