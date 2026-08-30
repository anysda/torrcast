"""Русские надписи кластера отказов TorrServer."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера ``torrserver``."""
    return {
        "torrserver.unexpected_answer_add": "TorrServer вернул неожиданный ответ на добавление",
        "torrserver.no_hash": "TorrServer не отдал hash раздачи",
        "torrserver.unexpected_answer_files": (
            "TorrServer вернул неожиданный ответ на список файлов"
        ),
        "torrserver.unexpected_answer_cache": "TorrServer вернул неожиданный ответ на счётчик кэша",
        "torrserver.swarm_empty": "рой пуст - за {seconds} с ни одного пира",
        "torrserver.metadata_timeout": "раздача не отдала метаданные за {timeout} с - нет пиров",
        "torrserver.unexpected_answer_list": "TorrServer вернул неожиданный ответ на список раздач",
        "torrserver.unresponsive": "TorrServer не отвечает ({base_url}): {reason}",
        "torrserver.not_json": "TorrServer вернул не JSON",
        "torrserver.warmup_timed_out": "TorrServer не принял раздачу за отведённое время",
    }
