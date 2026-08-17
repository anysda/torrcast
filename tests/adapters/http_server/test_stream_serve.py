"""Проверяет прежний путь к внешней части медиатракта и полноту его набора имён."""

import torrcast.stream_serve as facade
from torrcast.adapters.http_server import stream_serve
from torrcast.adapters.http_server.hls_server import HlsServer
from torrcast.adapters.systemd.start_play_unit import start_play_unit


def test_facade_points_to_adapter() -> None:
    assert facade is stream_serve


def test_every_promised_name_really_lives_here() -> None:
    """Обещанное в ``__all__`` обязано разрешаться: по этому списку модуль читает фасад.

    Разъехавшиеся единицы собираются здесь заново, и пропавшее имя ломает не этот
    модуль, а :mod:`torrcast.stream` - на импорте, то есть весь показ разом.
    """
    missing = [name for name in stream_serve.__all__ if not hasattr(stream_serve, name)]
    assert not missing, f"прежний путь потерял: {missing}"


def test_the_names_are_the_very_units_and_not_copies() -> None:
    """Собирается тот же объект, что и по новому пути: копия разъехалась бы молча."""
    assert stream_serve.HlsServer is HlsServer
    assert stream_serve.start_play_unit is start_play_unit


def test_an_empty_value_is_not_a_string() -> None:
    """``_opt_str``: пусто и ``None`` - это «поля нет», а не строка «None»."""
    assert stream_serve._opt_str(None) is None
    assert stream_serve._opt_str("") is None
    assert stream_serve._opt_str(0) == "0"
    assert stream_serve._opt_str("rus") == "rus"
