"""Запуск приложения отдельным процессом: ``python -m torrcast.runtime``.

Этой строкой поднимается показ в юните ``torrcast-play``
(:func:`torrcast.adapters.systemd.start_play_unit.start_play_unit`). Console-script
``cast`` юниту не годится: ему нужен ровно тот интерпретатор, в котором лежит пакет.
Вход при этом обязан быть тем же самым, что у ``cast``, - то есть через композиционный
корень, иначе процесс показа получит пустые порты вместо внешнего мира.
"""

import sys

from torrcast.runtime.main import main

if __name__ == "__main__":
    sys.exit(main())
