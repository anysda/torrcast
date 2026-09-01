"""Достаёт последнюю внятную строку самого показа из его журнала; зовут отчёты о беде."""

from __future__ import annotations

from torrcast.adapters.launchd._job_files import _log_path
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.unit_naming import _UNIT_NAME
from torrcast.domain.why import why

#: Сколько байт читается с конца журнала: внятная строка - одна из последних, а за
#: долгий показ журнал растёт.
_TAIL: int = 16384


def job_why(unit: str = _UNIT_NAME) -> str:
    """Последняя внятная строка САМОГО ПОКАЗА - наружу без трейсбеков.

    journald на macOS нет: оба потока задания пишутся в файл (``StandardErrorPath`` в
    plist'е), поэтому отбирать свои строки по автору записи, как у systemd, не нужно -
    в файле только показ. Ответ - последняя непустая его строка.
    """
    try:
        with _log_path(unit).open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - _TAIL))
            tail = stream.read().decode("utf-8", errors="replace")
        if size > _TAIL:
            # Срез пришёлся на середину строки: до первого перевода строки в хвосте -
            # обрубок, и доверять ему нельзя (там может быть и полстроки utf-8).
            tail = tail.split("\n", 1)[1] if "\n" in tail else ""
    except FileNotFoundError:
        return phrase("launchd.log_empty")
    except OSError as exc:
        return phrase("launchd.reason_unavailable", reason=why(exc))[:160]
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    return lines[-1][:160] if lines else phrase("launchd.log_empty")
