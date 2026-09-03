"""Начало упаковки с нужного места: перемотка, возврат с паузы или старт показа.

Зовёт отсюда решение об упаковке (:meth:`torrcast.usecases.feed_pack.feed.Feed.restart`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.hls_settings import PACK_DIR, SPLIT_SLACK
from torrcast.ports.journal.slot import journal
from torrcast.ports.pack_run.pack_factory import PackShrink

if TYPE_CHECKING:
    from torrcast.usecases.feed_pack.feed_state import _State


def _restart(
    state: _State, slot: int, shrink: PackShrink, entry: tuple[float, float] | None = None
) -> None:
    """Начать упаковку с сегмента ``slot``: перемотка, возврат с паузы или старт показа.

    Границы сегментов от места старта не зависят (:class:`Grid`), поэтому уже
    упакованное не выбрасывается: под именем ``vN`` и до, и после перезапуска лежит
    ровно одно и то же место фильма. Убирать приходится только то, что прошлый прогон
    не успел дописать, — а этого наружу и не попадало.

    ``entry`` — готовая пара «с какого ``-ss`` заходить и где прогон встанет». Называют её
    там, где место захода уже измерено и служит не только упаковке: начало показа с
    закладки выбирает опорный кадр под ЗРИТЕЛЯ (:func:`_begin`) и обязано паковать ровно
    оттуда же. Без довода место захода меряется здесь и по границе слота, как всегда.
    """
    if state.packer is not None:
        # 🔴 TC-905. Довод обязателен: без него снятый нами прогон остаётся с пустым
        # :attr:`PackRun.stopped`, а по этому полю показ и отличает «сняли сами» от
        # «оборвалось» (:func:`torrcast.usecases.feed_pack.feed_survive._survive`).
        # Окно тут не мгновенное: до подмены :attr:`packer` внизу лежит пробный прогон
        # (0.5-1.7 с), и всё это время часы показа видят наш же труп текущим прогоном.
        # На стенде это выходило строкой «упаковка оборвалась (молча, код 255)» - 255
        # есть ответ ffmpeg на наш SIGTERM - и раздувало счёт ``crashes``, на котором
        # стоят решения о живости упаковки.
        state.packer.stop(keep_files=True, reason=phrase("feed.restart_reason", slot=slot))
    # ⚠️ Кодировщик узнаёт о новом месте показа ПЕРВЫМ делом, до пробного прогона
    # (0.5-1.7 с): голову прогона он обязан начать не позже упаковщика, иначе
    # придерживать её копию будет нечего и первый сегмент уйдёт тяжёлым.
    if state.recoder is not None:
        state.recoder.opening(slot)
    # ⚠️ Перекодирующему прогону пробный не нужен и вреден: по ``-ss`` он встаёт точно,
    # докатки не делает (:func:`ffmpeg_pack_command`), и измеренное ``at`` увело бы
    # весь прогон на сегмент назад. Заодно это минус 0.5-1.7 с из пути старта - ровно
    # та цена, которой сплошной перекод отчасти и оплачивает свою голову.
    at = seek = state.grid.start(slot)
    if entry is not None:
        seek, at = entry
        journal().mark("заход упаковки", слот=slot, встали=round(at, 3))
    elif state.encode is None:
        # Место захода считается по карте опорных кадров, а пробный прогон остаётся
        # запасным путём и сверкой: он идёт один раз на файл (:func:`pack_start`).
        # Дороже всего это на перемотке - там прогон был на пути к картинке каждый раз.
        #
        # 🔴 Заход, вставший ПОЗЖЕ границы, не производит плёнку между границей и собой
        # вовсе, и приёмник упирается в дыру. Поэтому спрашивается не «где встанем», а
        # «с какого места зайти, чтобы не проскочить границу»
        # (:func:`torrcast.adapters.stream_pack.settle_start.settle_start`).
        seek, at = _state.settle_start(state.source, state.grid.start(slot))
        journal().mark("заход упаковки", слот=slot, встали=round(at, 3))
    command = _state.ffmpeg_pack_command(
        state.source,
        state.audio,
        str(state.out / PACK_DIR),
        state.grid,
        slot,
        at,
        state.readrate,
        state.burst,
        encode=state.encode,
        seek=seek,
        voice=state.voice,
        container=state.container,
        video_tag="hvc1" if state.video_codec.startswith("hvc1") else "",
    )
    state.restarted = _state.clock_port.monotonic()
    state.packer = _state.Packer.start(
        command,
        state.out,
        state.out / PACK_DIR,
        slot,
        spare=None if state.recoder is None else state.recoder.spare,
        told=None if state.recoder is None else state.recoder.note,
        hold=None if state.recoder is None else state.recoder.holding,
        shrink=shrink,
        at=at,
        rate=state.readrate,
        burst=state.burst,
        grid=state.grid,
        cap=state.cap,
        container=state.container,
    )
    drop = state.grid.start(slot) - at
    said = phrase("feed.pack_from", start=f"{state.grid.start(slot):.1f}")
    if drop > SPLIT_SLACK:
        said += phrase("feed.catchup", drop=f"{drop:.1f}")
    state._say(said)


def _begin(state: _State, want: float, shrink: PackShrink) -> float:
    """Начать показ с закладки ``want``; вернуть место, с которого приёмнику давать LOAD.

    🔴 TC-1002. Закладка стоит там, где зритель бросил смотреть, а картинка начинается
    только с опорного кадра. Совпадают они редко: у релиза с отвергнутым индексом сетка
    ровная, кадры на ней лежат как попало, и на «Матрице» входа не позже закладки нет у
    **67% плёнки** (замер по прогретой копии: 659 кусков, 281 без единого опорного кадра).
    Приёмник, которому назвали место без входа, буферит до следующего кадра — а до него
    бывает две минуты (замер на источнике: 2455.796 и следом 2580.317). Живой замер тем же
    двоичным файлом, разница только в закладке: 2488.137 — «ни одной картинки показано не
    было» за 200.9 с, 2455.796 (ровно кадр) — «старт 21 с».

    Поэтому показ спрашивает не «где граница слота», а «где ближайший вход не позже
    закладки» (:func:`torrcast.adapters.stream_pack.settle_start.settle_start`) и пакует
    ровно оттуда: первый выложенный кусок НАЧИНАЕТСЯ опорным кадром, как у показа с нуля.

    Назад зритель уезжает только тогда, когда входа в его собственном слоте не нашлось:
    вход из того же слота приёмник берёт сам, доиграв до закладки, и трогать её незачем.
    Уехать вперёд ``want`` может лишь там, где отвод сдался (провал шире 80 с): пропустить
    кусок плёнки хуже, чем ничего, но лучше, чем чёрный экран весь бюджет старта.

    ⚠️ Вход берётся тот, что нашёл отвод, а не ближайший к закладке: шаг удвоения
    (:data:`torrcast.adapters.stream_pack.settle_start.SEEK_BACK_TRIES`) перешагивает
    промежуточные опорные кадры, и зритель пересматривает до 80 с уже виденного:
    досматривать дешевле, чем платить пробным прогоном за каждую секунду точности.
    Первый выложенный кусок при этом короче своего места в манифесте на длину от границы
    слота до входа: приёмнику это ничем не грозит - его туда и посылают, - а отъезд назад
    в эти же секунды в первые две минуты показа отдаст кусок с поздним началом.

    🔴 Живой замер на приставке (стенд .136, «Матрица» 1080p, ровная сетка, закладка
    2489.548 - опорные кадры вокруг стоят на 2403.294, 2418.140, 2440.284 и 2580.317).
    Сборка master: 277 с без единой картинки, приговор списан на источник («0.20 Мбит/с
    против нужных 17.81»), тогда как сам же след все эти минуты писал ``supply ratio``
    2.99-3.61. Эта сборка на той же закладке: вход 2403.294, картинка на 22 с. Шесть
    продолжений подряд, каждое с чистой остановки: 22, 21, 18, 22, 23, 17 с; контроль
    ``--new`` тем же файлом - 13 и 13 с.

    Сплошной перекод сюда не заходит: он ставит опорные кадры САМ и ровно на границы
    сетки, то есть вход есть у каждого слота по построению.
    """
    if want <= 0.0 or state.encode is not None:
        _restart(state, state.grid.slot_at(want), shrink)
        return want
    seek, at = _state.settle_start(state.source, want)
    slot = state.grid.slot_at(at)
    start = want if at <= want and slot == state.grid.slot_at(want) else at
    journal().mark("вход показа", закладка=round(want, 3), вход=round(at, 3), с=round(start, 3))
    _restart(state, slot, shrink, entry=(seek, at))
    return start
