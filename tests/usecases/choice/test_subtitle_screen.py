"""Сшитая склейка: одно имя в пункте, подсказке, выборе и сухом запуске."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.usecases.choice.world import Outside, outside, plan
from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.args import Args
from torrcast.domain.catalogs.tongue import RU, _choose_tongue
from torrcast.domain.cluster import cluster
from torrcast.domain.config import Config
from torrcast.domain.media import Media
from torrcast.domain.raw_result import RawResult
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.cast_command._entry_for import _entry_for
from torrcast.usecases.choice._pick_plan import _pick_plan
from torrcast.usecases.choice.default_line import default_line
from torrcast.usecases.choice.menu_blocks import menu_blocks
from torrcast.usecases.playback._launch import _launch
from torrcast.usecases.select._about import _about
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.start_clock import _Clock


def test_one_picture_keeps_its_name_on_every_screen_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _choose_tongue(RU)
    pairs = json.loads((Path(__file__).parents[2] / "fixtures/katalog/subtitles.json").read_text())
    _, first, second = pairs[0]
    # Две обычные раздачи против одной номерной: подпись выбирает живое большинство.
    rows = [RawResult(name, str(i) * 40) for i, name in enumerate((first, second, second))]
    pictures = cluster(to_releases(rows))
    assert len(pictures) == 1
    picture = pictures[0]
    one = plan(pool=picture.releases)
    one.picture = picture
    title = "Пираты Карибского моря: На краю Света"
    world = Outside()
    with outside(world):
        assert menu_blocks([one]) == [[f"  1. {title} (2007)"]]
        assert f"«{title} (2007)»" in default_line([one], 1)
        chosen = _pick_plan([one], pick=1, asked="пираты карибского моря", environment=world)
    assert chosen is one
    assert title in world.said[-1]
    assert "Пираты Карибского моря 3:" not in "\n".join(world.said)
    # Запуск берёт имя картины, даже если выбран релиз с номерным именем.
    release = next(r for r in picture.releases if r.raw_name == first)
    prep = _Prep(number=1, release=release)
    video = TorrFile(index=1, name="film.mkv", size=1_000_000)
    prep.media = Media(duration=7200)
    entry = _entry_for(one, prep, release, video, prep.media, 0, "Дубляж", "", Args(query=[title]))
    assert entry.title == title
    assert _launch(Config(), "test", entry, _about(entry), _Clock(), dry=True) == 0
    assert f"«{title}»" in capsys.readouterr().out
