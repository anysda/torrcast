"""Отложенный добор тратится там, где иначе идёт «русской дорожки не нашлось»."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.release import Release
from torrcast.usecases.reinforce.plan_for import plan_for

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.config import Config
    from torrcast.ports.progress.progress import Progress
    from torrcast.usecases.select.plan import Plan


def _fresh(picture: Picture) -> list[Release]:
    """Отложенное, чего в пуле картины ещё нет, - и в первую очередь обещающее русский.

    🔴 Отбор проверяет паспорта не всей очереди, а её головы: бюджет попыток и часы
    ему дороже полноты (:meth:`Bench.resolve`). На замере (стенд .66, замороженный пул,
    «эксперименты лейн») карман отдал 81 раздачу, отбор успел проверить ДВЕ, и обе
    оказались японскими - при том что русский по имени обещают 12 из 101. Упор был не в
    пул, а в порядок: круг звали за русской дорожкой, а голову очереди ему собирали по
    общему качеству.

    Поэтому спрашиваются сперва те, чьё имя русский обещает
    (:attr:`~torrcast.domain.release.Release.dubbed`) - той же меркой, какой уже мерит
    пул :func:`~torrcast.usecases.reinforce.voiceless_pool.voiceless_pool`, то есть до
    всякого ffprobe и без похода в рой. Обещание имени - не приговор, приговор выносят
    дорожки; но выбирать, КОГО спросить первым, честнее по нему, чем по разрешению.
    Не обещает никто - идёт всё отложенное, как есть.
    """
    mine = {r.raw_name for r in picture.releases}
    fresh = [r for r in picture.aside if r.raw_name not in mine]
    return [r for r in fresh if r.dubbed] or fresh


def late_voice(
    plan: Plan, args: Args, config: Config, progress: Progress, profile: Profile = CAUTIOUS
) -> Plan | None:
    """План из раздач, отложенных сторожем добора, - когда русской дорожки не нашлось.

    🔴 TC-770. Все ранние доборы решают, идти ли им, ПО ИМЕНИ раздачи: тощий пул
    (:func:`worth_asking_original`), негодный пул (:func:`unfit_pool`), обещанный в
    неиграбельной раздаче дубляж (:func:`voiceless_pool`). А приговор «русской дорожки
    нет» выносится ПО ДОРОЖКАМ, и выносит его ffprobe уже после меню
    (:func:`voice_unproven`). Между этими мерами лежит дыра: имя обещает русский, паспорт
    его не подтверждает, и ни один ранний повод не срабатывает.

    Спрашивать за неё некого - и не надо. Ранний добор по оригиналу чаще всего УЖЕ сходил
    и уже привёз нужное, а сторож «привёз больше картин» его отверг, защищая МЕНЮ. С этой
    карточки та выдача не выбрасывается, а откладывается
    (:attr:`~torrcast.domain.picture.Picture.aside`) и тратится здесь. Поэтому круг не
    стоит ни секунды сети: платить за него уже заплачено, а меню давно отвечено и
    защищать нечего.

    🔴 Своего захода к индексерам тут нет НАРОЧНО. Он был написан и замерен: на пяти
    картинах класса (стенд .66, живой Prowlarr) поздний круг по оригиналу картины сходил
    к индексерам четырежды, привёз до 81 раздачи и не дал НИ ОДНОЙ картины с русским
    звуком - отбор успевает проверить из привезённого две-три, и упор оказался не в пул,
    а в бюджет попыток. Ход, ничего не дающий человеку, в продукте не живёт.

    В план идут ТОЛЬКО отложенные раздачи: про прежние отбор уже всё узнал, и второй
    ffprobe по ним был бы чистой платой за известный ответ. Из отложенного берутся лишь
    те, что сели в собственный кластер картины (:func:`_fresh`) - новых картин круг не
    открывает вовсе.
    """
    picture = plan.picture
    if not picture.aside:
        return None
    fresh = _fresh(picture)
    if not fresh:
        return None
    late = plan_for(replace(picture, releases=fresh, aside=[]), args, config, profile, plan.runtime)
    if not late.ranked:
        return None
    progress.note(phrase("reinforce.late_voice_note", now=len(late.ranked)))
    return late
