"""Кого из приехавших после добора сверять с той картиной, за которой шли."""

from __future__ import annotations

from torrcast.domain.facts.origin import Origin
from torrcast.domain.picture import Picture
from torrcast.usecases.reinforce._leading import _leading


def _twin(pictures: list[Picture], about: Origin, before: Picture | None) -> Picture | None:
    """Кого из приехавших после добора сверять с той картиной, за которой шли.

    Не самого многолюдного: добор по русскому имени приносит ФРАНШИЗУ целиком, и вожаком
    в ней становится самая раздаваемая часть. На «cars» это «Тачки 3» (14 раздач против
    четырёх у «Тачек» 2006 года), гейт читал 2017 против 2006 как подмену и выбрасывал
    ровно ту выдачу, за которой ходил: человек оставался с одной мёртвой англоязычной
    раздачей при живых русских.

    Поэтому сверяется картина ТОГО ЖЕ ГОДА - года справки, а её нет, так года той картины,
    за которой шли. Нет среди приехавших картины нужного года - сверять идёт вожак.

    🔴 Зовётся это только на ДОКАЗАННОМ имени добора (справка), и в этом вся его
    безопасность: справка отвечает про ту самую картину, поэтому вопрос к добору один -
    доехала ли она. Имя, подобранное из выдачи, не доказывает ничего: под ним приезжает
    однофамилец («Восхождение» - и фильм Шепитько, и китайский ``The Climbers``), и там
    сверяется вожак, то есть тот, кто станет ответом.
    """
    year = about.year if about.year is not None else (before.year if before else None)
    if year is not None:
        near = [p for p in pictures if p.year is not None and abs(p.year - year) <= 1]
        if near:
            return max(near, key=lambda p: len(p.releases))
    return _leading(pictures)
