"""Таблица релизов: N, качество, размер, сиды, озвучка, студия, кодек."""

from __future__ import annotations

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.rank.render_table import render_table


def test_the_table_names_the_columns_and_the_row() -> None:
    table = render_table([rel(name="Кино", seeders=42, voices=("Дубляж",))], RUNTIME, 20.0)
    lines = table.splitlines()

    assert lines[0] == "Релизы:"
    assert lines[1].split() == ["N", "Качество", "Размер", "Сиды", "Озвучка", "Студия", "Кодек"]
    assert lines[2].split() == ["1", "1080p", "8.0", "ГБ", "42", "Дубляж", "-", "H.264"]


def test_the_columns_are_padded_to_one_width() -> None:
    """Без выравнивания таблица читается как список, а не как таблица."""
    rows = [rel(name="первый", seeders=7), rel(name="второй", seeders=1234)]
    lines = render_table(rows, RUNTIME, 20.0).splitlines()

    head, first, second = lines[1], lines[2], lines[3]
    assert head.index("Сиды") == first.index("7") == second.index("1234")
    assert all(line.startswith("  ") for line in lines[1:])


def test_the_limit_cuts_the_tail_and_says_how_much_is_left() -> None:
    """Ниже предела - раздачи без сидов, выбирать там нечего."""
    many = [rel(name=f"р{n}", seeders=n) for n in range(20)]
    assert render_table(many, RUNTIME, 20.0, limit=3).splitlines()[-1] == (
        "  ... и ещё 17 с меньшим числом сидов"
    )


def test_a_fat_release_carries_its_warning_into_the_codec_column() -> None:
    assert phrase("choice.mark_heavy") in render_table(
        [rel(name="жирный", size_gb=28)], RUNTIME, 20.0
    )


def test_the_studio_column_names_who_voiced_it() -> None:
    """Строки сериала подписаны одинаково, и руками из них выбирают по студии."""
    kitchen = rel(
        name="Кино (Сезон 2) WEB-DL 1080p, Dub (The Kitchen Russia) + MVO (Good People)",
        voices=("Дубляж", "Многоголосый"),
    )
    row = render_table([kitchen], RUNTIME, 20.0).splitlines()[2]

    assert "The Kitchen Russia, Good People" in row


def test_the_marks_counted_by_a_guess_are_named_a_guess() -> None:
    """🔴 TC-819. Длительность - прикидка, и пометки веса говорят это вслух.

    Прикидка «серия это 45 минут» против замеренных 27 занижает битрейт вдвое: молча
    отдать такие пометки за замеренные значило бы врать про каждую строку таблицы.
    """
    table = render_table([rel(name="Кино", seeders=42)], RUNTIME, 20.0, estimated=True)

    assert "по оценке длительности" in table.splitlines()[-1]


def test_the_marks_counted_by_a_measurement_carry_no_footnote() -> None:
    """Замер паспорта или хронометраж справки - не оценка, и сноски у таблицы нет."""
    table = render_table([rel(name="Кино", seeders=42)], RUNTIME, 20.0)

    assert "по оценке" not in table
