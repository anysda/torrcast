"""Запуск показа: отказ безнадёжному, юнит, ожидание картинки на экране.

Зовут его команда показа и продолжение по сохранённому выбору."""

from __future__ import annotations

import contextlib

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.cancelled_error import CancelledError
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.infra_error import InfraError
from torrcast.domain.playing_where import playing_where
from torrcast.ports.clock import Clock
from torrcast.ports.journal.slot import journal
from torrcast.ports.progress.progress import Progress
from torrcast.ports.progress.slot import progress as progress_bar
from torrcast.ports.show_unit.show_unit import ShowUnit
from torrcast.ports.show_unit.slot import unit as show_unit
from torrcast.ports.state_store.slot import store
from torrcast.usecases.playback._refuse_hopeless import _refuse_hopeless
from torrcast.usecases.playback.hls_root import hls_root
from torrcast.usecases.playback.launch_owner import LaunchOwner
from torrcast.usecases.playback.place_kept import place_kept
from torrcast.usecases.playback.refuse_called_off import refuse_called_off
from torrcast.usecases.select._about import _about
from torrcast.usecases.start_budget import START_BUDGET
from torrcast.usecases.start_clock import _Clock
from torrcast.usecases.still_playing import still_playing


def _resume(
    config: Config, key: str, entry: Entry, clock: _Clock, dry: bool = False, here: bool = False
) -> int:
    """Молча продолжить с записанных релиза, файла, дорожки и позиции.

    Прежний прогрев позиции имел полезное время только пока человек отвечал на теперь
    удалённый вопрос. После запуска он конкурировал бы с ffmpeg за тот же рой, поэтому
    молчаливое продолжение сразу передаётся владельцу показа."""
    journal().mark("ответы")  # ноль секундомера: на этом пути вопросов нет
    return _launch(config, key, entry, _about(entry), clock, dry, here)


def _launch(
    config: Config,
    key: str,
    entry: Entry,
    about: str,
    clock: _Clock,
    dry: bool = False,
    here: bool = False,
) -> int:
    """Показ уезжает в transient-юнит: ``cast`` завершился — показ продолжается.

    🔴 Отказ человека спрашивается на двух поворотах подъёма, и что он значит, названо
    в :mod:`torrcast.usecases.playback.refuse_called_off`: до юнита - здесь, а при уже
    живом юните - в ожидании картинки (:func:`_await_playing`). ``here`` - приёмник ЭТОГО
    запуска - страница, а не ``config.tv``: юнит берёт это ключом командной строки."""
    if dry:
        print(phrase("playback.dry_run_no_cast", about=about))
        return EXIT_OK
    refuse_called_off()
    _refuse_hopeless(config, entry)
    out = hls_root(config.hls_dir)
    owner = LaunchOwner.claim(out)  # до погашения прошлого: его ожидание узнает, что снято
    # Сначала гасим прошлый показ и только потом пишем свою запись: умирающий юнит по
    # SIGTERM дописывает СВОЮ позицию, и записанный раньше прыжок на s1e5 он бы затёр.
    show_unit().stop()
    state = store().load()
    before = state.get(key)  # место, которое не поднявшийся показ обязан вернуть (place_kept)
    # Темнота прошлого показа новому не наследуется. Снимает отметку тот же сторож, что
    # её ставит (:attr:`torrcast.domain.entry.Entry.dark`), но у убитого по SIGKILL юнита сторожа
    # не было вовсе, а у нового она снимается только с первого опроса приёмника - и до
    # него `cast status` звал бы погасшим показ, который прямо сейчас поднимается.
    entry.dark, entry.dark_why = 0.0, ""
    # Продолжение начинается с чужой, уже положительной позиции ПРОШЛОГО сеанса: она ничего не
    # говорит про кадр этого запуска. Без сброса здесь `cast status` и мост Home Assistant звали бы
    # паузой показ, который ещё не начал играть (TC-1002). Слово о паузе сбрасывается по той же
    # причине: оно отвечало за экран прошлого сеанса, а не этого.
    entry.moved = False
    entry.paused = ""
    state.put(key, entry)
    store().save(state)
    _state.forget_playing(out)  # флажок прошлого показа нам не доказательство
    with place_kept(key, before, owner.taken_over):
        _state.start_play_unit(key, here)
        journal().mark("юнит")
        with progress_bar() as progress:
            _await_playing(config, progress, start=entry.pos, owner=owner)
    where = playing_where(here)
    print(phrase("playback.now_playing", about=about, secs=f"{clock.total:.0f}", where=where))
    return EXIT_OK


def _await_playing(
    config: Config,
    progress: Progress,
    timeout: float = START_BUDGET,
    clock: Clock | None = None,
    unit: ShowUnit | None = None,
    start: float = 0.0,
    owner: LaunchOwner | None = None,
) -> None:
    """Дождаться **картинки на экране**, а не «упаковка пошла».

    Две разные вещи, которые легко счесть одной: первый сегмент в tmpfs — это упаковка, а картинка
    — это приёмник, сдвинувший указатель (слова ``PLAYING`` мало, он говорит его раньше кадра).
    Спросить приёмник отсюда нельзя: сендер к нему должен быть ровно один, и он живёт в юните (см.
    :mod:`torrcast.adapters.chromecast.cast`). Поэтому юнит кладёт флажок (:func:`mark_playing`), а
    CLI его ждёт — и печатает «старт NN с». Флажок ставится на круге опроса приёмника, поэтому до
    первого кадра юнит спрашивает его чаще
    (:data:`torrcast.domain.start_settings.FIRST_FRAME_POLL`): иначе строка запаздывала бы за
    настоящим кадром на секунды.

    ``clock`` и ``unit`` - выдержка ожидания и сам юнит показа
    (:class:`torrcast.ports.show_unit.show_unit.ShowUnit`). Боевой путь ждёт настоящими секундами и
    спрашивает тот юнит, что поставил композиционный корень; сухому прогону дают свои
    часы и свой юнит прямо здесь, иначе тест выжидал бы весь бюджет старта по-настоящему.

    🔴 Потеря флажка не имеет права стоить зрителю серии. Флажок - доказательство
    одностороннее: он есть только когда картинка доказана, но его отсутствие само по себе
    ничего не доказывает, а лежит он в каталоге, куда ходит не только показ. Поэтому
    исчерпанный бюджет - это не приговор, а повод спросить сам юнит
    (:func:`torrcast.usecases.still_playing.still_playing`): двинувшийся указатель значит, что
    зритель СМОТРИТ, и гасить тут нечего. ``start`` - место, куда показ заводили: без него
    «указатель двинулся» не отличить от «приёмник сказал PLAYING, не дав ни кадра».

    🔴 TC-1010. Сверяется указатель не с самой закладкой, а с настоящим местом посадки
    (:func:`torrcast.adapters.stream_pack.read_landed.read_landed`): после TC-1002 показ
    вправе сесть НИЖЕ закладки (:func:`torrcast.usecases.feed_pack.feed_restart._begin`
    берёт ближайший опорный кадр не позже неё, а отвод назад на неудачном заходе отступает
    ещё дальше). Указатель приёмника тогда честно меньше закладки, но БОЛЬШЕ настоящей
    посадки - и гасить показ, который зритель уже смотрит, было бы не за что. Файла нет -
    значит спрашивать нечего, и в дело идёт сама закладка, как и до TC-1002.

    🔴 ``owner`` - метка ЭТОГО подъёма (:mod:`torrcast.usecases.playback.launch_owner`). Имя
    юнита одно на машину, и чужой запуск (мост веба, бот, консоль) гасит наш юнит и ставит
    свой под тем же именем: ожидание, не сверявшее метку, кончалось чужой картинкой или
    звало своим отказом смерть погашенного юнита («показ не запустился», TC-1203). Метка
    сверяется раньше флажка - флажок мог поставить уже чужой показ, - и чужой юнит при
    этом не гасится: он не наш."""
    unit = unit if unit is not None else show_unit()
    clock = clock if clock is not None else _state.CLOCK
    # 🔴 Строка берётся и ДО ожидания. Имя юнита переживает показы, и в журнале за ним
    # лежит хвост ПРОШЛОГО сеанса: свежий юнит своих строк ещё не сказал, а послесловие
    # systemd отсеивается (:func:`torrcast.adapters.systemd.unit_why.unit_why`). Не
    # сдвинувшаяся за весь бюджет строка - это тот хвост и есть, и принять его за
    # картинку значило бы оставить зрителя перед чёрным экраном с бодрым «показ идёт».
    stale = unit.why()
    out = hls_root(config.hls_dir)
    flag = _state.playing_flag(out)
    deadline = clock.monotonic() + timeout
    packed = False
    while clock.monotonic() < deadline:
        _yield_to_other(owner, progress)
        refuse_called_off(progress, unit)
        if flag.exists():
            journal().mark("картинка")
            progress.phase("")
            return
        if not packed:
            with contextlib.suppress(OSError):
                packed = any(out.glob("v*.ts")) or any(out.glob("v*.m4s"))
            if packed:
                journal().mark("первый сегмент")
        progress.phase(phrase("playback.waiting_tv") if packed else phrase("playback.packing"))
        if not unit.active():
            _yield_to_other(owner, progress)
            progress.phase("")
            raise InfraError(phrase("playback.did_not_start", why=unit.why()))
        clock.sleep(0.2)
    _yield_to_other(owner, progress)
    progress.phase("")
    said = unit.why()
    landed = _state.read_landed(out, start)
    if said != stale and still_playing(said, landed):
        journal().mark("картинка")
        print(
            phrase("playback.picture_undetected_but_playing", secs=f"{timeout:.0f}", said=said),
            flush=True,
        )
        return
    unit.stop()
    raise InfraError(phrase("playback.did_not_start_timeout", secs=f"{timeout:.0f}", said=said))


def _yield_to_other(owner: LaunchOwner | None, progress: Progress) -> None:
    """Подъём снят чужим запуском - кончить ожидание отменой, не трогая чужой юнит."""
    if owner is not None and owner.taken_over():
        progress.phase("")
        raise CancelledError(phrase("playback.abandoned"))
