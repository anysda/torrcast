"""Круг из сети на месте круга с диска, когда отбор по старому пулу кончился ничем."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from torrcast.domain.magnet_hash import magnet_hash
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.usecases.reinforce.plan_for import plan_for

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.config import Config
    from torrcast.domain.release import Release
    from torrcast.usecases.select.plan import Plan


def _name(release: Release) -> str:
    """Имя раздачи между двумя выдачами: инфохэш, а без него - магнит как есть."""
    return magnet_hash(release.magnet) or release.magnet


def renewed_plan(
    plan: Plan, live: Plan | None, args: Args, config: Config, profile: Profile = CAUTIOUS
) -> Plan | None:
    """План из раздач живого круга, которых в отобранном пуле не было; нечего - ``None``.

    Показ с карточки берёт её круг сразу, и после рестарта это круг с диска (старт
    фильма за 0.1-0.4 с против 1.7-9.0 с ожидания сети). Такой пул бывает старым: у
    «Рик и Морти» s2e1 в выдаче трёхчасовой давности не было единственной играющей
    раздачи, и все девять раздач сезона отпали одна за другой. Живой круг к этой секунде
    обычно уже приехал.

    В план идут ТОЛЬКО новые раздачи: про прежние отбор уже всё узнал, и второй заход
    по ним стоил бы тех же ожиданий роя (как :func:`late_voice`). Круг и так был из
    сети - новых раздач нет, и отказ остаётся отказом.
    """
    if live is None:
        return None
    judged = {_name(release) for release in plan.picture.releases}
    fresh = [release for release in live.picture.releases if _name(release) not in judged]
    if not fresh:
        return None
    picture = replace(live.picture, releases=fresh, aside=[])
    renewed = plan_for(picture, args, config, profile, plan.runtime, plan.studio)
    return renewed if renewed.ranked else None


__all__ = ["renewed_plan"]
