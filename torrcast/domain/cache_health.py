"""Что считается здоровым у службы раздачи и её кэша.

Зовёт сценарий :mod:`torrcast.usecases.doctor`, размеры и ответы приносит порт среды.
"""

from torrcast.domain.health_verdict import HealthLine, HealthVerdict

#: Во сколько раз память службы раздачи больше кэша, который она держит В ПАМЯТИ. Замер:
#: кэш лежит в куче Go, и рядом с каждым куском живёт его копия в работе плюс мусор,
#: который сборщик забирает уже потом. Тот же множитель считает размер кэша в
#: ``install.sh`` (``TS_MEM_OVERHEAD``) - если правишь тут, правь и там.
CACHE_OVERHEAD = 2
#: Байты, которые кэшу не отдают: система, python показа, два ffmpeg, сегменты в
#: /dev/shm (``install.sh``: ``TS_MEM_RESERVE``).
CACHE_RESERVE = 1792 * 1024 * 1024
#: Байты памяти, которые служба берёт себе, когда кэш лежит НА ДИСКЕ. Замер: 104 МиБ при
#: кэше 3.2 ГиБ и 111 МиБ при 12 ГиБ - от размера кэша это число не зависит вовсе
#: (``install.sh``: ``TS_DISK_MEM``).
CACHE_ON_DISK_MEMORY = 512 * 1024 * 1024


class CacheHealth:
    """Правила строк про раздачу: жива ли служба и во что обходится её кэш.

    Кэш - это запас показа на обрыв интернета, поэтому строки тут не про красоту: замер
    на одном фильме дал 32 минуты показа после обрыва при кэше 3.2 ГиБ и 81 минуту при
    12 ГиБ. Но платят за него разным, и проверять надо разное:

    * кэш В ПАМЯТИ платит памятью, причём ВДВОЕ против своего размера
      (:data:`CACHE_OVERHEAD`). Искать это число однажды пришлось с гипервизора: 4 ГиБ
      кэша на 8-гигабайтной машине выросли в 7.45 ГБ RSS, и она встала колом на
      четвёртой минуте показа - без ssh, без журнала;
    * кэш НА ДИСКЕ платит МЕСТОМ, а память берёт себе постоянную сотню мегабайт
      (замер: 104 МиБ при 3.2 ГиБ кэша и 111 МиБ при 12 ГиБ). Зато на том же разделе
      живёт прогрев, и упереть раздел в ноль кэшем нельзя: без прогрева обрыв убьёт
      показ ровно так же.
    """

    @staticmethod
    def gib(size: int) -> str:
        """Байты человеку: доли гигабайта тут читаются, а сами байты - нет."""
        return f"{size / 1024**3:.1f} ГиБ"

    @staticmethod
    def server(url: str, echo: str | None) -> HealthLine:
        """Служба раздачи: ``echo`` - её ответ, ``None`` - молчание."""
        if echo is None:
            return HealthVerdict.bad(f"TorrServer не отвечает ({url}) - раздачи не будет")
        return HealthVerdict.ok(f"TorrServer {echo.strip()[:20]} ({url})")

    @staticmethod
    def unreadable() -> HealthLine:
        """Настройки не прочитались: про саму службу уже сказала строка выше."""
        return HealthVerdict.warn("настройки TorrServer не читаются - размер кэша неизвестен")

    @staticmethod
    def in_memory(size: int, total: int) -> HealthLine:
        """Кэш в памяти: мера ему - память машины, и платит он вдвое против себя."""
        weight = size * CACHE_OVERHEAD
        text = (
            f"кэш раздачи {CacheHealth.gib(size)} в памяти, под показом это "
            f"~{CacheHealth.gib(weight)} памяти из {CacheHealth.gib(total)} машины"
        )
        if weight + CACHE_RESERVE > total:
            return HealthVerdict.bad(
                f"{text} - не влезает: показ уронит машину, переставь install.sh"
            )
        return HealthVerdict.ok(text)

    @staticmethod
    def on_disk(size: int, path: str, free: int, reserve: int) -> HealthLine:
        """Кэш на диске: память ему не мера, мера - место рядом с прогревом.

        ``reserve`` - байты диска, которые кэшу не отдают: рядом на том же разделе живёт
        прогрев со своим бюджетом и запасом, а также состояние и система. То же число
        складывает установка - слагаемые общие, чтобы числа не разъезжались.
        """
        text = f"кэш раздачи {CacheHealth.gib(size)} на диске ({path or 'путь не задан'})"
        if not path:
            return HealthVerdict.bad(
                f"{text} - служба положит его куда сама решит, переставь install.sh"
            )
        if not free:
            return HealthVerdict.warn(f"{text}, свободное место на разделе не читается")
        text = (
            f"{text}, память службы ~{CacheHealth.gib(CACHE_ON_DISK_MEMORY)}, "
            f"на разделе {CacheHealth.gib(free)}"
        )
        if free < reserve:
            return HealthVerdict.bad(f"{text} - прогреву места не остаётся, обрыв оборвёт показ")
        return HealthVerdict.ok(text)
