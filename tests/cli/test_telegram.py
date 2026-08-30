"""Проверки команды настройки Telegram."""

from torrcast.cli.telegram import telegram
from torrcast.domain.args import Args


def test_command_passes_the_language_seam_to_wizard() -> None:
    seen: list[str | None] = []

    def setup(lang: str | None) -> int:
        seen.append(lang)
        return 0

    assert telegram(Args(query=[], telegram=True, language="ru"), setup) == 0
    assert seen == ["ru"]


def test_without_a_flag_the_language_is_left_to_the_wizard_itself() -> None:
    """`None` - это «язык не назван»: мастер возьмёт его из настройки, а не английский."""
    seen: list[str | None] = []

    def setup(lang: str | None) -> int:
        seen.append(lang)
        return 0

    assert telegram(Args(query=[], telegram=True), setup) == 0
    assert seen == [None]
