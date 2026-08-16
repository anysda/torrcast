"""Что считается здоровым у самой машины: терминал, локаль и ffmpeg.

Зовёт сценарий :mod:`torrcast.usecases.doctor`, факты приносит порт среды.
"""

from torrcast.domain.health_verdict import HealthLine, HealthVerdict


class HostHealth:
    """Правила первых трёх строк ``cast doctor`` - про машину, а не про сеть."""

    @staticmethod
    def terminal(tty: bool, utf8: bool | None) -> HealthLine:
        """Терминал и режим ``IUTF8``: без него ssh ломает забой на кириллице.

        ``utf8`` - ``None``, когда режим ввода не читается: это не поломка, а
        непроверенное место, поэтому «внимание».
        """
        if not tty:
            return HealthVerdict.warn(
                "терминала нет (запуск не интерактивный) - вопросы возьмут дефолты"
            )
        if utf8 is None:
            return HealthVerdict.warn(
                "терминал есть, но режим ввода не читается - кириллица не проверена"
            )
        how = "уже включён" if utf8 else "выключен, включаем сами на время команды"
        return HealthVerdict.ok(f"терминал: pty есть, IUTF8 {how} - кириллица в вопросах работает")

    @staticmethod
    def locale(encoding: str, env: str) -> HealthLine:
        """Кодировка: русские названия и ключи состояния должны переживать запись в файл."""
        if "utf" in encoding or "utf" in env.lower():
            return HealthVerdict.ok(
                f"локаль: {encoding or 'utf-8'} {('(' + env + ')') if env else ''}".strip()
            )
        return HealthVerdict.bad(
            f"локаль {encoding or '?'} не UTF-8 - русские названия побьются ({env or 'пусто'})"
        )

    @staticmethod
    def ffmpeg(help_text: str | None, version: str | None) -> HealthLine:
        """ffmpeg и поддержка ``-readrate_initial_burst`` (нужен ffmpeg ≥ 6.1).

        ``help_text`` - ``None``, когда программа не запускается вовсе: паковать поток
        нечем, и это самое «плохо» из трёх. ``version`` - первая строка ``-version``
        или ``None``, если она не сказала ничего.
        """
        if help_text is None:
            return HealthVerdict.bad("ffmpeg не запускается - упаковывать поток нечем")
        head = version[:60] if version is not None else "ffmpeg"
        if "readrate_initial_burst" not in help_text:
            return HealthVerdict.bad(f"{head}: нет -readrate_initial_burst - старт будет медленным")
        return HealthVerdict.ok(f"{head}, -readrate_initial_burst есть")
