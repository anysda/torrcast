"""Порт сетки прогрева: настоящая сетка медиатракта под договор подходит."""

from torrcast.adapters.stream_pack.grid import Grid
from torrcast.ports.warm_environment.warm_grid import WarmGrid


def test_the_media_tract_grid_fits_the_warming_contract() -> None:
    """Сетку прогреву отдаёт медиатракт, и подходит она по строению, а не по наследству.

    Проверка не косметическая: сетка и договор живут в разных слоях и разъехаться могут
    молча - сценарий прогрева получает её уже готовой и ни одного поля не заводит сам.
    """
    grid: WarmGrid = Grid(bounds=(0.0, 8.0, 16.0), duration=20.0)

    assert grid.count == 3
    assert (grid.start(1), grid.end(1), grid.span(1)) == (8.0, 16.0, 8.0)
    assert grid.duration == 20.0
    assert not grid.on_keys
    assert grid.origin == 0.0
    assert grid.weigh is None
