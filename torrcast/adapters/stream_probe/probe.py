"""Дорожки и длительность из HTTP-потока, не качая файл.

Зовут его меню озвучек, показ и длительность следующей серии."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from torrcast.adapters.ffprobe.parse_media import parse_media
from torrcast.adapters.stream_probe.media_shelf import (
    _keep_media,
    _media_cache,
    _read_media,
)
from torrcast.adapters.stream_probe.run_ffprobe import _run_ffprobe
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import Media

#: Чем читается поток: боевой запуск ffprobe (:func:`_run_ffprobe`) или подделка стенда.
Runner = Callable[[list[str], float, Callable[[], bool] | None], str]


def probe(
    url: str,
    timeout: float = 90.0,
    alive: Callable[[], bool] | None = None,
    *,
    run: Runner = _run_ffprobe,
) -> Media:
    """Дорожки и длительность из HTTP-потока, не качая файл: ffprobe берёт заголовок mkv
    запросами Range — это и есть цена меню озвучек.

    Паспорт кэшируется на диск (:func:`_media_cache`) по тем же причинам, что и карта
    опорных кадров: содержимое файла задано раздачей и номером файла, а первое чтение
    стоит роя - до 17 с на «Моане 2». Но время тут даже не главное. Следующая серия
    узнаёт свою длительность именно отсюда (:func:`torrcast.usecases.episode_duration._duration`), а
    узнать её она обязана и тогда, когда сети уже нет: без длительности нет ни порога перехода, ни
    сетки, ни манифеста - то есть нет и автоперехода на прогретую серию посреди обрыва.

    ``alive`` — жив ли смысл дочитывать. Раздача с мёртвым роем метаданные отдаёт (они
    уже в TorrServer), а содержимого не отдаёт вовсе: ffprobe на ней молча сидит весь
    ``timeout``. Признак жизни (:func:`swarm_pulse`) отличает такую от честно долгого
    заголовка и даёт оборвать ожидание рано, не жгя весь бюджет на молчащем релизе.

    ``run`` - чем запускать ffprobe. Боевое умолчание одно (:func:`_run_ffprobe`), и
    меняет его только стенд: настоящий запуск требует и ffprobe, и живой раздачи.
    """
    cache = _media_cache(url)
    if (ready := _read_media(cache)) is not None:
        return ready
    entries = (
        "format=duration:"
        # ``profile`` и ``pix_fmt`` берутся тем же одним запросом и ничего не стоят, а без
        # них показ не отличает Hi10P от обычного H.264 (:func:`recodes_whole`).
        "stream=index,codec_name,codec_type,channels,width,height,bit_rate,profile,pix_fmt,"
        # ``color_transfer`` - оттуда же и даром, а без него HDR не отличить от SDR вовсе.
        # ``field_order`` - единственное место, откуда видна развёртка самого файла:
        # имя раздачи про неё молчит или врёт, а гребёнку на экране даёт поток.
        "color_transfer,field_order:"
        # Теги дорожки берутся ЦЕЛИКОМ, а не списком: mkvmerge пишет вес дорожки то как
        # ``BPS``, то как ``BPS-eng``/``BPS-rus`` - суффикс языковой и заранее неизвестен.
        "stream_tags"
    )
    flags = ["-v", "error", "-show_entries", entries, "-of", "json"]
    command = ["ffprobe", *flags, url]
    try:
        stdout = run(command, timeout, alive)
    except FileNotFoundError as exc:
        raise InfraError(phrase("media_binaries.ffprobe_missing")) from exc
    except subprocess.TimeoutExpired as exc:
        raise InfraError(phrase("media_binaries.ffprobe_timed_out")) from exc
    except subprocess.CalledProcessError as exc:
        raise InfraError(
            phrase("media_binaries.ffprobe_failed", reason=(exc.stderr or "").strip()[:120])
        ) from exc
    media = parse_media(stdout)
    _keep_media(cache, media)
    return media
