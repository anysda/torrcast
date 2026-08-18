"""Порт индикатора: без корня он молчит, назначенный - получает фазы и заметки."""

from __future__ import annotations

from typing import ClassVar

from torrcast.ports.progress import Progress, Quiet, install, progress


def test_without_a_root_the_bar_is_quiet_and_not_a_failure() -> None:
    """Прогон без композиционного корня ничего не рисует и не падает."""
    install(Quiet)

    with progress() as bar:
        bar.phase("поиск «моана»")
        bar.note("выбрана раздача")
        bar.stop()

    assert isinstance(progress(), Quiet)


def test_every_call_gets_its_own_bar() -> None:
    """Индикатор заводится на фазу работы, а не один на процесс: их бывает несколько."""

    class _Spy:
        seen: ClassVar[list[str]] = []

        def phase(self, text: str) -> None:
            self.seen.append(text)

        def note(self, text: str) -> None:
            self.seen.append(f"# {text}")

        def stop(self) -> None:
            return None

        def __enter__(self) -> _Spy:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    install(_Spy)
    first, second = progress(), progress()

    assert first is not second, "два вызова - два индикатора"
    bar: Progress = first
    bar.phase("поиск")
    assert _Spy.seen == ["поиск"]
    _Spy.seen.clear()
