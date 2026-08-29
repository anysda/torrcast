"""Фоновый прогрев всего фильма на диск: один показ - один каталог прогретого.

Собирает его показ (:func:`_play`) и сборка прогрева следующей серии.
"""

from __future__ import annotations

from torrcast.domain.config import Config
from torrcast.domain.delivered_mbit import AUDIO_MBIT, TS_OVERHEAD
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.segment_container import MPEGTS, SegmentContainer
from torrcast.ports.journal.slot import journal
from torrcast.ports.recode.encoding import Encoding
from torrcast.ports.recode.spot_rival import SpotRival
from torrcast.usecases.playback.following import Following
from torrcast.usecases.playback.media_grid import MediaGrid
from torrcast.usecases.warm.trim import trim
from torrcast.usecases.warm.vault import Vault
from torrcast.usecases.warm.warm_key import warm_key
from torrcast.usecases.warm.warm_root import warm_root
from torrcast.usecases.warm.warmer import Warmer


def _warmer(
    config: Config,
    source: str,
    audio: int,
    grid: MediaGrid,
    start: float,
    title: str,
    whole: Encoding | None = None,
    recoder: SpotRival | None = None,
    follow: Following | None = None,
    profile: Profile = CAUTIOUS,
    video_mbit: float = 0.0,
    container: SegmentContainer = MPEGTS,
    voice: str = "",
) -> Warmer | None:
    """Фоновый прогрев всего фильма на диск или ``None``, если он выключен.

    🔴 **Прогрев кодирует кусок ровно тем же решением, что и живая упаковка.** Куски
    одного показа приходят приёмнику из двух мест — из окна упаковки и с диска
    (:meth:`torrcast.usecases.feed_pack.feed.Feed.segment`), — и для приёмника это одна лента.
    Разойдись решение о кодировании, и на стыке двух источников меняется SPS: другой профиль, другая
    энтропийная кодировка, другая глубина буфера кадров — то есть декодер обязан
    переинициализироваться посреди фильма. Поэтому решение здесь ОДНО на обоих:

    * кодек, который приёмник не декодирует, — сплошной перекод (``whole``), и у показа,
      и у прогрева;
    * тяжёлые куски — точечный перекод тем же :class:`_state.Encode`, которым их берёт живой
      кодировщик (``recoder``), и ровно на тех же слотах;
    * всё остальное — копия.

    ⚠️ Прежде тут стояло «есть хоть один тяжёлый кусок — греть весь фильм перекодом».
    Замер на лёгком материале («Тачки 3»: 5 тяжёлых кусков из 525): живая упаковка отдавала
    копию релиза, а прогрев клал на диск сплошной ``ultrafast``, и SPS этих двух не
    совпадали ни одним байтом. Стык был не редкостью, а нормой работы — прогрев обгоняет
    показ и отдаёт ему свои куски.
    """
    if not config.warm:
        journal().emit("warm", "disabled")
        return None
    encode = whole
    spots = () if whole is not None or recoder is None else tuple(recoder.targets)
    # Решение точечного перекода спрашивается у самого кодировщика, а не у ``getattr``:
    # слоты непусты только тогда, когда кодировщик есть (:class:`SpotRival`).
    spot_encode = recoder.encode if spots and recoder is not None else None
    # Пресет и битрейт называет то решение, которым кусок и будет взят; решения нет
    # вовсе - и в записи стоят пустая строка и ноль, как стояли.
    decided: Encoding | None = spot_encode or encode
    vault = Vault(
        root=warm_root(config.warm_dir),
        key=warm_key(source, audio, grid, encode, spots, container, voice),
        budget=int(config.warm_budget_gb * 1e9),
        title=title,
        container=container,
    )
    # Каталог, прогретый ПРЕЖНИМ способом выкладки, находится по тому же ключу: способ в
    # ключ не входит (:func:`warm_key`). Помеченные точечные куски убираются здесь, до
    # первого запроса сегмента, - показ читает прогретое раньше всего, и на его пути этой
    # проверке не место.
    trimmed, freed = trim(vault, profile.max_segment_bytes, grid, spots)
    if trimmed:
        journal().mark("прогретое очищено", кусков=trimmed, байт=freed)
    relaid = vault.relay()
    if relaid:
        journal().mark("прогретое перекладывается", кусков=len(relaid), первый=relaid[0])
    journal().plan(
        pack="recode" if encode is not None else "copy",
        warm="recode" if encode is not None else "copy",
        spots=spots,
        preset=decided.preset if decided is not None else "",
        mbit=decided.mbit if decided is not None else 0.0,
    )
    return Warmer(
        source=source,
        audio=audio,
        voice=voice,
        grid=grid,
        vault=vault,
        container=container,
        encode=encode,
        spots=spots,
        spot_encode=spot_encode,
        began_at=grid.slot_at(start),
        # Потолок веса куска - свойство приёмника, и прогреву он нужен ровно затем, чтобы
        # «прогрето NN» называло то, что показ и правда возьмёт с диска
        # (:attr:`torrcast.usecases.warm.warmer.Warmer.warmed`,
        # :meth:`torrcast.usecases.feed_pack.feed.Feed._warm`).
        cap=profile.max_segment_bytes,
        # Второй потолок цели точечного перекода - тот же, которым его считает живой
        # кодировщик (:func:`torrcast.usecases.playback._recoder._recoder`): решение о куске
        # обязано выйти одним и тем же с обеих сторон.
        threshold=config.recode_at_mbit,
        # Сколько уедет на ТВ в среднем по фильму - тем же счётом, что и у живого
        # кодировщика тяжёлых кусков (:func:`torrcast.usecases.playback._recoder._recoder`):
        # видео копией, звук всегда AAC, сверху оверхед mpegts. Прогрев спрашивает по нему
        # место у бюджета там, где карты опорных кадров нет
        # (:func:`torrcast.usecases.warm.forecast._forecast`). Паспорт молчит - ноль, и
        # прогноз возвращается к потолку приёмника, как и был.
        delivered=(video_mbit + AUDIO_MBIT) * TS_OVERHEAD if video_mbit > 0 else 0.0,
        rate=config.warm_rate,
        follow=follow,
        rival=recoder,
        log=lambda text: print(text, flush=True),
    )
