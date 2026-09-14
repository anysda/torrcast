"""Правило richer namesake; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.facts.proof_in_map import KnownPictures, _renown
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


def _more_renowned(
    groups: dict[str, list[Picture]], held: str, rivals: list[str], known: KnownPictures
) -> list[str]:
    """Соперники, которых карта знает лучше самой картины; карта о ней молчит - все прежние."""
    mine = _renown(groups[held], known)
    if not mine:
        return rivals
    return [key for key in rivals if _renown(groups[key], known) > mine]


def _richer_namesake(
    groups: dict[str, list[Picture]],
    wanted: str,
    incumbent: str | None = None,
    imdb: KnownPictures | None = None,
) -> str | None:
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

    ``incumbent`` - тот, кто держит запрос сейчас, когда это НЕ одноимённая группа:
    третье имя картины (её псевдоним из выдачи IMDb) уводит запрос той же короткой
    дорогой мимо ранжирования. Живой замер стенда: «стражи» вставали на французских
    «Часовых» (2023, 7 раздач) - у той картины «стражи» записаны псевдонимом, - а рядом
    лежали «стражи-галактики»: 5 картин и 157 раздач.

    ⚠️ Граница правила названа числом: спасает оно ровно там, где тёзка каталогом почти
    не подтверждён. Была бы у «Властелина» (1999) не одна раздача, а пятнадцать, - он
    перестал бы быть тощим и снова забрал бы запрос себе.

    🔴 Выдача мерит известность ЧИСЛОМ РАЗДАЧ, а оно у короткого имени врёт: «Мы» (Us,
    2019) лежало одной картиной на две раздачи, а рядом «Чем мы заняты в тени» - два сезона
    на четыре, и запрос уходил соседу по слову. ``imdb`` - офлайн-карта IMDb
    (:func:`~torrcast.domain.facts.proof_in_map.proof_in_map`): когда она доказывает саму
    картину точным именем, типом и годом, счёт раздач больше не решает, и соперник берёт имя
    лишь при большем числе голосов (так ранжирует и TMDb ``search/movie``: имя, год,
    популярность). «Властелина» (1999) карта не знает вовсе, и он уступает «Властелину колец»
    по-прежнему. Молчит карта о самой картине - правило остаётся прежним, счётом выдачи.
    Третье имя (``incumbent``) картину запроса не называет, и карта его не доказывает.
    """
    held = incumbent or wanted
    mine = groups[held]
    if _group_weight(groups, held) >= THIN_POOL:
        return None
    rivals = [
        key
        for key in groups
        if key != held
        and _whole_word(key, wanted)
        and len(groups[key]) > len(mine)
        and _group_weight(groups, key) > _group_weight(groups, held)
    ]
    if rivals and incumbent is None and imdb is not None:
        rivals = _more_renowned(groups, held, rivals, imdb)
    if not rivals:
        return None
    return max(rivals, key=lambda key: (len(groups[key]), _group_weight(groups, key), key))


__all__ = ["_richer_namesake"]
