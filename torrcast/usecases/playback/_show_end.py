"""Конец показа: назвать вслух сплошной перекод, погасить хозяйство и найти виноватого.

Зовёт всё это сам показ (:func:`_play`) - каждое в своём месте круга.
"""

from __future__ import annotations

import contextlib
from typing import NoReturn

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.codec_name import codec_name
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import Profile
from torrcast.domain.recode_note import recode_note
from torrcast.domain.recodes_whole import recodes_whole
from torrcast.ports.clock import Clock
from torrcast.ports.journal.slot import journal
from torrcast.ports.receiver import Receiver
from torrcast.ports.recode.encoding import Encoding
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.following import _following
from torrcast.usecases.playback.stream_server import StreamServer
from torrcast.usecases.source_blame import _blamed
from torrcast.usecases.warm.warmer import Warmer
from torrcast.usecases.watch import Watch


def _say_whole(
    whole: Encoding, codec: str, depth: int, video_mbit: float, frame: int, profile: Profile
) -> None:
    """Причина сплошного перекода называется вслух: кодек с глубиной - или вес, с числом."""
    # Причина перекода называется вслух: кодек с глубиной - или вес, и тогда с числом.
    # А вместе с ней и ужатый кадр: 2160p наружу уезжает как 1080p (TC-222).
    name = codec_name(codec, depth)
    print(
        recode_note(
            name,
            0.0 if recodes_whole(codec, depth, profile, frame) else video_mbit,
            frame,
            whole.out_frame,
        ),
        flush=True,
    )
    journal().mark(
        "сплошной перекод",
        кодек=name,
        пресет=whole.preset,
        мбит=round(whole.mbit, 2),
        кадр=whole.out_frame,
        тонемап=whole.hdr,
    )


def _close_show(
    watch: Watch | None,
    warmer: Warmer | None,
    receiver: Receiver,
    feed: Feed,
    server: StreamServer,
) -> None:
    """Погасить хозяйство показа при любом исходе, включая SIGTERM."""
    # Позиция фиксируется при любом исходе, включая SIGTERM, и делается это ПЕРВЫМ
    # делом: показ, доигранный до конца файла, отмечает «досмотрено» ровно здесь, а
    # приёмнику ниже нужно уже готовое состояние - по нему он и узнаёт, конец это
    # показа или стык серий.
    if watch is not None:
        watch.close()
        journal().emit(
            "session",
            "session_end",
            pos=round(watch.entry.pos, 1),
            dur=round(watch.entry.dur, 1),
            watched=bool(watch.done),
        )
    if warmer is not None:
        warmer.stop()
        # Досмотрено - прогретое стирается: держать на диске фильм,
        # который уже посмотрели, незачем. Прерванный показ прогретое сохраняет:
        # `cast` завтра продолжит с диска и без сети.
        if watch is not None and watch.done:
            warmer.vault.clear()
            print(phrase("playback.watched_cleared_warm"), flush=True)
    # ⚠️ suppress(Exception), а не TorrcastError: pychromecast на полуживом соединении
    # роняет что угодно, а ffmpeg и раздача обязаны погаснуть в любом случае - иначе
    # процесс уходит, а они остаются.
    with contextlib.suppress(Exception):
        # Показ кончился - приложение приёмника закрываем, чтобы ТВ вернулся в
        # исходное состояние: иконка Default Media Receiver иначе висит до своего
        # таймаута простоя и оттягивает автовыключение.
        # Исключение ровно одно - стык серий: следующая серия грузится в то же
        # приложение, и гасить его между ними значит моргать экраном на каждой.
        receiver.stop(quit_app=not _handover(watch))
    feed.stop()
    server.stop()


def _report_end(
    receiver: Receiver,
    session_tag: str,
    watch: Watch | None,
    supply: StreamSource | None,
    expected_end: bool,
) -> int:
    """Последняя правда показа: цифры приёмки, чёрный экран и виноватый в обрыве."""
    report = getattr(receiver, "report", None)
    if report is not None:
        print(f"{session_tag} {report.line()}")
    # 🔴 Показ, не давший НИ ОДНОГО кадра, обязан назвать себя вслух - и раньше всего
    # прочего. Лестница воскрешения к этой строке уже отработала своё
    # (:meth:`_Revival.resurrect`), и раз кадра всё равно нет, молчаливый выход юнита -
    # это чёрный экран без единого слова. На стыке серий он же и самый дорогой: консоли
    # там нет вовсе, а сеанс до сих пор кончался кодом 0 и пустотой в журнале.
    # ⚠️ Живой приёмник цифр приёмки не считает (``report`` есть только у сухого), так
    # что до этой правды путь показа на живом ТВ не доходил вообще ничем.
    if watch is not None and not watch.entry.moved and not watch.done:
        _blame_the_end(supply, shown=False)
    if report is None:
        return EXIT_OK
    # Досмотренный показ виноватого не ищет: хвост упаковки декодеру отдали, а недобор
    # сегментов на самом конце - это конец файла, а не авария.
    if not report.ok and not expected_end and not (watch is not None and watch.done):
        _blame_the_end(supply)
    return EXIT_OK


def _handover(watch: Watch | None) -> bool:
    """Правда ли показ передают следующей серии, а не заканчивают.

    Порог перехода уже записал в состояние следующую серию (:meth:`Watch.close`), поэтому
    ответ лежит там же, где его читает :func:`_cmd_worker`, — двух разных мнений о конце
    показа быть не должно.

    Закрытый с пульта показ (:attr:`Watch.closed_by_remote`) сюда не считается, хоть
    закладка и сдвинута: цикл юнита (TC-880) следующую серию в этот же процесс не
    грузит, и держать приложение приёмника открытым ради несостоявшегося стыка незачем.
    """
    return (
        watch is not None
        and watch.done
        and not watch.closed_by_remote
        and _following(watch.key) is not None
    )


def _blame_the_end(
    supply: StreamSource | None, shown: bool = True, clock: Clock | None = None
) -> NoReturn:
    """Показ кончился недосмотренным - назвать виноватого, и назвать верно. Всегда бросает.

    🔴 Последняя строка показа - последняя возможность сказать правду. Раньше показ
    кончался обвинением «приёмник не досмотрел поток» при живом приёмнике и мёртвой
    службе раздач. Замерено на стенде: перезапуск службы под показом давал ровно эту
    строку, и про источник в ней не было ни слова.

    ``shown`` - видел ли зритель хоть один кадр. Разница не косметическая: «не досмотрел»
    и «не увидел вовсе» - это две разные аварии для того, кто сидит перед экраном, и
    вторая стоит выше на лестнице цели. Сюда она доходит только исчерпав лестницу
    воскрешения: показ, не давший кадра, сперва поднимают, и лишь потом хоронят.

    Спросить источник тут можно спокойно: показ уже кончился, горячего пути нет, а
    человеку и следу уходит одна и та же причина.

    🔴 Здоровая подача - это отдельная правда, а не молчание. Показ, которому рой весь
    сеанс вёз втрое сверх нужного, обвинял в темноте раздачу по последнему замеру, снятому
    уже после сдачи (TC-1009); назвать вместо неё приёмник было бы той же подменой с
    другим именем. Поэтому такой конец говорит о себе прямо: подача была, картинки не
    было, и виноватого мы не знаем.
    """
    why_source = _blamed(supply, clock if clock is not None else _state.CLOCK)
    if why_source:
        journal().offline(why=why_source, asked=True)
        if not shown:
            raise InfraError(phrase("playback.no_picture_source_unreadable", why=why_source))
        raise InfraError(phrase("playback.source_unreadable_cut_short", why=why_source))
    if not shown:
        if supply is not None and supply.kept_up:
            raise InfraError(phrase("playback.no_picture_supply_held"))
        raise InfraError(phrase("playback.no_picture_receiver_refused"))
    raise InfraError(phrase("playback.receiver_did_not_finish"))
