"""Проверки короткого объяснения ошибки."""

from torrcast.domain.why import why


class ReadTimeout(Exception):  # noqa: N818 - имя имитирует тип requests
    """Тестовый тип с именем ошибки requests."""


def test_known_reason() -> None:
    assert why(ReadTimeout()) == "не дождался ответа"
