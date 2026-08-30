"""Проверки команды настройки Telegram."""

from torrcast.cli.telegram import telegram
from torrcast.domain.args import Args


def test_command_passes_the_language_seam_to_wizard() -> None:
    seen: list[str] = []

    def setup(lang: str) -> int:
        seen.append(lang)
        return 0

    assert telegram(Args(query=[], telegram=True, language="ru"), setup) == 0
    assert seen == ["ru"]
