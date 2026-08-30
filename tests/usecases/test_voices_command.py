"""Зеркало отладочной ручки ``cast voices``: своё слово снято, внешний мир от корня."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.fakes.composition import use_settings
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.not_found_error import NotFoundError
from torrcast.runtime.wire import wire
from torrcast.usecases import voices_command
from torrcast.usecases.voices_command import _cmd_voices


@pytest.fixture(autouse=True)
def _russian_menu(_russian_product: None) -> None:
    """Предмет всего модуля - меню озвучек, писанное по-русски до языкового яруса."""


def test_an_empty_query_is_an_honest_line_not_a_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """``cast voices`` без запроса - это вопрос «что искать?», а не поход в каталог.

    Своё слово команда снимает с запроса сама и остаток называет внутренним запросом:
    останься «voices» в строке, команда молча ушла бы искать картину с таким именем -
    ни в рой, ни к индексерам за этим ходить не нужно.
    """
    use_settings(monkeypatch, Config)

    def never(*_args: Any, **_kwargs: Any) -> list[Any]:
        raise AssertionError("искать без запроса нечего")

    with pytest.raises(NotFoundError, match="что искать"):
        _cmd_voices(Args(query=["voices"]), search=never)


def test_the_inner_query_keeps_the_handles_that_name_a_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Внутренний запрос уносит ``--release``/``--pick``/``--file`` и роняет остальное.

    Названная раздача, картина и файл - это про то, ЧТО показать список озвучек, и
    потерять их значило бы отвечать про чужую раздачу. А ``--voice`` и ``--new``
    относятся к показу, которого здесь нет вовсе.
    """
    use_settings(monkeypatch, Config)
    seen: list[Args] = []

    def search(_config: Any, args: Args, *_rest: Any) -> list[Any]:
        seen.append(args)
        raise NotFoundError("дальше стенду нечем отвечать")

    with pytest.raises(NotFoundError):
        _cmd_voices(
            Args(query=["voices", "кино"], release=3, pick=2, file=5, voice=7, from_start=True),
            search=search,
        )
    (inner,) = seen
    assert inner.query == ["кино"]
    assert (inner.release, inner.pick, inner.file) == (3, 2, 5)
    assert (inner.voice, inner.from_start) == (None, False)


def test_the_composition_root_hands_the_command_its_whole_outside_world(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Настройки, служба раздач и происхождение картины приходят от корня."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    wire()
    slots = [name for name in voices_command.__annotations__ if name.startswith("_voices_")]
    assert slots, "у меню озвучек обязаны быть объявленные слоты внешнего мира"
    assert [name for name in slots if not hasattr(voices_command, name)] == []
    assert _cmd_voices is not None
