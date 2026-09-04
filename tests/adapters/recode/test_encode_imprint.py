"""Зеркало отпечатка правил кодирования: он снимается с БОЕВОЙ формы, а не со списка имён."""

from __future__ import annotations

from collections.abc import Iterable
from inspect import signature

import pytest

import torrcast.adapters.recode.encode as encode_module
from torrcast.adapters.ffmpeg.encode_args import encode_args
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.recode.encode_imprint import encode_imprint
from torrcast.adapters.stream_pack.grid import Grid

DECISION = Encode(preset="veryfast", mbit=9.0)


def _with_level(
    *,
    preset: str,
    mbit: float,
    maxrate: float,
    bufsize: float,
    keyframes: Iterable[float],
    filters: str = "",
    hdr: bool = False,
) -> list[str]:
    """Правила ДО TC-871: те же аргументы плюс уровень, вписанный от себя."""
    return [
        *encode_args(
            preset=preset,
            mbit=mbit,
            maxrate=maxrate,
            bufsize=bufsize,
            keyframes=keyframes,
            filters=filters,
            hdr=hdr,
        ),
        "-level",
        "4.1",
    ]


def test_the_same_rules_and_the_same_decision_give_the_same_imprint() -> None:
    """Отпечаток стабилен: иначе полка обесценивалась бы сама по себе, без всякой правки."""
    assert encode_imprint(DECISION) == encode_imprint(Encode(preset="veryfast", mbit=9.0))
    assert DECISION.imprint == encode_imprint(DECISION), "решение и отпечаток разошлись"


def test_a_flag_added_to_the_live_command_moves_the_imprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Правка боевой команды двигает отпечаток, и ни одно имя для этого не названо.

    Это и есть та самая правка TC-871, только развёрнутая назад: ``-level 4.1`` в
    аргументах кодировщика. Решение при этом не трогается ни одним полем - ни пресет, ни
    цель по битрейту, ни кадр, - а байты в SPS уезжают другие.
    """
    before = encode_imprint(DECISION)
    monkeypatch.setattr(encode_module, "encode_args", _with_level)
    after = encode_imprint(DECISION)

    assert before != after, "отпечаток не заметил флага, дописанного в боевую команду"


@pytest.mark.parametrize(
    ("rule", "value"),
    [("MAXRATE_GAIN", 1.30), ("VBV_SECONDS", 2.0), ("_KEY_SLACK", 0.05)],
)
def test_a_rule_that_is_no_field_of_the_decision_moves_the_imprint(
    monkeypatch: pytest.MonkeyPatch, rule: str, value: float
) -> None:
    """Правило живёт в коде, а не в решении, - и отпечаток обязан его видеть.

    Ни потолка кодера, ни буфера VBV, ни отступа опорного кадра среди полей решения нет:
    список полей рядом с ключом проглядел бы каждое из трёх. Форма их разворачивает, и
    потому форма их и ловит.
    """
    before = encode_imprint(DECISION)
    monkeypatch.setattr(encode_module, rule, value)

    assert encode_imprint(DECISION) != before, f"отпечаток проглядел правило {rule}"


def test_the_imprint_says_nothing_about_the_film_it_was_taken_on() -> None:
    """Отпечаток говорит о правилах, а не о фильме: границы уже входят в ключ отдельно.

    Считай он границы показа второй раз - каждый фильм давал бы свой отпечаток, ключи
    прежних прогонов не сходились бы сами с собой, и сравнивать между собой два выпуска
    стало бы нечем. Мера тут в двух строках сразу: сетка до боевой команды доезжает
    (первое утверждение), а до отпечатка - нет (второе).
    """
    one = Grid(bounds=(0.0, 10.0, 20.0), duration=30.0, on_keys=True)
    other = Grid(bounds=(0.0, 12.0, 21.0), duration=30.0, on_keys=True)

    assert DECISION.args(one, 0, 1) != DECISION.args(other, 0, 1), "сетка не дошла до команды"
    assert list(signature(encode_imprint).parameters) == ["encode"], "отпечатку дали знать фильм"
    assert len(DECISION.imprint) == 12
