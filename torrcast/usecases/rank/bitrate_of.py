"""Оценка битрейта раздачи по её размеру; зовут ворота отбора и признак старья."""

from __future__ import annotations

from torrcast.domain.bitrate_mbit import bitrate_mbit
from torrcast.domain.release import Release


def bitrate_of(release: Release, duration: float) -> float | None:
    """Оценка битрейта по размеру раздачи. У одиночного фильма берётся вся раздача,
    у сборника - один фильм, у сериала - ОДНА СЕРИЯ: «9.7 ГБ» на восемь серий это
    3 Мбит/с, а не 30, и по оценке целиком самые обсиженные раздачи сезона улетали бы
    вниз с пометкой «тяжёлый».

    Сколько внутри серий, говорит имя раздачи (:attr:`Release.episode_count`):
    ``[S01E01-08 of 220]`` — восемь, ``[E220 of 220]`` — двести двадцать. Имя молчит —
    отдаём ``None``, и это 🔴 TC-344: «не знаю» и «мало» — разные ответы. Ноль здесь
    раньше значил «ниже любого порога», и ворота читали молчание имени как «лёгкий и
    безопасный»: весовая половина :func:`is_extra` у таких сериалов срабатывала всегда,
    а потолок :func:`over_ceiling` - никогда. Делить на выдуманный счёт значит врать
    себе, а настоящий битрейт серии всё равно померит ffprobe по её файлу - поэтому
    каждый, кто зовёт эту прикидку, обязан решить свой ``None`` сам: в отказ молчание
    не превращается нигде.
    """
    if release.kind != "tv":
        count = release.collection_count
        return bitrate_mbit(release.size // count, duration) if count else None
    count = release.episode_count
    return bitrate_mbit(release.size // count, duration) if count else None
