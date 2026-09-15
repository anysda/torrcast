"""Происхождение картины как доказательство языка безымянной дорожки."""

from __future__ import annotations

from torrcast.domain.facts.domestic_about import domestic_about
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.proven_native import proven_native
from torrcast.domain.picture import Picture
from torrcast.runtime.facts_wiring import FACTS


def native_picture(picture: Picture, query: str, known: Origin | None = None) -> None:
    """Перенести уже полученный паспорт происхождения в картину перед отбором звука.

    Отечественная картина - та, про которую справка ПРОЧИТАЛА статью и чужого имени в ней
    не нашла (:func:`proven_native`). Паспорт спрашивает поиск, но первый успешный круг не
    проходит через добор, где раньше только и ставился :attr:`Picture.native`. Здесь сеть
    не спрашивается: читается тот же уже сохранённый ответ, а если он молчит или ещё не
    успел - поведение остаётся прежним.

    ⚠️ Тип картины (фильм или сериал) у ряда кэша свой, и спрашивается он первым: у
    сериала и фильма разные статьи. Ряд, записанный без типа, читается следом - им
    отвечает режим «оба типа», где тип взять было неоткуда.
    """
    about = known
    if about is None:
        series = picture.kind == "tv"
        about = FACTS.cache.read(query, series) or FACTS.cache.read(query, None)
    if about and proven_native(about, picture.title):
        picture.native = True
        return
    # Паспорт промолчал или назвал имя статьи на чужом языке («англ. Interns»): страну
    # производства говорит описание ЭТОЙ картины - ряд ключуется её именем и годом.
    wanted = (picture.title, picture.year)
    blurb = FACTS.cache.blurbs([wanted]).get(wanted)
    if blurb and domestic_about(blurb.about):
        picture.native = True
