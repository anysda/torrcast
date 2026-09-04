"""Сегмент ушёл наружу: уточнить профиль по факту и посчитать опоздания.

Зовёт это выкладка сегмента (:meth:`Packer.publish`) на каждом куске."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Final

from torrcast.adapters.http_server._handler import _tracing
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.domain.catalogs.phrase import phrase
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from torrcast.adapters.recode.recoder_state import _State

#: Ключ каталога для каждого внутреннего ярлыка исхода: ``how`` сам по себе не надпись
#: (сравнивается строкой ниже и в :mod:`torrcast.adapters.stream_pack.packer_publish`,
#: :mod:`torrcast.adapters.stream_pack._own_head`), а слово человеку берётся отсюда -
#: ровно в момент показа, а не там, где ``how`` только сравнивают.
_HOW_PHRASE: Final = {
    "copy": "digest.plan_copy",
    "recode": "digest.plan_recode",
    "splice": "digest.plan_splice",
    "shrink": "digest.plan_shrink",
}


def _note(state: _State, slot: int, how: str) -> None:
    """Сегмент ушёл наружу: уточнить профиль по факту и посчитать опоздания.

    ``how`` — чем именно он ушёл: ``copy``, ``splice`` (картинка перекода со звуком
    копии), ``recode`` (склейка не вышла) или ``shrink`` (место пересобрала сама
    выкладка, и наружу ушла его картинка - со звуком копии, пока склейка выходит).
    Копия — это
    единственный честный замер «сколько на самом деле уезжает на ТВ»: по ней и
    правится поправка :attr:`Weights.extra`, из-за которой байты карты (контейнер
    целиком) не равны байтам сегмента (видео и одна дорожка).

    ⚠️ «Склейка» и «перекод» в журнале обязаны различаться: отказ склейки — это
    вернувшийся разрыв на стыке, и молчать о нём значит разбирать подвисы вслепую.

    🔴 ``how`` - внутренний ярлык, а не слово человеку: его сравнивают строкой этот же
    файл и соседи по выкладке (:mod:`torrcast.adapters.stream_pack.packer_publish`,
    :mod:`torrcast.adapters.stream_pack._own_head`). Переведённое слово достаётся из
    :data:`_HOW_PHRASE` только для поля ``чем=`` и текста показа - перевести сам
    ``how`` значило бы сравнивать «splice» со «склейка» под ``--en`` и молча промахиваться
    каждый раз.
    """
    recoded = how != "copy"
    # Не максимум, а именно последний: перемотка назад начинает упаковку заново, и
    # край обязан уехать назад вместе с ней - иначе кодировщик решит, что всё позади
    # уже выложено, и до конца показа не возьмётся ни за один кусок.
    state.edge = slot
    # Кусок ушёл наружу - выкладку он больше не держит, каким бы ни был исход.
    state._unstick(slot)
    # Сколько ушло на ТВ на самом деле. Это единственный честный замер профиля, и
    # стоит он один `stat`: без него «почему приёмник встал» разбирается по размерам
    # файлов в чужом журнале, а предсказание профиля не с чем сверить.
    span, went = state.grid.span(slot), 0.0
    size = 0
    with contextlib.suppress(OSError):
        size = (state.spare.parent / segment_name(slot, state.container)).stat().st_size
        went = size * 8 / span / 1e6 if span > 0 else 0.0
    shown = phrase(_HOW_PHRASE[how])
    journal().mark(
        "сегмент",
        слот=slot,
        перекод=recoded,
        чем=shown,
        мбит=round(went, 2),
        профиль=round(state.weights.at(slot), 2),
    )
    if _tracing():
        state._say(
            f"выложен v{slot}: {shown} {went:.1f} Мбит/с (профиль {state.weights.at(slot):.1f})"
        )
    # Отказ склейки - это вернувшийся разрыв на голове захода, и молчать о
    # нём нельзя даже без TRACE: он редкий, поэтому дешёвый, и он объясняет подвис.
    if how == "recode":
        state._say(f"склейка v{slot} не вышла - перекод ушёл как есть, стык под вопросом")
    if recoded:
        return
    if size:
        state.weights.calibrate(slot, size, span)
    # Куски позади показа не в счёт: после перемотки прошлый прогон дописывает то,
    # что уже никто не увидит, и считать это опозданием - врать себе в отчёте.
    if slot in set(state.targets) and state.grid.end(slot) >= state.played:
        state.late += 1
        # Тяжёлый кусок, ушедший копией, - это будущий BUFFERING, и разбирать его
        # задним числом по размеру файла в журнале раздачи слишком дорого: пишем
        # сразу, чем в этот момент был занят кодировщик и куда смотрел показ.
        job = state.job
        state._say(
            f"тяжёлый v{slot} ({state.weights.at(slot):.0f} Мбит/с) ушёл копией: "
            f"показ {state.played:.0f} с, край {state.edge}, "
            + (f"заход v{job[0]}...v{job[1]}" if job else "заход не идёт")
        )
