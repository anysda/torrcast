"""Что считается здоровым у самой машины: терминал, локаль и ffmpeg.

Зовёт сценарий :mod:`torrcast.usecases.doctor`, факты приносит порт среды.
"""

from torrcast.domain.catalogs.phrase import phrase
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
            return HealthVerdict.warn(phrase("health.no_terminal"))
        if utf8 is None:
            return HealthVerdict.warn(phrase("health.terminal_mode_unknown"))
        how = phrase("health.iutf8_on") if utf8 else phrase("health.iutf8_off")
        return HealthVerdict.ok(phrase("health.terminal_ok", how=how))

    @staticmethod
    def locale(encoding: str, env: str) -> HealthLine:
        """Кодировка: русские названия и ключи состояния должны переживать запись в файл."""
        if "utf" in encoding or "utf" in env.lower():
            return HealthVerdict.ok(
                phrase(
                    "health.locale_ok",
                    encoding=encoding or "utf-8",
                    env=("(" + env + ")") if env else "",
                ).strip()
            )
        return HealthVerdict.bad(
            phrase(
                "health.locale_bad",
                encoding=encoding or "?",
                env=env or phrase("health.locale_empty"),
            )
        )

    @staticmethod
    def ffmpeg(help_text: str | None, version: str | None) -> HealthLine:
        """ffmpeg и поддержка ``-readrate_initial_burst`` (нужен ffmpeg ≥ 6.1).

        ``help_text`` - ``None``, когда программа не запускается вовсе: паковать поток
        нечем, и это самое «плохо» из трёх. ``version`` - первая строка ``-version``
        или ``None``, если она не сказала ничего.
        """
        if help_text is None:
            return HealthVerdict.bad(phrase("health.no_ffmpeg"))
        head = version[:60] if version is not None else "ffmpeg"
        if "readrate_initial_burst" not in help_text:
            return HealthVerdict.bad(phrase("health.ffmpeg_no_burst", head=head))
        return HealthVerdict.ok(phrase("health.ffmpeg_ok", head=head))
