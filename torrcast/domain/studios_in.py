"""Находит все знакомые студии, названные в тексте."""

import re
from typing import Final

from torrcast.domain.studio import STUDIOS, Studio

#: Всё, что не буква и не цифра, - разделитель слов: «[TVShows][MVO]», «AVO-Сербин»,
#: «Dub (The Kitchen Russia) + MVO (Good People)» подписаны студиями, а разделены
#: по-разному.
_WORDS_RE: Final = re.compile("[^0-9a-zа-яё]+", re.IGNORECASE)


def studios_in(text: str | None) -> tuple[Studio, ...]:
    """Знакомые студии из текста (:data:`STUDIOS`), в порядке появления; пусто - ни одной.

    Порядок тут несёт смысл, а не красоту: сезонная раздача подписывает свои дорожки
    именно им - «Dub (The Kitchen Russia) + MVO (Good People)» перечисляет студии в том
    же порядке, в каком дорожки лежат в файле, и другого способа узнать, ЧЬЯ дорожка
    играет, у раздачи с голым тегом ``rus`` нет вовсе.

    Сравниваем по словам, а не подстрокой: иначе «Ancord» нашёлся бы в любом слове,
    которое его содержит. Одно и то же место, названное двумя ключами («HDRezka» и
    «HDRezka Studio»), даёт одну студию: побеждает более подробный ключ.
    """
    words = f" {_WORDS_RE.sub(' ', (text or '').casefold()).strip()} "
    hit = [(at, key) for key in STUDIOS if (at := words.find(f" {key} ")) >= 0]
    found: list[Studio] = []
    for _, key in sorted(hit, key=lambda item: (item[0], -len(item[1]))):
        if STUDIOS[key] not in found:
            found.append(STUDIOS[key])
    return tuple(found)
