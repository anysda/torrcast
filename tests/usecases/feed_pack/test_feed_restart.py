"""Заход упаковки: кого предупредить, где измерить старт и что сказать зрителю."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from tests.usecases.feed_pack.world import factory, feed, grid, packer, signals, tract
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.recode.whole_encode import FULL_PRESET
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.hls_settings import PACK_DIR
from torrcast.usecases.feed_pack.feed_restart import _restart
from torrcast.usecases.feed_pack.feed_survive import _survive

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _Recoder:
    """Кодировщик тяжёлых кусков: запоминает, когда ему сказали о новом месте показа."""

    spare: Any = None
    seen: list[str] = field(default_factory=list)

    def opening(self, slot: int) -> None:
        self.seen.append(f"голова {slot}")

    def note(self, slot: int, how: str) -> None: ...

    def holding(self, slot: int, size: int) -> bool:
        return False


def _tract(seen: list[str], at: float = 0.0) -> list[tuple[Any, ...]]:
    """Собрать заходу стендовый медиатракт; возвращает поднятые прогоны."""
    started: list[tuple[Any, ...]] = []

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        started.append((command, out, run, first, kwargs))
        run.mkdir(parents=True, exist_ok=True)
        return packer(out.parent, out=out, run=run, first=first)

    def _pilot(source: str, want: float) -> tuple[float, float]:
        seen.append("проба")
        return want, at

    tract(
        settle_start=_pilot,
        pack_command=lambda *a, **k: ["ffmpeg", *map(str, a[4:6])],
        packer=factory(_start),
    )
    return started


def test_the_encoder_learns_about_the_new_place_before_the_pilot_run(
    tmp_path: Path, journal: Path
) -> None:
    """Голову прогона кодировщик обязан начать не позже упаковщика: пробный стоит 0.5-1.7 с."""
    seen: list[str] = []
    started = _tract(seen)
    recoder = _Recoder(spare=tmp_path / "recode")
    show = feed(tmp_path, recoder=recoder)

    _restart(show, 5, lambda slot, size: False)

    assert recoder.seen == ["голова 5"]
    assert seen == ["проба"], "пробный прогон обогнал кодировщика"
    assert started and started[0][3] == 5


def test_a_whole_film_recode_never_asks_the_pilot_and_stands_where_the_grid_says(
    tmp_path: Path, journal: Path
) -> None:
    """Перекодирующему прогону пробный вреден: по ``-ss`` он встаёт точно, докатки нет.

    Измеренное ``at`` увело бы весь прогон на сегмент назад - эта грабля уже стоила
    отладки кодировщику.
    """
    seen: list[str] = []
    started = _tract(seen, at=8.0)
    show = feed(tmp_path, grid=grid(60.0, 10.0), encode=object())

    _restart(show, 3, lambda slot, size: False)

    assert seen == [], "пробный прогон при сплошном перекоде звать нельзя"
    assert started[0][4]["at"] == 30.0


def test_the_run_starts_where_it_was_measured_and_the_rollback_is_told(
    tmp_path: Path, journal: Path
) -> None:
    """Место захода берут у пробного прогона, а докатку называют зрителю вслух.

    ``-segment_times`` считаются от ``at``, а муксер отмеряет их от первого пакета
    прогона: отдай мы задуманное начало - и все резы уехали бы на всю докатку.
    """
    seen: list[str] = []
    said: list[str] = []
    started = _tract(seen, at=28.4)
    show = feed(tmp_path, grid=grid(60.0, 10.0), log=said.append)

    _restart(show, 3, lambda slot, size: False)

    assert started[0][4]["at"] == 28.4
    assert started[0][2] == show.out / PACK_DIR
    want = phrase("feed.pack_from", start="30.0") + phrase("feed.catchup", drop="1.6")
    assert said == [want]


def test_a_run_that_stands_where_it_was_asked_says_nothing_about_a_rollback(
    tmp_path: Path, journal: Path
) -> None:
    """Докатки нет - и строки о ней нет: допуск сравнения меньше полкадра."""
    said: list[str] = []
    _tract([], at=30.0)
    show = feed(tmp_path, grid=grid(60.0, 10.0), log=said.append)

    _restart(show, 3, lambda slot, size: False)

    assert said == [phrase("feed.pack_from", start="30.0")]


def test_the_previous_run_is_taken_down_but_its_pieces_stay(tmp_path: Path, journal: Path) -> None:
    """Под именем ``vN`` и до, и после перезапуска лежит одно и то же место фильма."""
    _tract([])
    show = feed(tmp_path, grid=grid(60.0, 10.0))
    old = packer(tmp_path, first=0, out=show.out)
    (show.out / "v0.ts").write_bytes(b"old")
    show.packer = old

    _restart(show, 3, lambda slot, size: False)

    assert old.stopped == phrase("feed.restart_reason", slot=3) and signals(old) == ["terminate"]
    assert (show.out / "v0.ts").exists(), "перезапуск выбросил уже упакованное"
    assert show.packer is not old


def test_a_whole_film_recode_builds_an_encoding_command_from_the_grid(
    tmp_path: Path, journal: Path
) -> None:
    """Команда перекодирующего прогона встаёт от границы сетки и без докатки.

    Сборка команды тут настоящая: подделай её - и проверять было бы нечего, а вредна
    докатка ровно в готовой команде (``-segment_start_number`` и ``-ss`` разъехались бы,
    и весь прогон уехал бы на сегмент назад - грабля, стоившая отладки кодировщику).
    """
    lines = grid(600.0, 10.0)
    seen: list[list[str]] = []

    def _pilot(source: str, want: float) -> tuple[float, float]:
        raise AssertionError("пробный прогон при сплошном перекоде звать нельзя")

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        seen.append(command)
        run.mkdir(parents=True, exist_ok=True)
        return packer(out.parent, out=out, run=run, first=first)

    tract(settle_start=_pilot, packer=factory(_start))
    show = feed(tmp_path, grid=lines, encode=Encode(preset=FULL_PRESET))

    _restart(show, 5, lambda slot, size: False)

    command = seen[0]
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-segment_start_number") + 1] == "5", "докатки нет"
    assert command[command.index("-ss") + 1] == f"{lines.start(5):.3f}"


def test_our_own_restart_does_not_spend_the_crash_count(tmp_path: Path, journal: Path) -> None:
    """Снятый нами прогон - не обрыв: счёт ``crashes`` на перезапуске не растёт.

    🔴 TC-905. Окно тут настоящее: :attr:`packer` подменяется в конце захода, а до этого
    внутри лежит пробный прогон (0.5-1.7 с), и часы показа всё это время видят наш же
    труп текущим прогоном. Без довода он неотличим от обрыва, и на стенде это выходило
    строкой «упаковка оборвалась (молча, код 255)» - 255 есть ответ ffmpeg на SIGTERM.

    Мера тут не поле, а вред: поле ``stopped`` проверено выше
    (:func:`test_the_previous_run_is_taken_down_but_its_pieces_stay`), здесь считается
    то, на чём стоят решения о живости упаковки. Вторая половина держит сторожа с той же
    стороны: чужая смерть обязана считаться по-прежнему, иначе счёт замолчал бы весь.
    """
    said: list[str] = []
    _tract([])
    show = feed(tmp_path, grid=grid(60.0, 10.0), log=said.append)
    old = packer(tmp_path, first=0, out=show.out)
    show.packer = old

    _restart(show, 3, lambda slot, size: False)
    said.clear()

    assert _survive(show, old), "свой же перезапуск похоронил показ"
    assert show.crashes == 0, f"наш SIGTERM засчитан обрывом: {said}"
    assert said == [], "показ пожаловался зрителю на нами же снятый прогон"

    alien = packer(tmp_path, first=0, out=show.out)
    alien.proc.terminate()

    assert _survive(show, alien)
    assert show.crashes == 1, "чужой обрыв перестал считаться - счёт замолчал весь"
