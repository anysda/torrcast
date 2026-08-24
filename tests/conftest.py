"""Общее для тестов потока: self-signed серт, синтетический ролик-источник и заглушки
упаковки, которые нужны сразу двум наборам тестов.
"""

from __future__ import annotations

import ast
import functools
import importlib
import inspect
import socket
import subprocess
import sys
import threading
import time
from fractions import Fraction
from types import ModuleType
from typing import TYPE_CHECKING

import pytest

from tests import thread_guard
from tests.fakes import composition
from tests.fakes.cast_world import CastWorld
from tests.fakes.journal import Tape
from tests.fakes.pretend_tty import PretendTty
from tests.fakes.show_unit import FakeShowUnit
from torrcast.adapters.filesystem.trace_journal.log_dir import LOG_ENV
from torrcast.adapters.filesystem.trace_journal.session_id import SID_ENV
from torrcast.domain.debug_handles import CTL_ENV
from torrcast.domain.facts.origin import Origin
from torrcast.ports.journal import slot as journal_slot
from torrcast.ports.progress import slot as progress_slot
from torrcast.ports.show_unit import slot as unit_slot
from torrcast.ports.state_store import slot as state_slot
from torrcast.runtime.wire import wire

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from torrcast.adapters.stream_pack.packer import Packer

#: Длина синтетического ролика. Держим её кратной сетке HLS и с запасом в несколько
#: сегментов: на сетке 10 с двадцатисекундный ролик - это всего два сегмента,
#: и «продолжить с середины» на нём проверять уже нечего.
CLIP_SECONDS = 60

#: Частота кадров синтетических роликов, дробью для ffmpeg. 🔴 Это не вкус и не
#: правдоподобие, а условие видимости целого класса дефектов.
#:
#: На ровной сетке рез идёт по ВРЕМЕНИ, а не по кадру (``-break_non_keyframes 1``), а
#: принудительный опорный кадр кодировщик ставит на границу минус
#: :data:`torrcast.adapters.recode.encode_settings._KEY_SLACK`. Когда период кадра делит
#: границу нацело, этот кадр всякий раз ложится ровно на рез и достаётся куску справа:
#: куска, начинающегося НЕ с опорного кадра, на таком входе не бывает ни разу. А наружу
#: перекод идёт склейкой со звуком копии, склейка копирует поток ``-c copy``, и
#: копирование выбрасывает всё до первого опорного кадра - нет его вовсе, выброшено ВСЁ
#: видео, и зритель получает десять секунд звука на чёрном экране
#: (:func:`torrcast.adapters.stream_pack.key_missing.key_missing`).
#:
#: Замер на заходе кодировщика ``v1..v3`` по ровной сетке 10 с: 25 к/с - 0 кусков без
#: опорного кадра из 3, ровные 24 к/с - тоже 0, 24000/1001 - 1 из 3, 30000/1001 - 1 из 3.
#: Делят границу нацело ровно первые два, и они же были входом всего набора.
#:
#: Взята частота кинопроката: 10 с - это 239.76 кадра, сетка в границу не попадает
#: никогда, а ещё это самая частая частота живых релизов.
CLIP_FPS = Fraction(24000, 1001)
CLIP_RATE = f"{CLIP_FPS.numerator}/{CLIP_FPS.denominator}"

#: Через сколько КАДРОВ ролики ставят опорный кадр (``-g``).
CLIP_GOP = 50

#: Шаг опорных кадров ролика, секунды. Числом, а не строкой в комментарии: у ролика с
#: дробной частотой опорные кадры стоят не на круглых секундах, и тест, которому надо
#: встать ЗАВЕДОМО между ними, обязан считать это место, а не переписывать от руки.
CLIP_KEY_SECONDS = float(CLIP_GOP / CLIP_FPS)

# Любой тест из этой группы получает настоящий медиафайл, собранный ffmpeg. Маркер
# ставится по замыканию фикстур: так зависимость не потеряется, когда тест начнёт брать
# не ``clip`` напрямую, а производный mp4 или общую фикстуру поверх него.
FFMPEG_FIXTURES = frozenset({"clip", "clip_hevc", "clip_mp4", "clip_mp4_tail", "clip_mp4_bframes"})

# Эти проверки намеренно меряют настоящий планировщик, TCP/TLS или ожидание потока.
# Их нельзя честно распараллеливать с быстрым набором: под CPU-нагрузкой пауза потока
# становится частью замера. Список по nodeid оставляет логические тесты тех же модулей
# быстрыми; сторож ниже не даёт забыть внести сюда новый прямой машинный вызов.
# Это намеренно неглубокая проверка: вызовы в фикстурах и вынесенных хелперах она
# не видит, поэтому их машинную природу по-прежнему надо отмечать при ревью.
MACHINE_TESTS = frozenset(
    {
        # Локальные HTTP/TLS-серверы и настоящий TCP blackhole.
        "tests/test_shim.py::test_two_at_a_time_on_the_host",
        "tests/test_shim.py::test_alone_does_not_wait",
        "tests/test_shim.py::test_queue_is_per_host",
        "tests/test_shim.py::test_silent_candidate_does_not_hide_working_fallback",
        "tests/test_shim.py::test_shim_asks_gzip_and_unpacks_it",
        "tests/test_shim.py::test_client_that_asked_gzip_gets_it_as_is",
        "tests/test_shim.py::test_пятисотый_уводит_на_следующего_кандидата",
        "tests/test_shim.py::test_чужой_отказ_доезжает_когда_кандидаты_кончились",
        "tests/test_shim.py::test_dropped_client_frees_slot_at_once",
        "tests/test_shim.py::test_dropped_client_leaves_queue_before_a_slot_opens",
        "tests/test_shim.py::test_молчащий_клиент_не_запирает_шим_целиком",
        "tests/test_shim.py::test_client_gone_before_the_answer_is_one_line_not_a_traceback",
        "tests/test_shim.py::test_a_real_shim_failure_still_screams",
        "tests/adapters/systemd/test__systemd_call.py::test_the_plumbing_answers_about_a_unit_that_does_not_exist",
        # Потоки с настоящими сроками: поведение состоит именно в возврате до deadline.
        "tests/test_hls.py::test_a_promised_place_is_never_answered_with_a_404",
        "tests/test_hls.py::test_a_seek_back_behind_the_run_repacks_instead_of_waiting_out_the_clock",
        "tests/test_hls.py::test_a_long_decision_does_not_hold_up_a_neighbours_ready_segment",
        "tests/usecases/test_passport.py::test_origin_never_blocks_past_budget_when_the_reference_hangs",
        "tests/usecases/test_facts.py::test_the_menu_never_waits_longer_than_its_budget",
        "tests/adapters/wiki/test_wiki_blurbs.py::test_the_ratings_dump_is_read_alongside_the_first_request_not_after_it",
        "tests/adapters/wiki/test_http_json_client.py::test_a_memoized_address_rides_over_a_dns_storm",
        "tests/adapters/wiki/test_http_json_client.py::test_a_refusal_by_deadline_takes_its_resolver_thread_with_it",
        "tests/adapters/wiki/test_closed_wave.py::test_the_answer_is_taken_by_the_deadline_and_the_wave_is_closed_after_it",
        "tests/adapters/wiki/test_closed_wave.py::test_the_wave_is_waited_out_as_a_wave_not_as_a_queue",
        "tests/adapters/wiki/test_wiki_spelling.py::test_the_spelling_wave_is_closed_by_the_one_who_raised_it",
        "tests/adapters/wiki/test_wiki_articles.py::test_the_two_step_wave_is_closed_by_the_one_who_raised_it",
        "tests/adapters/wiki/test_wiki_blurbs.py::test_the_batch_wave_is_closed_by_the_one_who_raised_it",
        "tests/adapters/wiki/test_wiki_blurbs.py::test_the_ratings_reader_is_closed_by_the_one_who_raised_it",
        "tests/usecases/test_lookers.py::test_one_key_is_one_thread_no_matter_how_many_ask",
        "tests/usecases/test_lookers.py::test_an_answer_that_missed_its_deadline_is_free_for_the_next_asker",
        "tests/usecases/test_passport.py::test_one_name_is_asked_by_one_thread_no_matter_how_many_ask",
        "tests/usecases/test_passport.py::test_a_slow_map_is_read_by_one_thread_no_matter_how_many_ask",
        "tests/usecases/test_passport_either.py::test_one_name_is_asked_by_one_pair_of_threads_no_matter_how_many_ask",
        "tests/usecases/test_passport_either.py::test_the_second_source_is_asked_by_one_thread_per_entity",
        "tests/usecases/test_facts.py::test_the_deadline_lets_the_menu_go_but_the_topup_thread_is_closed_by_its_owner",
        "tests/adapters/wiki/test_wiki_articles.py::test_a_name_spelled_otherwise_is_answered_within_the_same_budget",
        "tests/usecases/test_passport.py::test_a_slow_offline_map_never_pushes_the_passport_past_the_budget",
        "tests/usecases/test_passport_either.py::test_both_types_together_fit_into_one_budget_not_two",
        "tests/test_cli.py::test_a_neighbour_that_missed_its_budget_is_let_go_too",
        # Дожим хвоста ленты - настоящий фоновый писатель и настоящий файл. Сторож
        # их не видел, пока звали через снесённый фасад (``trace.shutdown``): имя
        # вызова не совпадало с механизмом.
        "tests/adapters/filesystem/trace_journal/test_shutdown.py::test_the_tail_of_the_tape_is_pressed_out_on_a_normal_exit",
        "tests/adapters/filesystem/trace_journal/test_shutdown.py::test_shutting_down_twice_is_not_an_error",
        "tests/test_trace.py::test_records_reads_and_orders",
        "tests/test_trace.py::test_emit_schema",
        "tests/test_trace.py::test_two_show_sessions_are_unambiguously_selected_in_one_log",
        "tests/test_trace.py::test_show_start_prints_effective_thresholds_and_their_sources",
        "tests/test_trace.py::test_bad_field_dropped_not_raised",
        "tests/test_trace.py::test_rotation_drops_old_days",
        "tests/test_trace.py::test_digest_summarises_session",
        "tests/test_trace.py::test_a_dark_screen_and_its_revival_are_records_with_numbers",
        "tests/test_trace.py::test_an_eviction_says_who_was_thrown_out_and_how_much_it_freed",
        "tests/test_trace.py::test_a_piece_laid_off_the_grid_is_a_record_with_numbers",
        "tests/test_trace.py::test_the_share_of_the_warmed_movie_is_a_field",
        "tests/test_trace.py::test_cast_log_shows_the_new_events",
        "tests/test_trace.py::test_doctor_says_whether_the_journal_is_alive",
        "tests/test_trace.py::test_a_served_piece_says_which_producer_made_it",
        "tests/test_trace.py::test_the_plan_says_how_both_producers_encode",
        "tests/test_trace.py::test_cast_log_shows_the_timeline_and_the_query",
        "tests/test_trace.py::test_an_event_this_version_does_not_know_is_printed_anyway",
        "tests/test_anime.py::test_the_catalogue_hole_lands_in_the_weekly_trace",
        "tests/test_anime.py::test_the_gate_costs_no_extra_probe_when_the_top_release_speaks_russian",
        "tests/usecases/test_passport.py::test_the_map_answers_when_wikipedia_misses_the_deadline",
        "tests/test_warm.py::test_a_piece_laid_off_the_grid_never_reaches_the_show",
        "tests/test_ux.py::test_the_spare_release_warms_under_the_menu_not_after_the_first_one_fails",
        "tests/test_ux.py::test_a_dry_run_takes_even_the_chosen_torrent_back",
        "tests/test_ux.py::test_an_instant_answer_is_no_worse_than_before",
        "tests/test_ux.py::test_the_menu_prewarm_stands_aside_while_our_show_is_on_air",
        "tests/test_ux.py::test_prewarmed_torrents_are_dropped_when_the_show_never_starts",
        "tests/test_voices.py::test_a_voice_torrent_is_handed_to_the_show_and_not_pulled_from_under_it",
        "tests/test_play.py::test_a_source_the_receiver_cannot_decode_is_recoded_from_the_first_segment",
        "tests/test_play.py::test_packing_torn_off_again_and_again_is_an_honest_infra_error",
        "tests/test_hls.py::test_segments_are_never_cached_by_the_receiver",
        "tests/test_hls.py::test_cors_is_on_every_answer_including_404_and_preflight",
        "tests/test_hls.py::test_content_types_are_what_the_receiver_expects",
        "tests/test_hls.py::test_segments_answer_range_requests",
        "tests/test_hls.py::test_nothing_but_the_stream_is_reachable",
        "tests/test_hls.py::test_a_stopped_show_stops_answering_even_on_a_live_connection",
        "tests/test_hls.py::test_the_default_transport_is_plain_http_by_ip",
        "tests/test_hls.py::test_https_stays_a_working_but_switched_off_option",
        "tests/test_hls.py::test_the_playback_address_is_our_own_leg_toward_the_tv",
        "tests/test_hls.py::test_a_space_in_the_run_directory_does_not_quietly_kill_the_packing",
        "tests/test_warm.py::test_warming_lays_the_whole_clip_on_disk_and_reports_it",
        "tests/test_warm.py::test_warming_does_not_even_start_a_run_while_the_recoder_works",
        "tests/test_warm.py::test_the_warmed_film_is_homogeneous_and_its_heavy_piece_is_recoded",
        "tests/test_warm.py::test_the_warm_journal_says_whether_it_copies_or_recodes",
        "tests/test_swarm.py::test_run_ffprobe_returns_the_moment_the_probe_exits",
        "tests/test_swarm.py::test_run_ffprobe_bails_at_once_on_a_swarm_declared_dead",
        "tests/test_swarm.py::test_run_ffprobe_keeps_the_full_budget_while_the_stream_is_alive",
        "tests/test_swarm.py::test_swarm_pulse_calls_a_byteless_stream_dead_only_after_the_grace",
        "tests/test_swarm.py::test_swarm_pulse_stays_alive_once_a_byte_arrives",
        "tests/test_swarm.py::test_a_silent_stream_is_dropped_before_the_full_probe_budget",
        "tests/test_swarm.py::test_metadata_are_taken_up_within_a_step_not_within_a_second",
        "tests/test_swarm.py::test_the_poll_never_turns_into_a_flood",
        "tests/test_swarm.py::test_the_metadata_deadline_is_a_deadline",
        "tests/test_swarm.py::test_a_swarm_with_no_contacts_is_called_empty_within_the_grace",
        "tests/test_swarm.py::test_a_slow_but_live_swarm_still_waits_out_the_whole_budget",
        "tests/test_swarm.py::test_silence_about_peers_is_not_silence_of_the_swarm",
        "tests/test_swarm.py::test_a_healthy_release_pays_nothing_for_the_grace",
        "tests/test_swarm.py::test_prewarm_cannot_judge_the_swarm_before_the_release_is_chosen",
        "tests/test_swarm.py::test_a_picture_whose_swarm_never_answers_is_refused_in_seconds_with_a_move",
        "tests/test_swarm.py::test_a_slow_swarm_is_not_mistaken_for_an_empty_one_by_the_pick",
        "tests/test_swarm.py::test_trimming_does_not_hold_up_the_start",
        "tests/test_swarm.py::test_the_grace_a_release_gets_is_the_price_of_dropping_it",
    }
)


_threads_before: set[threading.Thread] = set()


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Запомнить потоки, которые были живы ДО пробы: чужие ей не в укор."""
    global _threads_before
    _threads_before = thread_guard.alive()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Iterator[None]:
    """Поток, переживший пробу, роняет её же, а не соседа (:mod:`tests.thread_guard`).

    Обёрткой, а не обычным хуком: разбирать надо ПОСЛЕ финализаторов фикстур - иначе
    сторож увидит поток, который фикстура как раз собирается закрыть.
    """
    result = yield
    left = thread_guard.leaked(_threads_before)
    if left:
        pytest.fail(thread_guard.complain(item.nodeid, left), pytrace=False)
    return result


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Отделить зависимости от настоящей машины от быстрых тестов с заглушками."""
    ffmpeg = pytest.mark.ffmpeg
    machine = pytest.mark.machine
    for item in items:
        if isinstance(item, pytest.Function) and FFMPEG_FIXTURES.intersection(item.fixturenames):
            item.add_marker(ffmpeg)
        if item.nodeid in MACHINE_TESTS:
            item.add_marker(machine)
        if item.get_closest_marker("machine") or item.get_closest_marker("ffmpeg"):
            continue
        if not isinstance(item, pytest.Function):
            continue
        tree = ast.parse(inspect.getsource(item.function))
        calls = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
        mechanisms = {
            "time.sleep": "стенные часы",
            "socket.socket": "настоящий сокет",
            "socket.socketpair": "настоящий сокет",
            "subprocess.run": "настоящий подпроцесс",
            "subprocess.Popen": "настоящий подпроцесс",
            "threading.Thread": "настоящий поток",
            "shutdown": "настоящий фоновый поток журнала",
        }
        leaked = sorted({label for call, label in mechanisms.items() if call in calls})
        if leaked:
            message = (
                f"{item.nodeid}: быстрый тест использует {', '.join(leaked)}; "
                "возьми маркер `machine`"
            )

            @functools.wraps(item.obj)
            def missing_machine_marker(*, _message: str = message, **_kwargs: object) -> None:
                pytest.fail(_message, pytrace=False)

            # Ошибка коллекции ломает сверку коллекций xdist и маскируется его
            # INTERNALERROR. Обычный красный test item одинаково виден с -n 0
            # и с воркерами; уже найденные фикстуры остаются у исходного item.
            item.obj = missing_machine_marker


def module_of(name: str) -> ModuleType:
    """Модуль по полному имени, а не одноимённая единица из его пакета.

    В пакете упаковщика имя файла - это имя его единицы, и ``film_keys`` значит то модуль,
    то функцию в нём. Подмену для пробы надо ставить туда, откуда её читает сам код, - в
    модуль, поэтому он и спрашивается полным именем, а не выуживается из импорта.
    """
    return importlib.import_module(name)


def free_port() -> int:
    """Свободный порт спрашивается у ядра, а не пишется константой в тесте.

    Раздача поднимается на настоящем сокете, поэтому прибитый номер делает тесты
    взаимно исключающими: два прогона рядом (соседний worktree, повторный запуск того
    же файла) дерутся за bind, и проигравший падает не по делу. ``bind`` на порт 0
    отдаёт номер, который в этот момент свободен, и он же сразу освобождается: сокет
    только привязан, соединений на нём не было, поэтому TIME_WAIT ему не грозит и
    сервер встаёт на то же место.

    Порт спрашивать надо перед самой раздачей, а не заранее и не на весь модуль: между
    ответом ядра и ``listen`` окно всё же есть, и чем оно короче, тем лучше.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(autouse=True)
def _silent_facts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Справка молчит, пока тест не попросит обратного.

    Тесты в сеть не ходят - ни за справкой, ни за чем-либо ещё. Заодно это и есть штатный
    случай «сети нет»: путь добора обязан работать и без справки.
    """
    composition.use_passport(monkeypatch, lambda title, series=False, budget=0.0: Origin())
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))


@pytest.fixture(autouse=True)
def _own_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Конфиг и лента следа - свои на каждый тест, а не хозяйские.

    Унаследованные ``TORRCAST_CONFIG`` и ``TORRCAST_LOG`` увели бы прогон в настоящие файлы
    владельца: конфиг тесты переписывают, а лента копила бы их записи рядом с боевыми.
    Пустая лента - это не «никуда»: путь тогда считается от файла состояния, а он уже
    свой (:func:`torrcast.adapters.filesystem.trace_journal.log_dir`).
    """
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("TORRCAST_LOG", "")
    # Идентификатор сеанса лента заводит лениво и кэширует В ОКРУЖЕНИИ: без своего он
    # утёк бы из теста в тест и подписал бы чужие записи
    # (:func:`torrcast.adapters.filesystem.trace_journal.session_id`).
    monkeypatch.setenv("TORRCAST_SID", tmp_path.name)


@pytest.fixture(autouse=True)
def _pretend_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Под pytest терминала нет, а вопросы проверять надо.

    Без терминала ``ask_line`` штатно берёт дефолт и не спрашивает — это отдельное
    требование, и у него есть свои тесты. Всем остальным нужен обычный «человеческий» pty,
    поэтому по умолчанию притворяемся терминалом, а ``builtins.input`` тесты подменяют
    сами.

    Притворяется вход прогона, а не наша ручка: терминала нет у МАШИНЫ, и врать надо ей.
    Подмени мы ``stdin_is_tty``, она сама выпала бы из прогона целиком - вместе со своим
    разбором закрытого входа, - а тесту досталась бы наша же ложь вместо ответа системы.
    """
    monkeypatch.setattr(sys, "stdin", PretendTty(sys.stdin))


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> CastWorld:
    """Стенд команды показа: внешний мир объектом, а не подменами по месту."""
    stand = CastWorld()
    stand.install(monkeypatch)
    return stand


@pytest.fixture(autouse=True)
def _no_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    """Диагностического пульта (``TORRCAST_CTL``) у теста нет, пока он его не попросит.

    Переменная живёт в окружении прогона, а показ читает её на каждом опросе: чужой
    пульт, забытый в среде, рулил бы показом посреди чужого теста.
    """
    monkeypatch.delenv(CTL_ENV, raising=False)


@pytest.fixture
def remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Файл диагностического пульта: тест пишет в него команду, показ её съедает."""
    path = tmp_path / "ctl"
    monkeypatch.setenv(CTL_ENV, str(path))
    return path


@pytest.fixture(autouse=True, scope="session")
def _wired() -> None:
    """Тесты собирают приложение так же, как боевой запуск: через композиционный корень.

    Без этого след молчал бы (:class:`torrcast.ports.journal.silent.Silent`), и проверки,
    которые читают ленту, доказывали бы не поведение показа, а собственную тишину.
    Каталог ленты у каждого теста свой - его даёт фикстура ``journal``.
    """
    wire()


@pytest.fixture(autouse=True)
def _ports_restored() -> Iterator[None]:
    """Порт - глобальное состояние ПРОЦЕССА: кто поставил своё, тому вернуть чужое.

    Без этого один тест портов гасил ленту всему прогону: :func:`torrcast.ports.journal.
    install` меняет модульную переменную, а не поле объекта, и следующие тесты читали
    молчание вместо своих записей. Ловилось это не всегда - только когда раскладка xdist
    заводила молчание раньше читателей ленты, то есть выглядело плавающим тестом при
    ошибке совершенно определённой. Возврат делает фикстура, а не дисциплина: полагаться
    на то, что каждый автор допишет ``install`` обратно, - значит ждать той же ошибки
    снова.
    """
    saved_journal = journal_slot.journal()
    saved_progress = progress_slot.factory()
    saved_state = state_slot.store()
    saved_unit = unit_slot.unit()
    yield
    journal_slot.install(saved_journal)
    progress_slot.install(saved_progress)
    state_slot.install(saved_state)
    unit_slot.install(saved_unit)


@pytest.fixture(autouse=True)
def show_unit(_ports_restored: None) -> FakeShowUnit:
    """Юнит показа под тестом - подделка, и это не удобство, а запрет.

    Настоящий (:class:`torrcast.adapters.systemd.transient_show_unit.TransientShowUnit`)
    зовёт ``systemctl`` хозяйской машины: спрашивает живой показ, читает journald и гасит
    юнит. Прогон не имеет права этого делать ни разу, поэтому подделка ставится ВСЕМ
    тестам, а не тем, кто про неё вспомнил. По умолчанию не играет ничего; тесту, которому
    нужен идущий показ, достаточно ``show_unit.alive = True``.
    """
    fake = FakeShowUnit()
    unit_slot.install(fake)
    return fake


@pytest.fixture
def tape(_ports_restored: None) -> Tape:
    """Лента под тестом - подделка на порту: зеркало спрашивает, ЧТО рассказал показ.

    Файл ленты тут не заводится вовсе, поэтому фонового писателя ждать не приходится, а
    округление и раскладка полей остаются заботой самой ленты и её зеркал.
    """
    fake = Tape()
    journal_slot.install(fake)
    return fake


@pytest.fixture
def journal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Своя лента следа на один тест: пустой каталог и свой идентификатор сеанса.

    Без неё записи теста уехали бы в настоящую ленту хозяина, а чужие - в проверку.
    Каталог отдельный от ``tmp_path``: тесты кладут туда и свои файлы, а лента обязана
    начинаться пустой.
    """
    path = tmp_path / "trace"
    path.mkdir()
    monkeypatch.setenv(LOG_ENV, str(path))
    monkeypatch.setenv(SID_ENV, "test-sid")
    return path


@pytest.fixture(scope="session")
def tls(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, str]:
    """Self-signed для dev. В бою на это место встанут файлы LE — меняется только путь."""
    directory = tmp_path_factory.mktemp("tls")
    cert, key = directory / "torrcast.crt", directory / "torrcast.key"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
         "-keyout", str(key), "-out", str(cert), "-subj", "/CN=torrcast.example.com",
         "-addext", "basicConstraints=critical,CA:TRUE",
         "-addext", "subjectAltName=DNS:torrcast.example.com,IP:127.0.0.1"],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(cert), str(key)


@pytest.fixture(scope="session")
def clip(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Ролик-источник: H.264 + AC3 5.1 — ровно тот звук, который ресиверу отдавать нельзя."""
    path = tmp_path_factory.mktemp("src") / "clip.mkv"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate={CLIP_RATE}",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", str(CLIP_SECONDS),
         "-c:v", "libx264", "-preset", "ultrafast", "-g", str(CLIP_GOP), "-c:a", "ac3", "-ac", "6",
         "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


@pytest.fixture(scope="session")
def clip_hevc(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Ролик-источник в HEVC — то, чего приёмник не декодирует вовсе.

    Такой файл показ обязан перекодировать ЦЕЛИКОМ
    (:data:`torrcast.domain.probe_settings.RECODE_CODECS`), а не посегментно по весу: смешанный поток
    H.264 и HEVC живой Q70D не доигрывает. Кадр мелкий и ``ultrafast`` — ролик собирается за
    секунды.
    """
    path = tmp_path_factory.mktemp("src-hevc") / "clip.mkv"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc2=size=320x180:rate={CLIP_RATE}",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", str(CLIP_SECONDS),
         "-c:v", "libx265", "-preset", "ultrafast",
         "-x265-params", f"log-level=none:keyint={CLIP_GOP}",
         "-c:a", "ac3", "-ac", "6", "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


@pytest.fixture(scope="session")
def clip_mp4(clip: str, tmp_path_factory: pytest.TempPathFactory) -> str:
    """Тот же ролик в mp4 с ``moov`` в голове — так его пишут релизы для сети (YTS).

    Пересобирается из mkv-ролика копией битстрима: карта опорных кадров обязана получиться
    той же самой, из какого бы контейнера её ни доставали, и тест это проверяет.
    ``-bf 2`` в исходном ролике нет, поэтому ``ctts`` в файле может и не быть — специально
    ради него ниже собирается :func:`clip_mp4_bframes`.
    """
    path = tmp_path_factory.mktemp("src-mp4") / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", clip,
         "-c", "copy", "-movflags", "+faststart", "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


@pytest.fixture(scope="session")
def clip_ts(clip: str, tmp_path_factory: pytest.TempPathFactory) -> str:
    """Тот же ролик в mpegts — единственный контейнер, где ``-ss`` уводит ВПЕРЁД.

    Карты опорных кадров для .ts взять неоткуда, поэтому место захода там меряет пробный
    прогон, и меряет он посадку на СЛЕДУЮЩИЙ опорный кадр
    (:data:`torrcast.domain.warm_open.SEEK_SHIFT`). Ровно так же садится файл, чей индекс
    врёт, - и это тот вход, на котором кусок под именем границы начинался позже неё.
    """
    path = tmp_path_factory.mktemp("src-ts") / "clip.ts"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", clip,
         "-c", "copy", "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


@pytest.fixture(scope="session")
def clip_mp4_tail(clip: str, tmp_path_factory: pytest.TempPathFactory) -> str:
    """Тот же ролик, но ``moov`` в хвосте: так пишет ffmpeg без ``faststart``.

    Такой файл встречается в раздачах, собранных «как получилось», и карта из него обязана
    сниматься тоже — не вычитывая при этом ``mdat`` целиком.
    """
    path = tmp_path_factory.mktemp("src-mp4-tail") / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", clip,
         "-c", "copy", "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


@pytest.fixture(scope="session")
def clip_mp4_bframes(tmp_path_factory: pytest.TempPathFactory) -> str:
    """mp4 с B-кадрами и списком правок: ``ctts`` и ``elst`` не пустые.

    Ровно на этой паре ломаются самодельные разборы: без ``ctts`` время опорного кадра
    получается временем ДЕКОДИРОВАНИЯ, а не тем, что показывает ffprobe и по чему режет
    сегментный муксер; без ``elst`` вся карта уезжает на пару кадров.
    """
    path = tmp_path_factory.mktemp("src-mp4-bf") / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc2=size=320x180:rate={CLIP_RATE}",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", str(CLIP_SECONDS),
         "-c:v", "libx264", "-preset", "ultrafast", "-g", str(CLIP_GOP), "-bf", "3",
         "-c:a", "aac", "-movflags", "+faststart", "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


class FakeProc:
    """Процесс упаковки: умеет ровно то, что от него нужно показу.

    Сигналов остановки у него нет вовсе — попытка придержать упаковку SIGSTOP'ом
    развалила бы тест, а показ таких сигналов больше не шлёт.
    """

    def __init__(self, code: int | None = None) -> None:
        self.code = code

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.code = -15

    def wait(self, timeout: float | None = None) -> int:
        return -15


def fake_packer(
    out: Path,
    first: int = 0,
    code: int | None = None,
    edge: int | None = None,
    run: Path | None = None,
    last: int = -1,
    at: float = 0.0,
    rate: float = 0.0,
    burst: float = 0.0,
    began: float = 0.0,
    kind: type[Packer] | None = None,
) -> Packer:
    """Прогон упаковки без ffmpeg: сегменты в ``out`` кладёт сам тест.

    Каталог прогона (``out/pack``) не создаётся: значит :meth:`Packer.publish` выкладывать
    нечего, и наружу остаётся ровно то, что тест положил своими руками.

    ``edge`` — честный край прогона
    (:attr:`torrcast.adapters.stream_pack.packer.Packer.edge`), то есть
    докуда **этот** прогон выложил. Без ffmpeg двигать его некому, поэтому фикстура спрашивает об
    этом тест. Умолчание — «выложил всё, что лежит в каталоге на момент создания»: так читается
    обычный случай «тест положил куски руками, они и есть работа прогона». Куски, положенные ПОСЛЕ
    создания, краем уже не считаются — ровно этим отличается честный край от глоба каталога, и на
    этом различии держится расчёт запаса показа.

    ``at``/``rate``/``burst``/``began`` — планка чтения ffmpeg (:meth:`Packer.eta`): с
    какой секунды фильма прогон читает вход, в каком темпе, сколько секунд читал на полной
    скорости и когда начался. Умолчание — темпа нет, то есть ждать упаковку не надо
    никогда: так читаются все тесты, где вопрос не про темп.

    ``run`` и ``last`` нужны там, где проверяется сама выкладка: каталог прогона со
    своими кусками и предел захода кодировщика
    (:attr:`torrcast.adapters.stream_pack.packer.Packer.last`).

    ``kind`` - каким прогоном притвориться. Умолчание - настоящий :class:`Packer`; свой
    наследник нужен там, где проверяется поведение показа на прогоне с иным исходом
    (оборванный вход, чужой код возврата), а подменять метод у общего класса нельзя.
    """
    from torrcast.adapters.stream_pack.packer import Packer
    from torrcast.adapters.stream_probe.segment_slot import segment_slot
    from torrcast.domain.hls_settings import PACK_DIR

    if edge is None:
        made = [s for s in (segment_slot(p.name) for p in out.glob("v*.ts")) if s >= first]
        edge = max(made, default=first - 1)
    return (kind or Packer)(
        proc=FakeProc(code),  # type: ignore[arg-type]
        out=out,
        run=out / PACK_DIR if run is None else run,
        first=first,
        edge=edge,
        last=last,
        at=at,
        rate=rate,
        burst=burst,
        began=began or time.monotonic(),
    )
