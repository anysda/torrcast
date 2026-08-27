"""Разобранный индекс контейнера в карту показа: одна дорожка, одни времена, одни байты.

Зовёт это снятие карты (:func:`~torrcast.adapters.stream_pack.film_keys.film_keys`) - и оба
его исхода, потому что у карты, отвергнутой как призрачная, наружу идёт тот же самый
байтовый указатель.
"""

from __future__ import annotations

from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.frames.keymap.key_map import KeyMap
from torrcast.domain.frames.keymap.video_track import video_track


def _film_keys_of(found: KeyMap) -> FilmKeys:
    """Карта показа из разобранного индекса: точки одной дорожки видео и их смещения.

    ⚠️ Дорожку видео выбираем ОДИН раз. Пока этот вызов стоял внутри списка, он считался
    на каждую точку Cues, а сам он линейный по всем точкам - то есть карта разбиралась
    квадратично. Цена замерена: «Моана 2», 7274 точки - 18.5 с чистого процессора после
    того, как рой всё отдал. Ровно это и принимали за «первое чтение хвоста у холодного
    роя»: рой отдаёт Cues за 2-6 с, остальное было наше.

    Дорожку называет сам файл (элемент ``Tracks`` у mkv); эвристика
    (:func:`~torrcast.domain.frames.keymap.video_track.video_track`) - запасной путь на случай
    головы без ``Tracks``.

    Исковое время лежит в том же порядке, что точки, и фильтруется вместе с ними; пустое -
    равно меткам показа (mkv, mp4 со списком правок).

    🔴 Зовут это ДВА исхода разбора, и в этом весь смысл отдельной единицы: карта принятая
    и карта, отвергнутая как призрачная (:class:`~torrcast.domain.ghost_keys_error.GhostKeysError`),
    отличаются судьбой, а не строением. Отвергнута в ней ровно одна её половина - «здесь
    стоит опорный кадр»; вторая, пара «время - смещение», честная, и по ней считается вес
    куска. Собирайся отвергнутая карта своим кодом - эти две половины разъехались бы
    молча.
    """
    track = found.video if found.video is not None else video_track(found.points)
    video = [point for point in found.points if point.track == track]
    pairs = zip(found.points, found.via, strict=True)
    via = tuple(when for point, when in pairs if point.track == track) if found.via else ()
    return FilmKeys(
        found.duration, [p.at for p in video], [p.offset for p in video], found.kind, via
    )
