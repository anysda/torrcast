"""Прогрев показа на диск: весь фильм заранее, чтобы обрыв связи его не убил.

Показ живёт окном в tmpfs (:class:`torrcast.stream.Feed`), и это окно упирается в
сеть: пропал интернет — упаковке нечего читать, и через минуту на экране пусто.
Прогрев закрывает ровно эту дыру: фоном, на остатке процессора, весь фильм
докачивается и (где надо) перекодируется **на диск**, теми же именами той же сетки.
Добежал прогрев до конца — дальше показ и перемотки идут вообще без сети.

Три вещи, на которых всё держится:

* **сетка детерминирована.** Сегмент ``vN.ts`` — это всегда одно и то же место фильма,
  с какого бы места ни начали паковать (:class:`torrcast.stream.Grid`). Поэтому
  прогретый кусок и живой кусок взаимозаменяемы: показ берёт тот, который есть
  (:meth:`torrcast.stream.Feed.segment`);
* **прогретое лежит на диске, а не в tmpfs.** Целый фильм в памяти контейнера не
  помещается: 9 Мбит/с × 3 ч — это 12–13 ГБ, а вся RAM — 8 ГиБ. Живое окно остаётся
  в ``/dev/shm``, как было;
* **прогрев не имеет права мешать показу.** Он идёт ``nice`` и в темпе, который
  задан :attr:`Warmer.rate`, а когда запас живого показа проседает — встаёт
  (``SIGSTOP``) и ждёт. Приоритет всегда у того места, где смотрят прямо сейчас.

⚠️ ``nice`` тут не приоритет, а вежливость, и она не работает. Замер на 4 vCPU,
настоящий материал: живой перекод тяжёлого куска идёт 2.62× реального времени на пустой
машине и 1.84× — рядом с прогревом под ``nice 19``, который держит 128 % из 400 %.
Ни ``-threads 2`` у прогрева (2.04×), ни ``cpu.weight=1`` в отдельной cgroup (2.30×) дыру
не закрывают: и то и другое лишь ограничивает соседа, а процессор освобождается только
тогда, когда сосед не работает вовсе. Поэтому у прогрева есть вторая, жёсткая причина
замереть (:meth:`Warmer._must_yield`): пока у живого кодировщика идёт заход
(:attr:`torrcast.recode.Recoder.working`), прогрев стоит. С ``SIGSTOP`` тот же перекод
идёт 2.62× — вровень с пустой машиной.

⚠️ **Один показ — один прогон ffmpeg.** Кадровая сетка AAC отсчитывается от ``-ss``
прогона, поэтому стык двух прогонов — это дыра до 21 мс в звуке, за которую Q70D
платит 2–5 секундами пересборки синхронизации (докстринг
:func:`torrcast.stream.merge_tracks`). Отсюда и устройство прогрева: не «заходы по N
кусков», а один прогон от места показа до конца фильма, который на просадке запаса
**замирает**, а не перезапускается. Второй прогон бывает ровно один — на голову
фильма, когда показ начат с середины, и его стык лежит там, где стык прогонов есть
и в живом показе.
"""

from __future__ import annotations

from torrcast.domain.warm_settings import WARM_BUDGET as WARM_BUDGET
from torrcast.domain.warm_settings import WARM_DIR as WARM_DIR
from torrcast.usecases.warm._state import Grid as Grid
from torrcast.usecases.warm.configure import configure as configure
from torrcast.usecases.warm.segment_start import segment_start
from torrcast.usecases.warm.settings import CHAIN_RETRY as CHAIN_RETRY
from torrcast.usecases.warm.settings import FREE_FLOOR as FREE_FLOOR
from torrcast.usecases.warm.settings import GUARD_HIGH as GUARD_HIGH
from torrcast.usecases.warm.settings import GUARD_LOW as GUARD_LOW
from torrcast.usecases.warm.settings import HEAD_BYTES as HEAD_BYTES
from torrcast.usecases.warm.settings import META as META
from torrcast.usecases.warm.settings import PCR_CLOCK as PCR_CLOCK
from torrcast.usecases.warm.settings import PES_CLOCK as PES_CLOCK
from torrcast.usecases.warm.settings import RUN_DIR as RUN_DIR
from torrcast.usecases.warm.settings import SKEW_MAX as SKEW_MAX
from torrcast.usecases.warm.settings import SKEW_TRIES as SKEW_TRIES
from torrcast.usecases.warm.settings import START_GRACE as START_GRACE
from torrcast.usecases.warm.settings import STARVE_GRACE as STARVE_GRACE
from torrcast.usecases.warm.settings import TS_PACKET as TS_PACKET
from torrcast.usecases.warm.settings import TS_SYNC as TS_SYNC
from torrcast.usecases.warm.settings import WARM_ENV as WARM_ENV
from torrcast.usecases.warm.settings import WARM_NICE as WARM_NICE
from torrcast.usecases.warm.settings import WARM_RATE as WARM_RATE
from torrcast.usecases.warm.vault import Vault
from torrcast.usecases.warm.warm_key import warm_key
from torrcast.usecases.warm.warm_root import warm_root
from torrcast.usecases.warm.warmer import Warmer

__all__ = ["Vault", "Warmer", "segment_start", "warm_key", "warm_root"]
