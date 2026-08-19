"""Зеркало :mod:`torrcast.usecases.select._plan_fields`: из чего состоит план показа."""

from __future__ import annotations

from dataclasses import fields

from torrcast.domain.picture import Picture
from torrcast.usecases.select._plan_fields import _PlanFields
from torrcast.usecases.select.plan import Plan


def test_the_plan_fields_ride_into_the_plan_with_their_working_defaults() -> None:
    """Поля приезжают в план целиком: без них очередь отбора судить нечем."""
    plan = Plan(picture=Picture(title="Кино", year=1999), ranked=[], runtime=0.0, warn_mbit=16.0)

    assert {field.name for field in fields(_PlanFields)} <= {field.name for field in fields(Plan)}
    assert (plan.loose, plan.last_resort, plan.off_season) == (False, False, 0)
