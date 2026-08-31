"""Проверки команды настройки Telegram."""

from torrcast.cli.telegram import telegram
from torrcast.domain.args import Args


def test_command_runs_the_wizard() -> None:
    calls: list[int] = []

    def setup() -> int:
        calls.append(1)
        return 0

    assert telegram(Args(query=[], telegram=True), setup) == 0
    assert calls == [1]


def test_the_language_flag_is_not_the_wizards_concern() -> None:
    """Флаг `--ru` до мастера уже лёг в настройку командой языка
    (:func:`torrcast.cli.main.main`), и мастер берёт язык у единого держателя,
    а не параметром из argv.
    """
    calls: list[int] = []

    def setup() -> int:
        calls.append(1)
        return 0

    assert telegram(Args(query=[], telegram=True, language="ru"), setup) == 0
    assert calls == [1]
