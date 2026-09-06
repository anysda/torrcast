"""Голый номер части сливается с картиной-подзаголовком, когда линия частей не спорит.

«Матрица 4» и «Матрица: Воскрешение» - одна картина 2021 года, названная на трекерах
то номером, то подзаголовком. Мостика-имени («Матрица 4: Воскрешение») в выдаче может
не быть вовсе, и тогда номер доказывает окружение: голова франшизы и год сошлись,
кандидат один, и свидетели с номерами вокруг не возражают.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain._name_data.data_2 import _PART_NUMBER_RE
from torrcast.domain.part_number import part_number
from torrcast.domain.picture import Picture


def _proven_part(
    pictures: list[Picture],
    identity: Callable[[str], str],
    root: Callable[[int], int],
    union: Callable[[int, int], None],
    alternative: list[bool],
) -> None:
    """Свести голое «Имя N» с картиной той же головы и года, если номер доказан.

    Ограждения, каждое куплено своей парой:

    * кандидат ровно один: голая «Матрица 3» 2003 года выбирала бы из «Перезагрузки»
      и «Революции», а выбирать - гадать;
    * у кандидата есть подзаголовок, либо претендент - первая часть: «Совершенные
      Мстители» и «Совершенные Мстители 2» - две картины ОДНОГО 2006 года, и голое
      имя кандидата говорит лишь «первая», а не «вторая»;
    * номер не занят другой картиной линии: «Пираты 2» 2007 года - не «На краю
      света», второй частью уже стоит «Сундук мертвеца» 2006-го;
    * год не спорит с соседями по номеру: часть N не может быть младше части N+1.

    Подборки и альтернативные версии свидетелями и кандидатами не бывают: «Пенталогия»
    не часть линии, а фанатская версия доказывать чужой номер не вправе. Претендентом
    альтернативная картина быть МОЖЕТ: «Матрица 4» фанатская, а фильм тот же.
    """

    def head_of(title: str) -> str:
        match = _PART_NUMBER_RE.match(title.strip())
        head = (title[: match.start(1)] if match else title).partition(":")[0].strip()
        return identity(head) if head else ""

    for i, picture in enumerate(pictures):
        if picture.kind == "other" or picture.year is None or ":" in picture.title:
            continue
        number = part_number(picture.title)
        head = head_of(picture.title)
        if number is None or not head:
            continue
        candidates = {
            root(j)
            for j, other in enumerate(pictures)
            if root(j) != root(i)
            and other.kind == picture.kind
            and other.year == picture.year
            and not other.collection
            and not alternative[j]
            and (other.part is None or other.part == number)
            and part_number(other.title) in (None, number)
            and head_of(other.title) == head
        }
        if len(candidates) != 1:
            continue
        target = candidates.pop()
        if number > 1 and not any(
            ":" in pictures[k].title for k in range(len(pictures)) if root(k) == target
        ):
            continue
        anchors = [
            other
            for k, other in enumerate(pictures)
            if root(k) not in (root(i), target)
            and other.kind == picture.kind
            and other.part is not None
            and other.year is not None
            and not other.collection
            and not alternative[k]
            and head_of(other.title) == head
        ]
        if any(
            other.part == number
            or ((other.part or 0) < number and (other.year or 0) > picture.year)
            or ((other.part or 0) > number and (other.year or 0) < picture.year)
            for other in anchors
        ):
            continue
        union(i, target)


__all__ = ["_proven_part"]
