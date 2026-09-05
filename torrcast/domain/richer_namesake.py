"""Правило richer namesake; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.group_weight import _group_weight
from torrcast.domain.picture import Picture
from torrcast.domain.thin_pool import THIN_POOL


def _whole_word(key: str, wanted: str) -> bool:
    """Стоит ли спрошенный слаг в ключе ОТДЕЛЬНЫМ словом, а не куском чужого."""
    return (
        key == wanted
        or key.startswith(f"{wanted}-")
        or key.endswith(f"-{wanted}")
        or f"-{wanted}-" in key
    )


def _richer_namesake(groups: dict[str, list[Picture]], wanted: str) -> str | None:
    """Кому отдать спрошенное имя, когда о самом имени каталог не знает почти ничего.

    🔴 TC-1025, второй заход: замер на широком пуле стенда `.135`. Точное совпадение
    слага уходило ответом МИМО ранжирования, и «властелин» вставал на индийского
    «Sikandar Sadak Ka» (1999): группа со слагом РОВНО «властелин» - одна картина, одна
    раздача. Рядом лежал «властелин-колец» - 12 картин и 169 раздач. На узком пуле `.50`
    (один индексер) этой группы в выдаче нет вовсе, случай не воспроизводится, и первая
    правка его не увидела.

    Условий три, и каждое куплено ОТДЕЛЬНЫМ живым запросом, который без него ломается:

    * о спрошенном имени каталог знает мало - раздач за группой меньше
      :data:`~torrcast.domain.thin_pool.THIN_POOL`. Порог не новый: это та самая мерка
      тощего пула, которой продукт уже меряет «за картиной пусто». Без условия «шерлок
      s3e2» (3 картины, 27 раздач) уезжал в «Шерлок Холмс»;
    * соперник знает БОЛЬШЕ РАЗНЫХ КАРТИН. Вес тут обманывает: у «Гарри Поттера» корень
      весит 14 раздач, а каждая часть - от 18 до 37, и по весу корень проиграл бы своей
      же части, потеряв остальные семь. Картин под корнем 4, под самой богатой частью 3;
    * и БОЛЬШЕ РАЗДАЧ заодно. Без этого «медведь s2e7» (6 картин, 46 раздач) уезжал в
      «Маша и Медведь» - картин там 9, а раздач всего 21.

    ⚠️ Слово должно стоять ОТДЕЛЬНЫМ (:func:`_whole_word`): «брат 2» уезжал в «Братья»
    (19 раздач) ровно потому, что «брат» лежит внутри «братья» куском, а не словом.

    ⚠️ Граница правила названа числом: спасает оно ровно там, где тёзка каталогом почти
    не подтверждён. Была бы у «Властелина» (1999) не одна раздача, а пятнадцать, - он
    перестал бы быть тощим и снова забрал бы запрос себе.
    """
    mine = groups[wanted]
    if _group_weight(groups, wanted) >= THIN_POOL:
        return None
    rivals = [
        key
        for key in groups
        if key != wanted
        and _whole_word(key, wanted)
        and len(groups[key]) > len(mine)
        and _group_weight(groups, key) > _group_weight(groups, wanted)
    ]
    if not rivals:
        return None
    return max(rivals, key=lambda key: (len(groups[key]), _group_weight(groups, key), key))


__all__ = ["_richer_namesake"]
