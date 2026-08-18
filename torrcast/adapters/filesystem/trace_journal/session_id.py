"""Идентификатор сеанса, которым склеиваются записи одного ``cast``.

Ставит его в каждую запись :func:`emit`, а в окружение юнита показа - сам показ."""

from __future__ import annotations

import os
import time
from typing import Final

#: Общий идентификатор сеанса у команды и у юнита показа. Ставится в окружение и едет в
#: юнит вместе с прочими путями (:data:`torrcast.domain.unit_naming._PASS_ENV`), поэтому поиск, отбор
#: и показ одного ``cast`` сводятся в одну строку истории.
SID_ENV: Final = "TORRCAST_SID"


def session_id() -> str:
    """Идентификатор сеанса; лениво создаётся и кэшируется в окружении под :data:`SID_ENV`."""
    sid = os.environ.get(SID_ENV)
    if not sid:
        sid = f"{int(time.time())}-{os.getpid()}"
        os.environ[SID_ENV] = sid
    return sid
