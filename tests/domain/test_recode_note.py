"""Проверки пояснения сплошного перекода."""

from torrcast.domain.recode_note import recode_note


def test_plain_note() -> None:
    assert recode_note("hevc") == "видео hevc - перекодирую на ходу целиком"
