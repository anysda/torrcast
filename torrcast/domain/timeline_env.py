"""Имя переменной окружения, которой включается секундомер критического пути.

Читают его и сам секундомер (:mod:`torrcast.timing`), и список того, что пробрасывается
в юнит показа (:data:`torrcast.domain.unit_naming._PASS_ENV`).
"""

from typing import Final

#: Куда писать ленту меток. Пусто - секундомера нет.
TIMELINE_ENV: Final = "TORRCAST_TIMELINE"
