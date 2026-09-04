"""Что считается здоровым у самой машины: терминал, локаль и ffmpeg.

Зовёт сценарий :mod:`torrcast.usecases.doctor`, факты приносит порт среды.
"""

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.ffmpeg_pace import FfmpegPace
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
    def ffmpeg(pace: FfmpegPace | None, version: str | None) -> HealthLine:
        """ffmpeg меряется ПОВЕДЕНИЕМ, а не номером версии и не текстом справки (TC-1048).

        Номер версии и упоминание ``-readrate_initial_burst`` в ``-h full`` ffmpeg 8.0.1
        печатает исправно, а на деле burst у него инертен, и темп перемотки считается от
        начала файла, а не от места входа - на боевой команде это вешает перемотку
        намертво. ``pace`` - ``None``, когда программа не запускается вовсе или
        синтетический ролик не собрался: паковать поток нечем, и это самое «плохо» из
        трёх. ``version`` - первая строка ``-version`` или ``None``, если она не сказала
        ничего; версия тут только для строки человеку, порог по ней не считается.
        """
        if pace is None:
            return HealthVerdict.bad(phrase("health.no_ffmpeg"))
        head = version[:60] if version is not None else "ffmpeg"
        if not pace.burst_honored:
            return HealthVerdict.bad(phrase("health.ffmpeg_no_burst", head=head))
        if not pace.entry_paced:
            return HealthVerdict.bad(phrase("health.ffmpeg_pace_from_start", head=head))
        return HealthVerdict.ok(phrase("health.ffmpeg_ok", head=head))
