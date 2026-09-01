"""Как зовётся transient-юнит показа и что ему передаётся окружением."""

from typing import Final

from torrcast.domain.timeline_env import TIMELINE_ENV

_UNIT_NAME: Final = "torrcast-play"

#: Описание юнита несёт ключ показа - по нему ``status`` знает, что играет.
_UNIT_TAG: Final = "torrcast: "

#: Куда кладёт ключ показа задание launchd: описания у него нет, зато окружение живого
#: задания показывает ``launchctl print`` - ключ читается оттуда, а не свежайшей записью
#: состояния (рядом мог писать другой ход, и ``status`` соврал бы).
_JOB_KEY_ENV: Final = "TORRCAST_PLAY_KEY"

#: Что пробрасывается в юнит: без этого показ уедет на прод-пути вместо dev-овских.
_PASS_ENV: Final = (
    "TORRCAST_CONFIG",
    "TORRCAST_STATE",
    # Каталог прогретого - такое же переопределение путей, как состояние и конфиг
    # (:data:`torrcast.usecases.warm.settings.WARM_ENV`). Без него юнит грел бы в боевое хранилище и
    # вытеснял из него чужое по бюджету, пока снаружи шёл заведомо тестовый показ.
    "TORRCAST_WARM",
    "TORRCAST_TRACE",
    "TORRCAST_CTL",
    TIMELINE_ENV,
    # Каталог недельного следа и общий id сеанса: без них показ вёл бы след в боевой
    # каталог и под другим id, и поиск с показом не склеились бы в один сеанс.
    "TORRCAST_LOG",
    "TORRCAST_SID",
)
