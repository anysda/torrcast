"""Номера картин, способных нести сезон, который назвал сам запрос."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def asked_season(plans: list[Plan], numbers: list[int]) -> list[int]:
    """Номера (с единицы) картин, способных нести сезон, названный запросом.

    🔴 TC-818. Зритель назвал сезон вслух (``s1e1``), а дефолт садился на картину, которую
    сам каталог подписал ДРУГИМ номером части. Замер по сохранённым выдачам: «код гиас
    s1e1» - спрошен первый сезон, а дефолтом вставал «Код Гиас: Восставший Лелуш 2»
    (2008), то есть второй. Первый сезон при этом стоял в том же меню и был жив.

    Номер части у сериала и есть номер сезона - тем же прочтением запрос «имя N»
    переписывается в «имя sNe1» (:func:`~torrcast.usecases.discover.season_reread.season_reread`),
    и второго значения у номера тут нет. Значит картина, подписанная частью 2, первого
    сезона не несёт, и дефолт спрошенного сезона ей не положен.

    Ворота узкие, и оба сужения нужны:

    * серию запрос не называл (:attr:`Plan.asked_series`) - номер сезона не назван,
      и судить картины по нему нечем;
    * подходящих не осталось ни одной - считаем как считали: спрошенного сезона в меню
      нет вовсе, и пустой ответ вместо картины был бы хуже неточного номера.

    Картина без номера части проходит всегда: «Код Гиас: Восставший Лелуш» без цифры -
    это и есть первый сезон, а «Ход королевы» без цифры - весь сериал целиком.
    """
    if not any(plan.asked_series for plan in plans):
        return numbers
    seasons = {plan.want.season for plan in plans if plan.want is not None}
    if len(seasons) != 1:
        return numbers
    season = next(iter(seasons))
    able = [
        n
        for n in numbers
        if plans[n - 1].picture.part is None or plans[n - 1].picture.part == season
    ]
    return able or numbers
