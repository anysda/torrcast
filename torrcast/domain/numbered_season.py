"""Правило numbered season; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture
from torrcast.domain.seasons_named import seasons_named


def _numbered_season(picture: Picture) -> bool:
    """Число при имени картины - номер сезона, а не номер части франшизы.

    Поручительством считается совпадение: раздачи картины назвали ровно один
    сезон, и он равен числу при имени. Чего признак НЕ обещает:

    - кворума: молчащие о сезоне раздачи не считаются вовсе, поэтому одной
      подписанной раздачи достаточно при любом числе молчащих;
    - независимости подписи: число при имени и подпись сезона могут быть
      извлечены из одного и того же имени файла;
    - проверки соседей по линейке: картины без числа при имени этим правилом
      не проверяются.
    """
    return (
        picture.kind == "tv"
        and picture.part is not None
        and (seasons_named(picture) == (picture.part,))
    )


__all__ = ["_numbered_season"]
