"""Проверки решения о сплошном перекоде."""

from torrcast.domain.recodes_whole import recodes_whole


def test_cautious_profile_recodes_hevc() -> None:
    assert recodes_whole("hevc")
