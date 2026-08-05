"""Тесты состояния: атомарная запись, порог «досмотрено», сброс по --new."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from torrcast.state import Entry, State, load_config, save_config


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Не трогать /var/lib/torrcast и /etc/torrcast из тестов."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))


def test_roundtrip_creates_parent_dirs_and_keeps_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Состояние переживает запись и чтение, кириллица не экранируется."""
    nested = tmp_path / "var" / "lib" / "torrcast" / "state.json"
    monkeypatch.setenv("TORRCAST_STATE", str(nested))

    state = State()
    entry = Entry(title="Матрица", magnet="magnet:?xt=1", pos=2467, dur=8160)
    state.put("movie:матрица:1999", entry)
    state.save()

    assert "Матрица" in nested.read_text(encoding="utf-8")
    reloaded = State.load().get("movie:матрица:1999")
    assert reloaded is not None
    assert reloaded.pos == 2467
    assert reloaded.updated  # метку времени ставит put()


def test_watched_threshold_is_95_percent() -> None:
    """Позиция ≥ 95 % длительности = досмотрено → следующая серия (§2.4 ТЗ)."""
    assert not Entry(title="x", magnet="m", pos=940, dur=1000).watched
    assert Entry(title="x", magnet="m", pos=950, dur=1000).watched


def test_drop_forgets_entry() -> None:
    """`--new` сбрасывает запись и проходит выбор с нуля (§4 ТЗ)."""
    state = State()
    state.put("movie:тачки:2006", Entry(title="Тачки", magnet="m"))
    state.drop("movie:тачки:2006")

    assert state.get("movie:тачки:2006") is None


def test_missing_state_file_is_empty_not_error() -> None:
    """Отсутствующий файл состояния — не ошибка."""
    assert not State.load().entries


def test_config_requires_only_tv() -> None:
    """Конфиг переживает roundtrip; остальные поля имеют рабочие дефолты (§5 ТЗ)."""
    config = load_config()
    assert config.tv is None

    config.tv = "192.168.100.102"
    save_config(config)

    reloaded = load_config()
    assert reloaded.tv == "192.168.100.102"
    assert reloaded.torrserver_url.endswith(":8090")


def test_unknown_keys_in_state_are_ignored(tmp_path: Path) -> None:
    """Незнакомые поля из будущих версий не роняют чтение."""
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"movie:x:2000": {"title": "X", "magnet": "m", "totally_new": 1}}),
        encoding="utf-8",
    )

    entry = State.load().get("movie:x:2000")

    assert entry is not None
    assert entry.title == "X"


def test_watched_movie_is_marked_and_rewound() -> None:
    """Фильм досмотрен: пометка «досмотрено» и сброс позиции — следующий cast начнёт
    с начала и вопроса «продолжить?» не задаст (§2.3, §2.4).
    """
    entry = Entry(title="Моана 2", magnet="m", pos=5700, dur=5978)
    assert entry.watched and entry.resumable

    done = entry.advance()

    assert done.done and done.pos == 0 and not done.resumable
    assert done.magnet == "m" and done.audio == entry.audio  # выбор релиза сохраняется


def series(episode: int = 3, **fields: object) -> Entry:
    """Сериал с выбранной раздачей: три серии, у каждой свой файл (§2.4)."""
    return Entry(
        title="Киберпанк",
        magnet="m",
        kind="tv",
        audio=1,
        season=1,
        episode=episode,
        episodes=[[1, 2, 5], [1, 3, 6], [1, 4, 7]],
        **fields,  # type: ignore[arg-type]
    )


def test_watched_episode_moves_to_the_next_file_of_the_release() -> None:
    """Серия досмотрена: следующая серия раздачи с нуля, релиз и дорожка те же (§2.4).
    Следующая — это следующий ФАЙЛ раздачи, а не «номер + 1»: в раздаче может не быть
    ни первой серии, ни сплошной нумерации.
    """
    entry = series(episode=3, pos=1400, dur=1440)
    assert entry.watched and entry.label == "s1e3"

    following = entry.advance()

    assert (following.season, following.episode) == (1, 4)
    assert following.file_idx == 7, "играем файл этой серии, а не тот же самый"
    assert following.pos == 0 and following.dur == 0 and not following.done
    assert following.magnet == "m" and following.audio == 1  # выбор релиза не переспрашивается


def test_last_episode_of_the_release_ends_the_run() -> None:
    """Конец раздачи (или сезона): «досмотрено», и юнит гаснет — выдумывать несуществующую
    следующую серию мы не будем (§2.4).
    """
    ended = series(episode=4, pos=1400, dur=1440).advance()

    assert ended.done and ended.pos == 0
    assert (ended.season, ended.episode) == (1, 4), "остаёмся на последней сыгранной"


def test_jump_lands_on_the_cached_episode_or_honestly_refuses() -> None:
    """`cast киберпанк s1e2` при готовом кэше раздачи: файл и позиция с нуля, без вопросов.
    Серии в раздаче нет — ``None``, и цепочка идёт искать релиз нужного сезона (§2.4).
    """
    entry = series(episode=3, pos=900.0)

    jumped = entry.jump(1, 2)

    assert jumped is not None
    assert (jumped.season, jumped.episode, jumped.file_idx) == (1, 2, 5)
    assert jumped.pos == 0.0 and jumped.label == "s1e2"
    assert entry.jump(2, 5) is None


def test_broken_episode_table_does_not_break_reading(tmp_path: Path) -> None:
    """Битую строку списка серий лучше потерять, чем упасть на чтении состояния."""
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"tv:x:0": {"title": "X", "magnet": "m", "episodes": [[1, 1, 0], [2], "х"]}}),
        encoding="utf-8",
    )

    entry = State.load().get("tv:x:0")

    assert entry is not None and entry.episodes == [[1, 1, 0]]


def test_unfinished_entry_is_resumable_and_finished_is_not() -> None:
    assert not Entry(title="x", magnet="m", pos=0, dur=1000).resumable
    assert Entry(title="x", magnet="m", pos=10, dur=1000).resumable
    assert not Entry(title="x", magnet="m", pos=10, dur=1000, done=True).resumable


def test_find_takes_the_entry_by_the_users_query() -> None:
    """Resume ищет запись по запросу, не ходя в Prowlarr (§2.3): годятся и сохранённый
    запрос, и slug из ключа; чужая картина не подхватывается.
    """
    state = State()
    state.put("movie:моана-2:2024", Entry(title="Моана 2", magnet="m", query="моана-2", pos=100))
    state.put("movie:тачки:2006", Entry(title="Тачки", magnet="m", query="тачки", pos=50))

    assert state.find("Моана 2") is not None
    assert state.find("моана-2")[1].title == "Моана 2"  # type: ignore[index]
    assert state.find("тачки")[1].title == "Тачки"  # type: ignore[index]
    assert state.find("матрица") is None
    assert state.find("") is None


def test_find_lets_a_series_be_called_by_a_short_name() -> None:
    """Сериал ищут коротко: «киберпанк» вместо «киберпанк бегущие по краю» (§2.4).
    Фильму такое нельзя: «матрица» — запрос франшизы, а не «Матрица: Перезагрузка» (§2.2).
    """
    state = State()
    state.put(
        "tv:киберпанк-бегущие-по-краю:2022",
        Entry(title="Киберпанк", magnet="m", kind="tv", query="киберпанк-бегущие-по-краю"),
    )
    state.put(
        "movie:матрица-перезагрузка:2003",
        Entry(title="Матрица: Перезагрузка", magnet="m", query="матрица-перезагрузка", pos=10),
    )

    assert state.find("киберпанк") is not None
    assert state.find("матрица") is None


def test_latest_is_the_freshest_record() -> None:
    """`cast status` показывает последнее, что игралось."""
    state = State()
    state.put("movie:a:2000", Entry(title="A", magnet="m"))
    state.entries["movie:a:2000"].updated = "2026-08-05T01:00:00+03:00"
    state.put("movie:b:2001", Entry(title="B", magnet="m"))
    state.entries["movie:b:2001"].updated = "2026-08-05T02:00:00+03:00"

    found = state.latest()

    assert found is not None and found[1].title == "B"
    assert State().latest() is None
