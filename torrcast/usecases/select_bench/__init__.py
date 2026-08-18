"""Часть CLI; публичный фасад - :mod:`torrcast.cli`.

Реэкспорт стенда отбора. Сам стенд разложен по файлам цепочкой классов: состояние у
него одно на весь обход очереди, и разнести его свободными функциями значило бы возить
это состояние доводом в каждую. Ни строчки логики тут нет - только имена.
"""

from __future__ import annotations

from torrcast.usecases.select_bench._bench_state import _configure_select_bench
from torrcast.usecases.select_bench.bench import Bench

__all__ = ["Bench", "_configure_select_bench"]
