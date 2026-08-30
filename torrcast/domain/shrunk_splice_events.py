"""Имена событий склейки ужатого места, общие для рассказчика и выжимки.

🔴 Это КЛЮЧИ ЗАПИСИ, а не надписи, и в каталог языка они не уходят. Имя события
ложится в jsonl на диск (:func:`torrcast.ports.journal.journal.mark`) и оттуда же
читается обратно разбором сеанса (:mod:`torrcast.domain.digest._session_block`
сверяет их, в том числе по началу строки). Переведи их - и лента, написанная вчера,
перестанет сходиться с разбором сегодня, а две установки заведут два несовместимых
журнала на один и тот же продукт. Человеку имя события показывает уже каталог, рамкой
``digest.phase``.
"""

from typing import Final

SHRUNK: Final = "ужатие на месте"
SHRUNK_SPLICE_ATTEMPT: Final = "попытка склейки ужатого"
SHRUNK_SPLICE_WON: Final = "склейка ужатого вышла"
SHRUNK_SPLICE_FAILED: Final = "склейка ужатого не вышла"
SHRUNK_SPLICE_NOT_TRIED: Final = "склейка ужатого не пробовалась:"
SHRUNK_SPLICE_KEYLESS: Final = f"{SHRUNK_SPLICE_NOT_TRIED} нет опорного кадра"
SHRUNK_SPLICE_SHRINK_FAILED: Final = f"{SHRUNK_SPLICE_NOT_TRIED} ужать не вышло"
SHRUNK_SPLICE_NOT_ON_TAPE: Final = "склейку ужатого не поставить на ленту показа"
SHRUNK_SPLICE_ASTRAY: Final = "склейка ужатого не с этого места:"
