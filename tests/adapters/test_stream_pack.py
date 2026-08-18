"""Проверяет полноту набора имён, который собирает пакет упаковщика."""

from torrcast.adapters import stream_pack
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.pack_start import pack_start


def test_every_promised_name_really_lives_here() -> None:
    """Обещанное в ``__all__`` обязано разрешаться: по этому списку модуль читают зовущие.

    Единицы разъехались по файлам, и пропавшее имя ломает не пакет, а того, кто
    берёт упаковщик целиком, - на импорте, то есть весь показ разом.
    """
    missing = [name for name in stream_pack.__all__ if not hasattr(stream_pack, name)]
    assert not missing, f"пакет упаковщика потерял: {missing}"


def test_the_names_are_the_very_units_and_not_copies() -> None:
    """Собирается тот же объект, что и по новому пути: копия разъехалась бы молча."""
    assert stream_pack.Grid is Grid
    assert stream_pack.pack_start is pack_start
