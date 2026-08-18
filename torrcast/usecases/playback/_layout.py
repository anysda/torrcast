"""Сетка сегментов и решение «перекодировать файл целиком» - одной парой.

Считают её двое и обязаны получить одно и то же: показ (:func:`_play`) и прогрев
следующей серии впрок (:func:`_next_warmer`).
"""

from __future__ import annotations

from collections.abc import Callable

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.config import Config
from torrcast.domain.media import AUDIO_MBIT, TS_OVERHEAD
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.ports.recode.encoding import Encoding
from torrcast.usecases.playback._encode_all import _encode_all
from torrcast.usecases.playback.media_grid import MediaGrid


def _layout(
    config: Config,
    source: str,
    length: float,
    codec: str,
    video_mbit: float,
    say: Callable[[str], None] | None = None,
    depth: int = 0,
    profile: Profile = CAUTIOUS,
    frame: int = 0,
    hdr: bool = False,
) -> tuple[MediaGrid, Encoding | None]:
    """Сетка сегментов и решение «перекодировать файл целиком» - одной парой.

    Отдельной функцией потому, что считать это приходится дважды и обязательно
    одинаково: один раз показу (:func:`_play`), другой - прогреву следующей серии впрок
    (:func:`_next_warmer`). Разойдись они хоть в одном знаке после запятой - прогретое
    легло бы под другим ключом (:func:`torrcast.usecases.warm.warm_key`), и показ, ради которого
    всё грелось, своего же прогретого не нашёл бы.

    🔴 Ровно поэтому паспорт сюда приходит целиком - кодек, глубина цвета, кадр и HDR:
    пока глубину знал один прогрев, а показ решал по имени кодека, десятибитный H.264
    уезжал на ТВ копией и вставал намертво (:func:`torrcast.domain.recodes_whole.recodes_whole`).

    Порядок внутри тоже не случаен: сплошной перекод решается ДО сетки, потому что от
    битрейта перекода зависит вес каждого куска, а значит и то, где сетка ставит границы.
    🔴 TC-222. На ужатом 4К это перестаёт быть тонкостью и становится условием показа: под
    сплошным перекодом вес куска задаём МЫ, и считать его по карте исходника нельзя. У
    4К-исходника на 21 Мбит/с карта обещает сегменты вдвое легче наших девяти - сетка
    нарезала бы по 20 с, а наши же 9 Мбит/с положили бы в такой кусок 22 МБ при потолке
    приёмника 16 (:attr:`torrcast.domain.profile.Profile.max_segment_bytes`). Поэтому в сетку
    едет ``fixed_mbit`` - наш битрейт, а не исходника.

    🔴 TC-501. Наш битрейт тут - это ``maxrate``, а не цель: см. комментарий у самого
    ``fixed_mbit``. Считать вес куска по средней цели значит обещать себе тем больше,
    чем труднее материал, - и на сплошном перекоде обещание промахивалось на все восемь
    процентов ``_state.MAXRATE_GAIN``, ровно вверх, ровно на длинных кусках.
    """
    whole = _encode_all(config, codec, video_mbit, depth, profile, frame, hdr)
    grid = _state.grid_for(
        source,
        length,
        config.hls_segment,
        config.hls_keyframes,
        say=say,
        delivered_mbit=(video_mbit + AUDIO_MBIT) * TS_OVERHEAD if video_mbit > 0 else 0.0,
        ceiling_mbit=(
            (config.recode_mbit * _state.MAXRATE_GAIN + AUDIO_MBIT) * TS_OVERHEAD
            if config.recode
            else 0.0
        ),
        # Сплошной перекод: вес куска задаём мы сами, карта источника тут не судья. 🔴 TC-501.
        # Задаём его МГНОВЕННЫМ потолком кодера (:attr:`torrcast.adapters.recode.Encode.maxrate`), а
        # не целью: цель - это средний битрейт по прогону, а в отдельный кусок кодер вправе положить
        # вплоть до потолка (:data:`torrcast.adapters.recode.MAXRATE_GAIN`), и на трудном материале
        # он ровно это и делает. Замер на стенде (1080p10 40 Мбит/с, ultrafast, цель 9): насыщенный
        # кусок уехал на 10.22 Мбит/с при обещанных сеткой 9.47 - промах ровно в
        # ``_state.MAXRATE_GAIN``. Сетка на этом обещании разрешала себе куски до 13.5 с, а такой
        # кусок весит 17 МБ при потолке приёмника 16: он рождался за потолком ещё до всякой
        # выкладки, и ловить его на выходе было уже нечем.
        fixed_mbit=(whole.maxrate + AUDIO_MBIT) * TS_OVERHEAD if whole is not None else 0.0,
        # Потолок веса куска - у каждого приёмника свой (:mod:`torrcast.domain.profile`).
        cap=profile.max_segment_bytes,
    )
    if whole is not None:
        # 🔴 TC-501, вторая половина. Сетка режет ТОЛЬКО по опорным кадрам, и там, где
        # один GOP сам по себе длиннее потолка, резать ей нечем - кусок остаётся длинным
        # («влез - или один GOP тяжелее потолка»,
        # :meth:`torrcast.adapters.stream_pack.grid.Grid.on_keyframes`). Замер на живом Q70D
        # («Эксперименты Лэйн», BDRip hi10p): честной сетки мало, у неё осталось два куска по 15.2
        # с, и наши 9 Мбит/с положили в них 17 и 16 МБ при потолке 16 - показ встал на 1:58 ровно на
        # них.
        #
        # Поэтому цель считается ОТ САМОГО ДЛИННОГО куска, который в сетке всё-таки
        # остался, - тем же и единственным местом, где живёт потолок (:meth:`_state.Encode.fit`),
        # и ровно так же, как её считает заход посегментного кодировщика (TC-483). Прогон
        # сплошного перекода один на весь показ и идёт одним ``-b:v``, так что судит его
        # худший кусок: иначе кусок, который резать нечем, не влезет никогда и ничем.
        # Чёткость тут и торгуется: гейт «ноль подгрузов» стоит выше неё.
        #
        # ⚠️ Хвост в судьи не берётся, и это не поблажка. Последний кусок сетки такой,
        # какой остался (:meth:`torrcast.adapters.stream_pack.grid.Grid.on_keyframes`), потолок веса
        # на него не распространялся никогда, и длина у него не связана ни с картой, ни с нашим
        # битрейтом. Замер: на 4К-карте с GOP 8.5 с хвост вышел 16.5 с и утянул бы цель всего фильма
        # с 9.0 до 6.12 Мбит/с - то есть один кусок в конце кино торговал бы чёткостью всех
        # остальных.
        judges = max(grid.count - 1, 1)
        whole = whole.fit(max(grid.span(k) for k in range(judges)), profile.max_segment_bytes)
    return grid, whole
