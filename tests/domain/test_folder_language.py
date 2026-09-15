"""Зеркало :func:`torrcast.domain.folder_language.folder_language`."""

from __future__ import annotations

import pytest

from torrcast.domain.folder_language import folder_language


@pytest.mark.parametrize(
    ("path", "language"),
    [
        ("Naruto/Sound/Rus [Dub+MVO]/[2x2] [001-220] [MVO]/Naruto - 001.mka", "rus"),
        ("Naruto/Sound/Eng [Dub]/Naruto - 001.mka", "eng"),
        ("Show/Озвучка/Русская/Show - 01.mka", "rus"),
        ("Russian Doll S01/Russian.Doll.S01E01.mka", None),
        ("Show/Sound/Rustam/Show - 01.mka", None),
        ("Show - 01.mka", None),
    ],
)
def test_the_nearest_named_folder_tells_the_language(path: str, language: str | None) -> None:
    """Ближайший каталог, назвавший язык, решает; корень раздачи и похожие слова - нет."""
    assert folder_language(path) == language
