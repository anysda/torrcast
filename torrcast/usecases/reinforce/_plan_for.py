"""План по одной картине: пул релизов в порядке отбора и цель для сериала."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

from torrcast.domain._series import _Series
from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.recodes_whole import recodes_whole
from torrcast.usecases.rank.gate_open import gate_open
from torrcast.usecases.rank.last_hope import last_hope
from torrcast.usecases.rank.rank_releases import rank_releases

if TYPE_CHECKING:
    Args: TypeAlias = Any
    Config: TypeAlias = Any
    _Plan: TypeAlias = Any


def _plan_for(
    picture: Picture,
    args: Args,
    config: Config,
    profile: Profile = CAUTIOUS,
    runtime: float = 0.0,
) -> _Plan:
    """План по одной картине: пул релизов в порядке отбора и цель для сериала.

    ``runtime`` — настоящая длительность картины, секунды (из справки, :func:`_timed`).
    Ноль — её не назвал никто, и в знаменатель битрейта идёт прикидка
    (:data:`torrcast.stream.RUNTIME_GUESS`).
    """
    from torrcast.domain.runtime_guess import RUNTIME_GUESS

    # 🔴 Сам план по слоям ещё не разложен: он живёт в сценарии выбора
    # (:class:`torrcast.usecases.select._Plan`), а тот зовёт добор. Пока договор не назван
    # (:mod:`torrcast.ports.choice_types`), имя берётся отложенным импортом - раньше оно
    # приезжало сюда плоским namespace прежнего монолита, то есть вообще ниоткуда.
    from torrcast.usecases.select import _Plan

    series = _Series(want=args.episode or Episode(1, 1)) if picture.kind == "tv" else None
    known = runtime > 0
    runtime = runtime if known else RUNTIME_GUESS.get(picture.kind, 7200.0)
    pool = picture.releases
    if series is not None:
        pool = [r for r in pool if r.covers(series.want.season)]
    # Потолок отбора - уже не потолок декодера. Тяжёлые куски перекодируются
    # (:mod:`torrcast.recode`), поэтому честный тяжёлый 1080p теперь берётся, а отбраковывает
    # только то, что перекодированием не спасти, - ``bitrate_hard_mbit``. Перекодирование
    # выключено - потолком снова становится прежний ``bitrate_warn_mbit``.
    # Выше ``bitrate_hard_mbit`` перекодированием спасается не всё, а только то, что
    # перекодируется ЦЕЛИКОМ одним прогоном (``bitrate_recode_mbit``): аниме-BD-ремуксы
    # на 28-37 Мбит/с - ровно этот случай, и отказывать им незачем.
    ceiling = config.bitrate_hard_mbit if config.recode else config.bitrate_warn_mbit
    hard = ceiling
    if config.recode:
        ceiling = max(ceiling, config.bitrate_recode_mbit)
    want = series.want if series else None
    copy_hevc = profile.plays_copy("hevc", profile.copy_depth)
    loose = gate_open(pool, runtime, ceiling, want, hard_mbit=hard, copy_hevc=copy_hevc)
    # Ворота последней надежды открываются при двух условиях сразу, и оба - не про пул.
    # Первое: перекодирование включено. Играть HEVC умеет ровно сплошной перекод, и без
    # него пускать такой релиз в очередь значило бы обещать показ, которого не будет.
    # Второе: HEVC для ЭТОГО приёмника и правда тяжёлый путь - спрашивается там же, где
    # об этом спрашивают показ и прогрев (:func:`torrcast.stream.recodes_whole`), чтобы
    # отбор не судил по чужим числам. Приёмник, который берёт HEVC копией, в последней
    # надежде не нуждается вовсе: у него это обычный релиз, и место ему в воротах,
    # которым передан ответ профиля, а не здесь.
    heavy_hevc = recodes_whole("hevc", profile.copy_depth, profile)
    last = (
        config.recode
        and heavy_hevc
        and last_hope(pool, runtime, ceiling, want, loose, hard, copy_hevc=copy_hevc)
    )
    ranked = rank_releases(
        pool,
        runtime,
        ceiling,
        want=want,
        loose=loose,
        hard_mbit=hard,
        last=last,
        copy_hevc=copy_hevc,
    )
    return _Plan(
        picture=picture,
        ranked=ranked,
        runtime=runtime,
        runtime_known=known,
        off_season=len(picture.releases) - len(pool),
        warn_mbit=ceiling,
        series=series,
        recode_at=config.recode_at_mbit if config.recode else 0.0,
        loose=loose,
        last_resort=last,
        copy_hevc=copy_hevc,
        hard_mbit=hard,
        asked_series=args.episode is not None,
    )
