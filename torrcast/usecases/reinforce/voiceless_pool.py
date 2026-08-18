"""Картина, у которой русская дорожка обещана только в неиграбельных раздачах."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.menu_order import menu_order
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.usecases.choice import first_alive, fitness
from torrcast.usecases.reinforce._plan_for import _plan_for

if TYPE_CHECKING:
    from torrcast.domain.config import Config
    from torrcast.ports.choice_types import Args


def voiceless_pool(
    found: list[Picture], args: Args, config: Config, profile: Profile = CAUTIOUS
) -> Picture | None:
    """Картина, у которой русская дорожка обещана только в неиграбельных раздачах.

    🔴 Русская дорожка - часть «включилось», а не предпочтение (TC-178): релиз без неё
    показу не годится, и очередь на нём не кончается, а идёт дальше. Значит картина,
    у которой дубляж лежит ровно там, куда отбор не ходит, - это не «выбор победнее»,
    а вечер, которого не будет, и повод переспросить он ровно такой же, как негодный пул
    (:func:`unfit_pool`). Живые случаи - обе «Тачки»: у первой части русские раздачи
    оказались образами DVD, у второй дубляж обещан 38-гигабайтным 4К-ремуксом и
    56-гигабайтным двухдисковым изданием, и то и другое отбор не берёт по делу.

    Условия ДВА, и второе не менее важно первого:

    * ни одна играбельная раздача русского не обещает. «Играбельная» - то же самое слово,
      что и в :func:`fitness`: годна воротами, жива и не старьё;
    * а НЕИГРАБЕЛЬНАЯ - обещает. Без этого условия круг платили бы за любую выдачу,
      чьи имена о звуке просто МОЛЧАТ, - а молчание вполне может скрывать дубляж, его
      рассудит ffprobe (:func:`sound_step` о том же). Здесь же каталог сказал прямо:
      русская дорожка у картины есть, и лежит она не там, где мы ищем.

    Спрашивается по имени раздачи (:attr:`~torrcast.parse.Release.dubbed`), то есть до
    всякого ffprobe и без единого похода в рой.

    Картина берётся не любая из найденных, а ТА, ЧТО СЫГРАЕТ (:func:`first_alive`): на
    франшизе «тачки» это первая часть, а не самая обсиженная третья, и добирать надо
    именно ей. Без оригинала или года точной строки не собрать - тогда ``None``.

    ⚠️ Сериал сюда не заходит, и это не забывчивость. «Оригинал + год» - приём КАТАЛОГА
    ПОЛНОМЕТРАЖНОГО КИНО: у фильма год стоит в имени каждой раздачи и разводит выдачу, а
    сезон-пак подписан годом первого сезона или вилкой лет, и точной строкой его не
    вытащить - его вытаскивает своя, сезонная (:func:`_season_reinforce`).

    Замер по ста сохранённым выдачам говорит и про цену: круг сработал бы в 13 из 99, а
    без сериалов - в 5 из 99. Это один лишний круг по индексерам там, где иначе показа
    нет, и платится он из остатка цели (:func:`_no_budget`), как и оба соседних добора.
    """
    plans = [
        plan
        for plan in (_plan_for(p, args, config, profile) for p in menu_order(found))
        if plan.ranked
    ]
    if not plans:
        return None
    plan = plans[first_alive(plans) - 1]
    # Картина у плана - обычная доменная :class:`Picture`, и наружу она уходит под
    # своим именем, а не безымянной.
    picture: Picture = plan.picture
    if picture.kind == "tv" or not picture.original or not picture.year:
        return None
    if fitness(plan, dubbed=True) or not any(r.dubbed for r in plan.ranked):
        return None
    return picture
