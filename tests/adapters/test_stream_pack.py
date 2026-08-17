"""Проверяет прежнее имя упаковщика и полноту набора имён, который оно собирает."""

import torrcast.stream_pack as facade
from torrcast.adapters import stream_pack
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.pack_start import pack_start


def test_old_module_name_is_adapter() -> None:
    assert facade is stream_pack


def test_every_promised_name_really_lives_here() -> None:
    """Обещанное в ``__all__`` обязано разрешаться: по этому списку модуль читает фасад.

    Единицы разъехались по файлам, и пропавшее имя ломает не пакет, а
    :mod:`torrcast.stream` - на импорте, то есть весь показ разом.
    """
    missing = [name for name in stream_pack.__all__ if not hasattr(stream_pack, name)]
    assert not missing, f"прежнее имя упаковщика потеряло: {missing}"


def test_the_names_are_the_very_units_and_not_copies() -> None:
    """Собирается тот же объект, что и по новому пути: копия разъехалась бы молча."""
    assert stream_pack.Grid is Grid
    assert stream_pack.pack_start is pack_start
