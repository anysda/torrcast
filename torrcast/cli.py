"""Командная строка torrcast и совместимый фасад её предметных частей.

Точка входа намеренно остаётся здесь. Имена прежнего монолита также доступны
отсюда: ими пользуются тесты и внешние диагностические сценарии.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from torrcast import choice as _choice_module
from torrcast import commands as _commands_module
from torrcast import discovery as _discovery_module
from torrcast import play_command as _play_command_module
from torrcast import playback as _playback_module
from torrcast import ranking as _ranking_module
from torrcast import reinforce as _reinforce_module
from torrcast import selection as _selection_module
from torrcast.choice import (
    _BLURB_INDENT as _BLURB_INDENT,
)
from torrcast.choice import (
    Config as Config,
)
from torrcast.choice import (
    Fact as Fact,
)
from torrcast.choice import (
    Facts as Facts,
)
from torrcast.choice import (
    Origin as Origin,
)
from torrcast.choice import (
    Picture as Picture,
)
from torrcast.choice import (
    Profile as Profile,
)
from torrcast.choice import (
    Progress as Progress,
)
from torrcast.choice import (
    Protocol as Protocol,
)
from torrcast.choice import (
    Receiver as Receiver,
)
from torrcast.choice import (
    _ctl as _ctl,
)
from torrcast.choice import (
    _first_alive as _first_alive,
)
from torrcast.choice import (
    _is_default as _is_default,
)
from torrcast.choice import (
    _named as _named,
)
from torrcast.choice import (
    _namesake as _namesake,
)
from torrcast.choice import (
    _passed_why as _passed_why,
)
from torrcast.choice import (
    _Passport as _Passport,
)
from torrcast.choice import (
    _passport as _passport,
)
from torrcast.choice import (
    _pick_plan as _pick_plan,
)
from torrcast.choice import (
    _played as _played,
)
from torrcast.choice import (
    _Revivable as _Revivable,
)
from torrcast.choice import (
    _rival as _rival,
)
from torrcast.choice import (
    _same_name as _same_name,
)
from torrcast.choice import (
    _Steerable as _Steerable,
)
from torrcast.choice import (
    _why_refused as _why_refused,
)
from torrcast.choice import (
    alive_numbers as alive_numbers,
)
from torrcast.choice import (
    asked_kind as asked_kind,
)
from torrcast.choice import (
    backed as backed,
)
from torrcast.choice import (
    console as console,
)
from torrcast.choice import (
    contextlib as contextlib,
)
from torrcast.choice import (
    default_line as default_line,
)
from torrcast.choice import (
    default_note as default_note,
)
from torrcast.choice import (
    first_alive as first_alive,
)
from torrcast.choice import (
    fitness as fitness,
)
from torrcast.choice import (
    franchise_key as franchise_key,
)
from torrcast.choice import (
    last_hope_note as last_hope_note,
)
from torrcast.choice import (
    liveliest as liveliest,
)
from torrcast.choice import (
    liveliness as liveliness,
)
from torrcast.choice import (
    menu_lines as menu_lines,
)
from torrcast.choice import (
    namesake_note as namesake_note,
)
from torrcast.choice import (
    origin as origin,
)
from torrcast.choice import (
    os as os,
)
from torrcast.choice import (
    outside_numbering as outside_numbering,
)
from torrcast.choice import (
    part_one_swap as part_one_swap,
)
from torrcast.choice import (
    playable as playable,
)
from torrcast.choice import (
    runtime_checkable as runtime_checkable,
)
from torrcast.choice import (
    shorten as shorten,
)
from torrcast.choice import (
    shutil as shutil,
)
from torrcast.choice import (
    slugify as slugify,
)
from torrcast.choice import (
    split_franchise_index as split_franchise_index,
)
from torrcast.choice import (
    swap_note as swap_note,
)
from torrcast.choice import (
    textwrap as textwrap,
)
from torrcast.choice import (
    threading as threading,
)
from torrcast.choice import (
    trace as trace,
)
from torrcast.choice import (
    understudy as understudy,
)
from torrcast.choice import (
    understudy_note as understudy_note,
)
from torrcast.choice import (
    warm_order as warm_order,
)
from torrcast.choice import (
    warned as warned,
)
from torrcast.choice import (
    year_note as year_note,
)
from torrcast.commands import (
    _BTIH as _BTIH,
)
from torrcast.commands import (
    _DISC_RE as _DISC_RE,
)
from torrcast.commands import (
    ALIVE_SEEDERS as ALIVE_SEEDERS,
)
from torrcast.commands import (
    CTL_ENV as CTL_ENV,
)
from torrcast.commands import (
    EXIT_INFRA as EXIT_INFRA,
)
from torrcast.commands import (
    EXIT_NOT_FOUND as EXIT_NOT_FOUND,
)
from torrcast.commands import (
    EXIT_OK as EXIT_OK,
)
from torrcast.commands import (
    EXTRAS_MBIT as EXTRAS_MBIT,
)
from torrcast.commands import (
    FULL_HD_LIVENESS as FULL_HD_LIVENESS,
)
from torrcast.commands import (
    FULL_HEIGHT as FULL_HEIGHT,
)
from torrcast.commands import (
    GATE_LIVENESS as GATE_LIVENESS,
)
from torrcast.commands import (
    HD_HEIGHT as HD_HEIGHT,
)
from torrcast.commands import (
    HONEST_BUDGET as HONEST_BUDGET,
)
from torrcast.commands import (
    HONEST_RATIO as HONEST_RATIO,
)
from torrcast.commands import (
    KEYS_WAIT as KEYS_WAIT,
)
from torrcast.commands import (
    MAX_LIVE as MAX_LIVE,
)
from torrcast.commands import (
    MAX_TRIES as MAX_TRIES,
)
from torrcast.commands import (
    PAUSE_LIMIT as PAUSE_LIMIT,
)
from torrcast.commands import (
    PAUSE_SECONDS as PAUSE_SECONDS,
)
from torrcast.commands import (
    PEER_GRACE as PEER_GRACE,
)
from torrcast.commands import (
    PICK_BUDGET as PICK_BUDGET,
)
from torrcast.commands import (
    PILOT_TIMEOUT as PILOT_TIMEOUT,
)
from torrcast.commands import (
    PREWARM as PREWARM,
)
from torrcast.commands import (
    PREWARM_DUB as PREWARM_DUB,
)
from torrcast.commands import (
    PREWARM_SPARE as PREWARM_SPARE,
)
from torrcast.commands import (
    PROBE_TIMEOUT as PROBE_TIMEOUT,
)
from torrcast.commands import (
    SAY_SECONDS as SAY_SECONDS,
)
from torrcast.commands import (
    SD_BITRATE as SD_BITRATE,
)
from torrcast.commands import (
    SEASON_EPISODES as SEASON_EPISODES,
)
from torrcast.commands import (
    SOUND_LIVENESS as SOUND_LIVENESS,
)
from torrcast.commands import (
    SOURCE_PAUSE as SOURCE_PAUSE,
)
from torrcast.commands import (
    SOURCE_TRIES as SOURCE_TRIES,
)
from torrcast.commands import (
    START_SLACK as START_SLACK,
)
from torrcast.commands import (
    STEP_GRACE as STEP_GRACE,
)
from torrcast.commands import (
    SWARM_GRACE as SWARM_GRACE,
)
from torrcast.commands import (
    TRACE_ENV as TRACE_ENV,
)
from torrcast.commands import (
    TV_MENU as TV_MENU,
)
from torrcast.commands import (
    VERDICT_BUDGET as VERDICT_BUDGET,
)
from torrcast.commands import (
    VOICE_MENU as VOICE_MENU,
)
from torrcast.commands import (
    WARMED_RATIO as WARMED_RATIO,
)
from torrcast.commands import (
    WATCH_SECONDS as WATCH_SECONDS,
)
from torrcast.commands import (
    WORKER_DUR as WORKER_DUR,
)
from torrcast.commands import (
    WORKER_META as WORKER_META,
)
from torrcast.commands import (
    Args as Args,
)
from torrcast.commands import (
    Device as Device,
)
from torrcast.commands import (
    Watch as Watch,
)
from torrcast.commands import (
    __version__ as __version__,
)
from torrcast.commands import (
    _cache_reserve as _cache_reserve,
)
from torrcast.commands import (
    _Clock as _Clock,
)
from torrcast.commands import (
    _cmd_configure as _cmd_configure,
)
from torrcast.commands import (
    _cmd_doctor as _cmd_doctor,
)
from torrcast.commands import (
    _cmd_log as _cmd_log,
)
from torrcast.commands import (
    _cmd_releases as _cmd_releases,
)
from torrcast.commands import (
    _cmd_status as _cmd_status,
)
from torrcast.commands import (
    _cmd_stop as _cmd_stop,
)
from torrcast.commands import (
    _cmd_voices as _cmd_voices,
)
from torrcast.commands import (
    _cmd_worker as _cmd_worker,
)
from torrcast.commands import (
    _darkness as _darkness,
)
from torrcast.commands import (
    _duration as _duration,
)
from torrcast.commands import (
    _following as _following,
)
from torrcast.commands import (
    _held_by_show as _held_by_show,
)
from torrcast.commands import (
    _on_term as _on_term,
)
from torrcast.commands import (
    _own_torrent as _own_torrent,
)
from torrcast.commands import (
    _release_orphans as _release_orphans,
)
from torrcast.commands import (
    _release_torrents as _release_torrents,
)
from torrcast.commands import (
    _say_showing as _say_showing,
)
from torrcast.commands import (
    _shown as _shown,
)
from torrcast.commands import (
    _since_seconds as _since_seconds,
)
from torrcast.commands import (
    _Stopped as _Stopped,
)
from torrcast.commands import (
    _torrent_hash as _torrent_hash,
)
from torrcast.commands import (
    _worker_loop as _worker_loop,
)
from torrcast.commands import (
    argparse as argparse,
)
from torrcast.commands import (
    found_tv as found_tv,
)
from torrcast.commands import (
    io as io,
)
from torrcast.commands import main as main
from torrcast.commands import (
    parse_args as parse_args,
)
from torrcast.commands import (
    partial as partial,
)
from torrcast.commands import (
    save_config as save_config,
)
from torrcast.commands import (
    scan as scan,
)
from torrcast.commands import (
    signal as signal,
)
from torrcast.commands import (
    split_episode as split_episode,
)
from torrcast.commands import (
    terminal as terminal,
)
from torrcast.commands import (
    tv_lines as tv_lines,
)
from torrcast.commands import (
    unit_key as unit_key,
)
from torrcast.discovery import (
    CIRCLE_SHARE as CIRCLE_SHARE,
)
from torrcast.discovery import (
    FACTS_BUDGET as FACTS_BUDGET,
)
from torrcast.discovery import (
    GOAL as GOAL,
)
from torrcast.discovery import (
    KIN_SHOWN as KIN_SHOWN,
)
from torrcast.discovery import (
    SECOND_LEAST as SECOND_LEAST,
)
from torrcast.discovery import (
    _ask as _ask,
)
from torrcast.discovery import (
    _asked_kind as _asked_kind,
)
from torrcast.discovery import (
    _kin as _kin,
)
from torrcast.discovery import (
    _no_budget as _no_budget,
)
from torrcast.discovery import (
    _nothing as _nothing,
)
from torrcast.discovery import (
    _query_note as _query_note,
)
from torrcast.discovery import (
    _search as _search,
)
from torrcast.discovery import (
    _second_language as _second_language,
)
from torrcast.discovery import (
    _vouched as _vouched,
)
from torrcast.discovery import (
    kin_line as kin_line,
)
from torrcast.discovery import (
    other_words as other_words,
)
from torrcast.discovery import (
    season_gaps as season_gaps,
)
from torrcast.discovery import (
    silent_swarm as silent_swarm,
)
from torrcast.discovery import (
    unfit_line as unfit_line,
)
from torrcast.discovery import (
    unfit_pool as unfit_pool,
)
from torrcast.discovery import (
    worth_asking_original as worth_asking_original,
)
from torrcast.play_command import (
    _cmd_play as _cmd_play,
)
from torrcast.play_command import (
    _forget_progress as _forget_progress,
)
from torrcast.play_command import (
    _relayout as _relayout,
)
from torrcast.play_command import (
    _season_asked as _season_asked,
)
from torrcast.play_command import (
    _titled_number as _titled_number,
)
from torrcast.play_command import (
    load_config as load_config,
)
from torrcast.play_command import (
    tune_profile as tune_profile,
)
from torrcast.playback import (
    CAUTIOUS as CAUTIOUS,
)
from torrcast.playback import (
    CLOCK as CLOCK,
)
from torrcast.playback import (
    REVIVE_DROP as REVIVE_DROP,
)
from torrcast.playback import (
    REVIVE_LIMIT as REVIVE_LIMIT,
)
from torrcast.playback import (
    REVIVE_LIVED as REVIVE_LIVED,
)
from torrcast.playback import (
    REVIVE_PAUSE as REVIVE_PAUSE,
)
from torrcast.playback import (
    REVIVE_TRIES as REVIVE_TRIES,
)
from torrcast.playback import (
    START_BUDGET as START_BUDGET,
)
from torrcast.playback import (
    VIDEO_EXT as VIDEO_EXT,
)
from torrcast.playback import (
    WATCHED_RATIO as WATCHED_RATIO,
)
from torrcast.playback import (
    Callable as Callable,
)
from torrcast.playback import (
    ChromecastReceiver as ChromecastReceiver,
)
from torrcast.playback import (
    Clock as Clock,
)
from torrcast.playback import (
    Encode as Encode,
)
from torrcast.playback import (
    Entry as Entry,
)
from torrcast.playback import (
    Feed as Feed,
)
from torrcast.playback import (
    Grid as Grid,
)
from torrcast.playback import (
    HlsServer as HlsServer,
)
from torrcast.playback import (
    NoReturn as NoReturn,
)
from torrcast.playback import (
    Recoder as Recoder,
)
from torrcast.playback import (
    State as State,
)
from torrcast.playback import (
    Supply as Supply,
)
from torrcast.playback import (
    TorrcastError as TorrcastError,
)
from torrcast.playback import (
    TorrServer as TorrServer,
)
from torrcast.playback import (
    Vault as Vault,
)
from torrcast.playback import (
    Warmer as Warmer,
)
from torrcast.playback import (
    _asked as _asked,
)
from torrcast.playback import (
    _await_playing as _await_playing,
)
from torrcast.playback import (
    _blame_the_end as _blame_the_end,
)
from torrcast.playback import (
    _blamed as _blamed,
)
from torrcast.playback import (
    _default_file as _default_file,
)
from torrcast.playback import (
    _encode_all as _encode_all,
)
from torrcast.playback import (
    _file_picker as _file_picker,
)
from torrcast.playback import (
    _handover as _handover,
)
from torrcast.playback import (
    _hold as _hold,
)
from torrcast.playback import (
    _launch as _launch,
)
from torrcast.playback import (
    _layout as _layout,
)
from torrcast.playback import (
    _next_warmer as _next_warmer,
)
from torrcast.playback import (
    _play as _play,
)
from torrcast.playback import (
    _recoder as _recoder,
)
from torrcast.playback import (
    _refuse_hopeless as _refuse_hopeless,
)
from torrcast.playback import (
    _Resume as _Resume,
)
from torrcast.playback import (
    _resume as _resume,
)
from torrcast.playback import (
    _Revival as _Revival,
)
from torrcast.playback import (
    _warmer as _warmer,
)
from torrcast.playback import (
    ask_line as ask_line,
)
from torrcast.playback import (
    codec_name as codec_name,
)
from torrcast.playback import (
    dataclass as dataclass,
)
from torrcast.playback import (
    detect_profile as detect_profile,
)
from torrcast.playback import (
    forget_playing as forget_playing,
)
from torrcast.playback import (
    hls_base as hls_base,
)
from torrcast.playback import (
    make_receiver as make_receiver,
)
from torrcast.playback import (
    mark as mark,
)
from torrcast.playback import (
    mark_playing as mark_playing,
)
from torrcast.playback import (
    pick_video_file as pick_video_file,
)
from torrcast.playback import (
    playing_flag as playing_flag,
)
from torrcast.playback import (
    probe as probe,
)
from torrcast.playback import (
    recode_note as recode_note,
)
from torrcast.playback import (
    recodes_whole as recodes_whole,
)
from torrcast.playback import (
    start_play_unit as start_play_unit,
)
from torrcast.playback import (
    stop_play_unit as stop_play_unit,
)
from torrcast.playback import (
    time as time,
)
from torrcast.playback import (
    unit_active as unit_active,
)
from torrcast.playback import (
    unit_why as unit_why,
)
from torrcast.playback import (
    warm_file as warm_file,
)
from torrcast.playback import (
    warm_key as warm_key,
)
from torrcast.playback import (
    warm_root as warm_root,
)
from torrcast.playback import (
    whole_encode as whole_encode,
)
from torrcast.playback import (
    why as why,
)
from torrcast.ranking import (
    _AUDIO_FILE_EXT as _AUDIO_FILE_EXT,
)
from torrcast.ranking import (
    _CODEC as _CODEC,
)
from torrcast.ranking import (
    _DISC as _DISC,
)
from torrcast.ranking import (
    _EXTRAS as _EXTRAS,
)
from torrcast.ranking import (
    _HEAVY as _HEAVY,
)
from torrcast.ranking import (
    _HEVC as _HEVC,
)
from torrcast.ranking import (
    _NO_EPISODE as _NO_EPISODE,
)
from torrcast.ranking import (
    _PINNED as _PINNED,
)
from torrcast.ranking import (
    _QUIET as _QUIET,
)
from torrcast.ranking import (
    _RU_FILE_RE as _RU_FILE_RE,
)
from torrcast.ranking import (
    _SMALL as _SMALL,
)
from torrcast.ranking import (
    _SOURCE as _SOURCE,
)
from torrcast.ranking import (
    _SPOKEN as _SPOKEN,
)
from torrcast.ranking import (
    OFF_SEASON as OFF_SEASON,
)
from torrcast.ranking import (
    RECODE_HEIGHT as RECODE_HEIGHT,
)
from torrcast.ranking import (
    STEP_RATIO as STEP_RATIO,
)
from torrcast.ranking import (
    TABLE_LIMIT as TABLE_LIMIT,
)
from torrcast.ranking import (
    AudioTrack as AudioTrack,
)
from torrcast.ranking import (
    Episode as Episode,
)
from torrcast.ranking import (
    Final as Final,
)
from torrcast.ranking import (
    InfraError as InfraError,
)
from torrcast.ranking import (
    Media as Media,
)
from torrcast.ranking import (
    NotFoundError as NotFoundError,
)
from torrcast.ranking import (
    Path as Path,
)
from torrcast.ranking import (
    Release as Release,
)
from torrcast.ranking import (
    Sequence as Sequence,
)
from torrcast.ranking import (
    TorrFile as TorrFile,
)
from torrcast.ranking import (
    _ask_voice as _ask_voice,
)
from torrcast.ranking import (
    _cut as _cut,
)
from torrcast.ranking import (
    _gb as _gb,
)
from torrcast.ranking import _hms as _hms
from torrcast.ranking import (
    _pad as _pad,
)
from torrcast.ranking import (
    _russian_audio_file as _russian_audio_file,
)
from torrcast.ranking import (
    _voice_number as _voice_number,
)
from torrcast.ranking import (
    ask as ask,
)
from torrcast.ranking import (
    bitrate_mbit as bitrate_mbit,
)
from torrcast.ranking import (
    bitrate_of as bitrate_of,
)
from torrcast.ranking import (
    drop_reason as drop_reason,
)
from torrcast.ranking import (
    gate_open as gate_open,
)
from torrcast.ranking import (
    heard as heard,
)
from torrcast.ranking import (
    hevc_hope as hevc_hope,
)
from torrcast.ranking import (
    honest_shot as honest_shot,
)
from torrcast.ranking import (
    is_candidate as is_candidate,
)
from torrcast.ranking import (
    is_dated as is_dated,
)
from torrcast.ranking import (
    is_dead as is_dead,
)
from torrcast.ranking import (
    is_disc as is_disc,
)
from torrcast.ranking import (
    is_extra as is_extra,
)
from torrcast.ranking import (
    is_full_hd as is_full_hd,
)
from torrcast.ranking import (
    last_hope as last_hope,
)
from torrcast.ranking import (
    misses_episode as misses_episode,
)
from torrcast.ranking import (
    needs_whole_recode as needs_whole_recode,
)
from torrcast.ranking import (
    over_ceiling as over_ceiling,
)
from torrcast.ranking import (
    pack_mbit as pack_mbit,
)
from torrcast.ranking import (
    peer_grace as peer_grace,
)
from torrcast.ranking import (
    pick_voice as pick_voice,
)
from torrcast.ranking import (
    promises_more as promises_more,
)
from torrcast.ranking import (
    quality_text as quality_text,
)
from torrcast.ranking import (
    queue_drops as queue_drops,
)
from torrcast.ranking import (
    rank_releases as rank_releases,
)
from torrcast.ranking import (
    re as re,
)
from torrcast.ranking import (
    render_table as render_table,
)
from torrcast.ranking import (
    sound_note as sound_note,
)
from torrcast.ranking import (
    sound_step as sound_step,
)
from torrcast.ranking import (
    spoken as spoken,
)
from torrcast.ranking import (
    stepdown_note as stepdown_note,
)
from torrcast.ranking import (
    understated as understated,
)
from torrcast.ranking import (
    voice_note as voice_note,
)
from torrcast.ranking import (
    voice_unproven as voice_unproven,
)
from torrcast.ranking import (
    voices_table as voices_table,
)
from torrcast.reinforce import (
    Prowlarr as Prowlarr,
)
from torrcast.reinforce import (
    _as_is as _as_is,
)
from torrcast.reinforce import (
    _ceiling_hides_name as _ceiling_hides_name,
)
from torrcast.reinforce import (
    _ceiling_reinforce as _ceiling_reinforce,
)
from torrcast.reinforce import (
    _foreign_note as _foreign_note,
)
from torrcast.reinforce import (
    _lacks_season as _lacks_season,
)
from torrcast.reinforce import (
    _leading as _leading,
)
from torrcast.reinforce import (
    _plan_for as _plan_for,
)
from torrcast.reinforce import (
    _season_reinforce as _season_reinforce,
)
from torrcast.reinforce import (
    _timed as _timed,
)
from torrcast.reinforce import (
    _topup as _topup,
)
from torrcast.reinforce import (
    _twin as _twin,
)
from torrcast.reinforce import (
    _voice_reinforce as _voice_reinforce,
)
from torrcast.reinforce import (
    catalog_has_name as catalog_has_name,
)
from torrcast.reinforce import (
    menu_order as menu_order,
)
from torrcast.reinforce import (
    merge as merge,
)
from torrcast.reinforce import (
    minutes_of as minutes_of,
)
from torrcast.reinforce import (
    replace as replace,
)
from torrcast.reinforce import (
    same_name as same_name,
)
from torrcast.reinforce import (
    same_picture as same_picture,
)
from torrcast.reinforce import (
    to_releases as to_releases,
)
from torrcast.reinforce import (
    transliterate as transliterate,
)
from torrcast.reinforce import (
    voiceless_pool as voiceless_pool,
)
from torrcast.selection import (
    COPY as COPY,
)
from torrcast.selection import (
    META_BUDGET as META_BUDGET,
)
from torrcast.selection import (
    PROBE_BUDGET as PROBE_BUDGET,
)
from torrcast.selection import (
    REFUSE as REFUSE,
)
from torrcast.selection import (
    ContactWait as ContactWait,
)
from torrcast.selection import (
    EpisodeFile as EpisodeFile,
)
from torrcast.selection import (
    RawResult as RawResult,
)
from torrcast.selection import (
    ServerDownError as ServerDownError,
)
from torrcast.selection import (
    SwarmError as SwarmError,
)
from torrcast.selection import (
    _about as _about,
)
from torrcast.selection import (
    _Bench as _Bench,
)
from torrcast.selection import (
    _continue as _continue,
)
from torrcast.selection import (
    _did_not_answer as _did_not_answer,
)
from torrcast.selection import (
    _nothing_late as _nothing_late,
)
from torrcast.selection import (
    _Plan as _Plan,
)
from torrcast.selection import (
    _Prep as _Prep,
)
from torrcast.selection import (
    _remembered as _remembered,
)
from torrcast.selection import (
    _revoice as _revoice,
)
from torrcast.selection import (
    _Series as _Series,
)
from torrcast.selection import (
    _silenced as _silenced,
)
from torrcast.selection import (
    _turned_down as _turned_down,
)
from torrcast.selection import (
    _Voiced as _Voiced,
)
from torrcast.selection import (
    _voiced as _voiced,
)
from torrcast.selection import (
    _waiting_note as _waiting_note,
)
from torrcast.selection import (
    field as field,
)
from torrcast.selection import (
    map_episodes as map_episodes,
)
from torrcast.selection import (
    swarm_pulse as swarm_pulse,
)

_PARTS = (
    _commands_module,
    _play_command_module,
    _discovery_module,
    _reinforce_module,
    _selection_module,
    _playback_module,
    _choice_module,
    _ranking_module,
)

# Функции в перенесённых частях разрешают глобальные имена в своём модуле.
# Доводим до каждой части полный namespace после завершения цепочки импортов.
_namespace: dict[str, Any] = {}
for _part in _PARTS:
    _namespace.update(
        (name, value)
        for name, value in vars(_part).items()
        if not name.startswith("__")
    )
globals().update(_namespace)
for _part in _PARTS:
    vars(_part).update(_namespace)


class _CliModule(ModuleType):
    """Передаёт тестовые/диагностические подмены в модули реализации."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if not name.startswith("__"):
            for part in _PARTS:
                if name in vars(part):
                    setattr(part, name, value)


sys.modules[__name__].__class__ = _CliModule

__all__ = [name for name in globals() if not name.startswith("_")]


if __name__ == "__main__":
    raise SystemExit(main())
