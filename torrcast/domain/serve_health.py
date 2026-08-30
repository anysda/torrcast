"""Что считается здоровым у раздачи, полок и недельного следа.

Зовёт сценарий :mod:`torrcast.usecases.doctor`, диск и часы приносит порт среды.
"""

from torrcast.domain.catalogs.phrase import phrase
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
            return HealthVerdict.bad(phrase("health.hls_no_base", error=error))
        if not https:
            return HealthVerdict.ok(phrase("health.hls_plain", base=base))
        if days is None:
            return HealthVerdict.bad(phrase("health.hls_cert_unreadable", base=base, cert=cert))
        if days < CERT_FLOOR:
            return HealthVerdict.bad(phrase("health.hls_cert_expiring", base=base, days=days))
        return HealthVerdict.ok(phrase("health.hls_cert_ok", base=base, days=days))

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
            phrase(
                "health.shelves",
                shelf=shelf,
                keys=keys[0],
                keys_kept=keys_kept,
                keys_mb=keys[1] / 1e6,
                probe=probe[0],
                probe_kept=probe_kept,
                probe_mb=probe[1] / 1e6,
            )
        )

    @staticmethod
    def ago(seconds: float) -> str:
        """Возраст записи словами: минуты, часы или дни - что уместнее."""
        if seconds < 3600:
            return phrase("health.ago_minutes", count=seconds / 60)
        if seconds < 86400:
            return phrase("health.ago_hours", count=seconds / 3600)
        return phrase("health.ago_days", count=seconds / 86400)

    @staticmethod
    def trace(found: bool, age: float, total: int, directory: str, retain_days: int) -> HealthLine:
        """Недельный след: пишется ли он вообще, свежий ли и сколько занимает.

        Проверка не про показ, а про диагностику: пустая или протухшая лента означает, что
        разбирать прошлый сеанс будет нечем, и узнать об этом лучше заранее, а не тогда,
        когда что-то уже сломалось. Сама по себе лента показу не нужна - поэтому «внимание».
        """
        if not found:
            return HealthVerdict.warn(phrase("health.trace_missing", directory=directory))
        size = phrase("health.trace_size", size=total / 1e6)
        days = age / 86400
        if days > retain_days:
            return HealthVerdict.warn(phrase("health.trace_stale", size=size, days=days))
        return HealthVerdict.ok(phrase("health.trace_ok", size=size, ago=ServeHealth.ago(age)))
