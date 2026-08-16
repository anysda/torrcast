"""Что считается здоровым у раздачи, полок и недельного следа.

Зовёт сценарий :mod:`torrcast.usecases.doctor`, диск и часы приносит порт среды.
"""

from torrcast.domain.health_verdict import HealthLine, HealthVerdict

#: За сколько дней до конца серта показ считается обречённым: меньше недели - это уже
#: «плохо», потому что чинить придётся в тот вечер, когда сядут смотреть.
CERT_FLOOR = 7


class ServeHealth:
    """Правила строк про то, чем и откуда мы раздаём, и про диагностику после."""

    @staticmethod
    def hls(base: str, error: str, https: bool, cert: str, days: int | None) -> HealthLine:
        """Адрес раздачи и, если кто-то включил https, свежесть серта."""
        if error:
            return HealthVerdict.bad(f"адрес раздачи не собирается: {error}")
        if not https:
            return HealthVerdict.ok(f"раздача {base} - ни серта, ни DNS в пути показа")
        if days is None:
            return HealthVerdict.bad(f"раздача {base}, но серт {cert} не читается")
        if days < CERT_FLOOR:
            return HealthVerdict.bad(
                f"раздача {base}, серту осталось {days} дн - показ вот-вот отвалится"
            )
        return HealthVerdict.ok(f"раздача {base}, серту осталось {days} дн")

    @staticmethod
    def shelves(
        shelf: str, keys: tuple[int, int], keys_kept: int, probe: tuple[int, int], probe_kept: int
    ) -> HealthLine:
        """Кэши карт опорных кадров и паспортов: сколько записей и сколько это весит.

        Строка одна и всегда «ок»: это не проверка, а цифра. Расти без предела полки больше
        не могут, но потолок молчаливый, а инструмент живёт годами - и место на диске лучше
        видеть числом, чем узнавать о нём от файловой системы. Потолки печатаются рядом,
        чтобы «много» и «мало» читались без документации.
        """
        return HealthVerdict.ok(
            f"кэши в {shelf}: карт {keys[0]}/{keys_kept} ({keys[1] / 1e6:.1f} МБ), "
            f"паспортов {probe[0]}/{probe_kept} ({probe[1] / 1e6:.1f} МБ)"
        )

    @staticmethod
    def ago(seconds: float) -> str:
        """Возраст записи словами: минуты, часы или дни - что уместнее."""
        if seconds < 3600:
            return f"{seconds / 60:.0f} мин"
        if seconds < 86400:
            return f"{seconds / 3600:.0f} ч"
        return f"{seconds / 86400:.0f} дн"

    @staticmethod
    def trace(found: bool, age: float, total: int, directory: str, retain_days: int) -> HealthLine:
        """Недельный след: пишется ли он вообще, свежий ли и сколько занимает.

        Проверка не про показ, а про диагностику: пустая или протухшая лента означает, что
        разбирать прошлый сеанс будет нечем, и узнать об этом лучше заранее, а не тогда,
        когда что-то уже сломалось. Сама по себе лента показу не нужна - поэтому «внимание».
        """
        if not found:
            return HealthVerdict.warn(f"следа нет в {directory} - `cast log` покажет пустоту")
        size = f"{total / 1e6:.1f} МБ"
        days = age / 86400
        if days > retain_days:
            return HealthVerdict.warn(
                f"след есть ({size}), но последняя запись {days:.0f} дн назад"
            )
        return HealthVerdict.ok(f"след {size}, последняя запись {ServeHealth.ago(age)} назад")
