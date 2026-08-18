"""Ворота отбора: годится ли раздача в дефолт меню; зовут план картины и порядок."""

from __future__ import annotations

from torrcast.domain.release import Release
from torrcast.usecases.rank.hevc_hope import hevc_hope
from torrcast.usecases.rank.is_disc import is_disc
from torrcast.usecases.rank.is_extra import is_extra
from torrcast.usecases.rank.over_ceiling import over_ceiling


def is_candidate(
    release: Release,
    runtime: float,
    warn_mbit: float,
    loose: bool = False,
    hard_mbit: float = 0.0,
    last: bool = False,
    copy_hevc: bool = False,
) -> bool:
    """Кандидат в дефолт: первый сорт (:attr:`Release.prime`), не образ диска, не
    приложение к картине (:func:`is_extra`) и в пределах потолка декодера. Жирнее потолка —
    в таблице остаётся с пометкой, но Enter его не возьмёт: ресивер на таком битрейте встаёт.

    ``loose`` — ворота открыты (:func:`gate_open`): живых именных кандидатов у картины
    нет, и тогда кандидатом становится ещё и раздача, чьё имя о качестве просто МОЛЧИТ
    (:attr:`Release.quiet`). Судить её будет ffprobe после выбора — механизм отбраковки
    и перехода к следующему уже стоит на пути (:meth:`Bench.resolve`), и стоит он
    ровно тех же секунд, что и на любом другом релизе.

    Имя, сказавшее о себе правду, послаблением ``loose`` не пользуется: названный HEVC,
    MPEG-4 и «480p» остаются снаружи, потому что про них известно, а не неизвестно.
    Образ диска и потолок битрейта тоже не двигаются: там играть нечего и там ресивер
    встаёт, а от открытых ворот это не меняется.

    ``last`` — последняя надежда (:func:`last_hope`): живого кандидата с нужной серией
    нет ВООБЩЕ, и тогда в очередь пускается названный HEVC (:func:`hevc_hope`). Это не
    смягчение ворот, а признание того, что тракт умеет: такой файл играется сплошным
    перекодом (:data:`torrcast.domain.probe_settings.RECODE_CODECS`) ровно как десятибитный H.264.
    Предпочтением это не становится ни на шаг — ворота открываются только когда живого
    обычного кандидата нет, а порядок держит HEVC ниже всех живых (:func:`rank_releases`).

    ``copy_hevc`` - ответ единственного судьи кодека (:meth:`Profile.verdict`): свой
    ресивер объявил HEVC играющим копией через наш HLS. Для него HEVC проходит обычные
    ворота; профиль не снимает ограничения образа диска, качества и битрейта.

    ⚠️ Не-видео (``kind == "other"``: игры, музыка, книги) послабление не пускает
    никогда, и это не перестраховка. Замер на живой выдаче «one piece»: репак игры
    «One Piece: Pirate Warriors 4 … PC | RePack» несёт 97 сидов и о качестве видео
    молчит по той простой причине, что видео там нет, — при открытых воротах он
    перевешивал настоящий сериал с русским дубляжом и вставал дефолтом меню.

    ``hard_mbit`` — потолок для тех, у кого запас сплошного перекода тонок: имя, обещающее
    кадр выше 1080p, судится им, а не поднятым ``warn_mbit``. Причина не в качестве и уже
    не в «4К не успевает» (замер TC-157 это снял: ужатый до 1080p перекод идёт 1.34-1.53×
    реального времени), а в том, сколько остаётся про запас. У 1080p-ремукса запас 3.4×,
    у ужатого 4К - полтора, и рою при этом всё равно надо отдавать вес ИСХОДНИКА.
    Ноль — ступени нет, всё судится одним потолком.
    """
    if (
        is_disc(release)
        or is_extra(release, runtime)
        or over_ceiling(release, runtime, warn_mbit, hard_mbit)
    ):
        return False
    if (
        release.prime
        or (copy_hevc and release.is_hevc)
        or (loose and release.quiet and release.kind != "other")
    ):
        return True
    return hevc_hope(release, last)
