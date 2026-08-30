"""Структурированная ошибка настройки хранит путь отдельно от готовой строки."""

from pathlib import Path

from torrcast.domain.invalid_config_object_error import InvalidConfigObjectError


def test_keeps_the_path_separate_from_the_console_message() -> None:
    """Путь переживает готовую строку: по нему беду называют заново на другом языке.

    Строку собирает тот, кто читал файл, и собирает языком продукта; телеграм-бот
    говорит языком зрителя (:func:`tgbot.i18n._failure_detail`) и пересобирает жалобу
    из пути. Разбирать чужой готовый текст ему нечем.
    """
    path = Path("/tmp/config.json")
    said = "broken config /tmp/config.json: expected a JSON object"

    error = InvalidConfigObjectError(path, said)

    assert error.path == path
    assert str(error) == said


def test_is_still_the_value_error_that_a_refused_write_was_always_raised_as() -> None:
    """Прежний договор записи поверх неразобранного файла не переписан.

    ``tgbot.config.Config._stored`` роняла запись именно ``ValueError``, и места, что
    ловят его, о новом типе не знают.
    """
    assert isinstance(InvalidConfigObjectError(Path("/tmp/config.json"), "нет"), ValueError)
