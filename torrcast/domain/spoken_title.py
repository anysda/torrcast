"""Имя картины с языковой стороны продукта: под EN - оригинальное, если оно есть."""

from torrcast.domain.catalogs.tongue import EN, tongue


def spoken_title(title: str, original: str) -> str:
    """Как назвать картину человеку: записанное имя, а под английской ручкой - оригинальное.

    Правило одно на все места, где картину зовут человеку, и спрашивают его отсюда все
    трое: пункт меню ``cast`` (:func:`torrcast.usecases.choice._named._title`), запись
    показа (:attr:`torrcast.domain.playback_snapshot.PlaybackSnapshot.spoken`) и находка
    в карточке Home Assistant (:func:`hass.search_results.search_results`) - иначе одна и
    та же картина звучит двумя языками в одной сессии, а то и на одном экране: карточка
    звала её «Назад в будущее», пока меню того же стенда звало Back to the Future.
    Оригинала у картины нет (отечественная) или запись писалась
    прежней версией - остаётся записанное имя как есть: выдуманного имени (транслита) у
    картины нет, а молчать о том, что играет, нельзя.
    """
    if tongue() == EN and original:
        return original
    return title
