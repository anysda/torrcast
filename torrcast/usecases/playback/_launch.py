"""Запуск показа: отказ безнадёжному, юнит, ожидание картинки на экране.

Зовут его команда показа и продолжение по сохранённому выбору.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.ports.clock import Clock
from torrcast.ports.journal import journal
from torrcast.ports.progress import Progress
from torrcast.ports.progress import progress as progress_bar
from torrcast.ports.show_unit import ShowUnit
from torrcast.ports.show_unit import unit as show_unit
from torrcast.ports.state_store import store
from torrcast.usecases.select._about import _about
from torrcast.usecases.start_budget import START_BUDGET
from torrcast.usecases.start_clock import _Clock


def _resume(config: Config, key: str, entry: Entry, clock: _Clock, dry: bool = False) -> int:
    """Молча продолжить с записанных релиза, файла, дорожки и позиции.

    Прежний прогрев позиции имел полезное время только пока человек отвечал на теперь
    удалённый вопрос. После запуска он конкурировал бы с ffmpeg за тот же рой, поэтому
    молчаливое продолжение сразу передаётся владельцу показа.
    """
    journal().mark("ответы")  # ноль секундомера: на этом пути вопросов нет
    return _launch(config, key, entry, _about(entry), clock, dry)


def _launch(
    config: Config, key: str, entry: Entry, about: str, clock: _Clock, dry: bool = False
) -> int:
    """Показ уезжает в transient-юнит: ``cast`` завершился — показ продолжается."""
    if dry:
        print(f"(--dry) {about} - каста нет")
        return EXIT_OK
    _refuse_hopeless(config, entry)
    # Сначала гасим прошлый показ и только потом пишем свою запись: умирающий юнит по
    # SIGTERM дописывает СВОЮ позицию, и записанный раньше прыжок на s1e5 он бы затёр.
    show_unit().stop()
    state = store().load()
    # Темнота прошлого показа новому не наследуется. Снимает отметку тот же сторож, что
    # её ставит (:attr:`torrcast.state.Entry.dark`), но у убитого по SIGKILL юнита сторожа
    # не было вовсе, а у нового она снимается только с первого опроса приёмника - и до
    # него `cast status` звал бы погасшим показ, который прямо сейчас поднимается.
    entry.dark, entry.dark_why = 0.0, ""
    state.put(key, entry)
    store().save(state)
    _state.forget_playing(Path(config.hls_dir))  # флажок прошлого показа нам не доказательство
    _state.start_play_unit(key)
    journal().mark("юнит")
    with progress_bar() as progress:
        _await_playing(config, progress)
    print(f"играю {about} - на ТВ   (старт {clock.total:.0f} с)")
    return EXIT_OK


def _refuse_hopeless(config: Config, entry: Entry) -> None:
    """Отказать ДО юнита, если этой записи на этом приёмнике картинки не видать.

    🔴 Случай ровно один, и он живой (TC-157): кадр 4К приёмник не берёт вовсе - ни в
    чужом кодеке, ни в своём. Замер 09-08-2026 на Q70D: пять заходов LOAD, каждый —
    ``IDLE/ERROR`` сразу после первого сегмента, картинки нет ни разу
    (:attr:`torrcast.profile.Profile.recode_frame`).

    ⚠️ TC-222 сузил проверку до одного условия, и это не ослабление. Ужать кадр вниз
    умеет сплошной перекод - значит отказывать надо не «большому кадру», а большому кадру
    БЕЗ перекода: ``recode: false`` в настройках. С включённым перекодированием ровно та
    же запись теперь играется - 2160p уезжает на приёмник как 1080p.

    Отбор такие релизы отбраковывает сам (:meth:`_Bench._trouble`), но мимо отбора ведут
    две двери: ``--release N`` / ``--file N`` (там человек выбрал сам, и подмен не бывает)
    и продолжение записи, попавшей в состояние через них же. Без этой проверки обе
    кончались одинаково: 86 с «жду телевизор», код 2 и ни слова о причине. Теперь
    причина печатается за доли секунды, а ffmpeg и раздача не поднимаются вовсе.

    Молчим там, где не знаем: кадр ноль — это записи прежних версий, они играются
    как раньше.
    """
    profile = _state.detect_profile(config).profile
    if not entry.frame or entry.frame <= profile.recode_frame:
        return
    if config.recode:
        return
    raise NotFoundError(
        f"{entry.quality or f'{entry.frame}p'} - такой кадр приёмник берёт только ужатым, "
        f"а перекодирование выключено: нужен релиз {profile.recode_frame}p или ниже"
    )


def _await_playing(
    config: Config,
    progress: Progress,
    timeout: float = START_BUDGET,
    clock: Clock | None = None,
    unit: ShowUnit | None = None,
) -> None:
    """Дождаться **картинки на экране**, а не «упаковка пошла».

    Две разные вещи, которые легко счесть одной: первый сегмент в tmpfs — это упаковка, а
    картинка — это приёмник, ответивший ``PLAYING``. Спросить приёмник отсюда нельзя:
    сендер к нему должен быть ровно один, и он живёт в юните (см. :mod:`torrcast.cast`).
    Поэтому юнит кладёт флажок (:func:`mark_playing`), а CLI его ждёт — и печатает
    «старт NN с» ровно в тот момент, когда на экране появилось изображение.

    ``clock`` и ``unit`` - выдержка ожидания и сам юнит показа
    (:class:`torrcast.ports.show_unit.ShowUnit`). Боевой путь ждёт настоящими секундами и
    спрашивает тот юнит, что поставил композиционный корень; сухому прогону дают свои
    часы и свой юнит прямо здесь, иначе тест выжидал бы весь бюджет старта по-настоящему.
    """
    unit = unit if unit is not None else show_unit()
    clock = clock if clock is not None else _state.CLOCK
    out = Path(config.hls_dir)
    flag = _state.playing_flag(out)
    deadline = clock.monotonic() + timeout
    packed = False
    while clock.monotonic() < deadline:
        if flag.exists():
            journal().mark("картинка")
            progress.phase("")
            return
        if not packed:
            with contextlib.suppress(OSError):
                packed = any(out.glob("v*.ts"))
            if packed:
                journal().mark("первый сегмент")
        progress.phase("жду телевизор" if packed else "упаковка")
        if not unit.active():
            progress.phase("")
            raise InfraError(f"показ не запустился: {unit.why()}")
        clock.sleep(0.2)
    progress.phase("")
    unit.stop()
    raise InfraError(f"показ не начался за {timeout:.0f} с - {unit.why()}")
