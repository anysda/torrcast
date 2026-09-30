"""Checks what each indexer is asked in a circle of the picture's names."""

from torrcast.domain.joint_query import JOINT, joint_query
from torrcast.domain.wire_query import wire_query


def test_only_jacred_takes_the_joined_names() -> None:
    joint = JOINT.join(["Тачки 2006", "Cars 2006"])
    assert joint_query("JacRed", "Тачки 2006", joint) == joint
    assert joint_query("RuTor", "Тачки 2006", joint) == "Тачки 2006"


def test_the_viewers_text_is_asked_as_typed() -> None:
    assert joint_query("JacRed", "Тачки", None) == "Тачки"


def test_the_viewers_text_takes_the_names_along_to_jacred_alone() -> None:
    names = JOINT.join(["Тачки 2006", "Cars 2006"])
    joined = JOINT.join(["Тачки", "Тачки 2006", "Cars 2006"])
    assert joint_query("JacRed", "Тачки", None, names) == joined
    assert joint_query("RuTor", "Тачки", None, names) == "Тачки"


def test_an_empty_joint_leaves_jacred_out() -> None:
    assert joint_query("JacRed", "Cars 2006", "") == ""


def test_the_joint_survives_the_wire() -> None:
    joint = JOINT.join(["Тачки 2006", "Cars 2006"])
    assert wire_query(joint) == joint
