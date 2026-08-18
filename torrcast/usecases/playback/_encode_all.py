"""Чем перекодировать ВЕСЬ файл: решение файл-уровневое и принимается один раз.

Зовёт его сборка сетки показа (:func:`_layout`), и только она.
"""

from __future__ import annotations

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.recodes_whole import recodes_whole
from torrcast.ports.recode.encoding import Encoding


def _encode_all(
    config: Config,
    codec: str,
    video_mbit: float = 0.0,
    depth: int = 0,
    profile: Profile = CAUTIOUS,
    frame: int = 0,
    hdr: bool = False,
) -> Encoding | None:
    """Чем перекодировать ВЕСЬ файл или ``None`` — если видео уезжает копией, как всегда.

    Решение файл-уровневое и принимается один раз, по паспорту ffprobe: приёмник либо
    декодирует поток, либо нет (:func:`torrcast.domain.recodes_whole.recodes_whole`), и середины тут
    не бывает. Посегментное решение по весу и битрейту на таком файле давало **смешанный** поток
    H.264 и HEVC — на живом Q70D это 24 с картинки и вечная петля «залип → перезагрузка»: ровно на
    границе первого не перекодированного куска.

    🔴 Вопрос задаётся белым списком: копия достаётся ТОЛЬКО тому, что в нём названо
    (:meth:`torrcast.domain.profile.Profile.verdict`). Пока список был чёрным, VP9 и AV1 уезжали
    в mpegts копией всюду, куда отбор не дотянулся, — на релизе, названном руками
    (``--release N``), и на записи возобновления. Приёмник такой поток не начинает вовсе:
    ``LOAD`` не взят, ``IDLE/ERROR``. Кодек, которого мы не мерили, — честный отказ
    ОТБОРА, но если файл всё же играем, он идёт сплошным перекодом, а не копией.

    ``depth`` - глубина цвета из того же паспорта (:attr:`torrcast.domain.entry.Entry.depth`).
    🔴 Спрашивается она наравне с кодеком, потому что имени кодека не хватает: Hi10P
    зовётся тем же ``h264``, а приёмник его не декодирует (:data:`COPY_DEPTH`). Ноль -
    глубину не спрашивали (запись прежней версии), решаем по одному кодеку.

    ``frame`` - ступень кадра из того же паспорта (:attr:`torrcast.domain.media.Media.frame`).
    🔴 TC-222. Спрашивается она наравне с кодеком и глубиной по той же причине: 2160p
    приёмник не берёт и в посильном кодеке (TC-157), а ужать кадр может только перекод.
    Поэтому кадр выше потолка приёмника - это не отказ, а сплошной перекод со скейлом
    вниз, и потолок едет в :attr:`torrcast.adapters.recode.Encode.ceiling` вместе с самим кадром:
    решение «во что ужимать» принимается здесь, один раз, до первого сегмента.

    ``hdr`` - картинка в HDR (:attr:`torrcast.domain.media.Media.hdr`). Тонемап включается
    только вместе с настройкой (:attr:`torrcast.domain.config.Config.recode_tonemap`), и по
    умолчанию он выключен: замер его цены лежит там же.

    Битрейт — не потолок, а **цель**, и она считается от источника. ``recode_mbit``
    остаётся потолком, но брать его всегда нельзя: 🔴 замер на живом Q70D (TC-29,
    «Bocchi the Rock» — 1.3 Мбит/с HEVC) показал, что перекод «в 9 Мбит/с» раздувает
    лёгкое аниме в семь раз, кладёт в сегменты 18.3 и 21.4 МБ при потолке 16 и тратит
    процессор на биты, которых в источнике нет. Отсюда :data:`FULL_GAIN` — во сколько
    раз H.264 тем же ``ultrafast`` (без CABAC и почти без анализа) дороже HEVC при
    сравнимой картинке, — и :data:`FULL_FLOOR`, ниже которого 1080p разваливается.

    Второй повод для сплошного перекода — не кодек, а вес: выше
    :attr:`torrcast.domain.config.Config.bitrate_hard_mbit` тяжёл КАЖДЫЙ кусок, и посегментный
    кодировщик выродился бы в сотню коротких ffmpeg вместо одного длинного. Живой класс,
    ради которого написано, — аниме-BD-ремуксы 1080p на 28–37 Мбит/с; замер на 4 vCPU:
    ``h264`` 37.8 Мбит/с → 9 Мбит/с идёт 3.4× реального времени, синтетический ``hevc``
    29.9 Мбит/с → 2.35×. Потолок отбора для них — ``bitrate_recode_mbit``.
    """
    if not config.recode:
        return None
    heavy = video_mbit > config.bitrate_hard_mbit
    if not recodes_whole(codec or "", depth, profile, frame) and not heavy:
        return None
    return _state.whole_encode(
        config.recode_mbit,
        video_mbit=video_mbit,
        frame=frame,
        ceiling=profile.recode_frame,
        hdr=hdr and config.recode_tonemap,
    )
