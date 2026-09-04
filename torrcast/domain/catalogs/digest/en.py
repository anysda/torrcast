"""Английские надписи кластера выжимки следа."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера выжимки следа.

    Английский - и умолчание продукта, и запасной каталог: ключа, которого тут нет,
    не существует вовсе, и :func:`torrcast.domain.catalogs.phrase.phrase` на нём падает
    громко, а не отвечает пустотой.
    """
    return {
        # Общее: отметка времени, вес, пустая лента.
        "digest.stamp": "+{at}s ",
        "digest.gb": "{size} GB",
        "digest.no_trace": "no trace - not a single session over the week",
        "digest.phase": "{stamp}phase “{event}”{facts}",
        # Сеанс: ошибка, начало с порогами, потери ленты.
        "digest.error": "{stamp}error: {text}",
        "digest.lost": (
            "{stamp}records lost {count}:"
            " the trace queue overflowed - those decisions are not on the tape"
        ),
        "digest.show_start": "{stamp}playing “{title}” from {pos}",
        "digest.profile": " · profile {profile}",
        "digest.thresholds": "{head}{profile} · thresholds:\n    {details}",
        # Поиск и отбор.
        "digest.indexers": "{stamp}indexers {parts}{tail}",
        "digest.took": " in {secs} s",
        "digest.silent": "; silent {names}",
        "digest.late": "; late {names}",
        "digest.query": "{stamp}query “{query}”{tail}",
        "digest.query_rows": ": rows {raw}",
        "digest.query_pictures": ", pictures {pictures}",
        "digest.select": "{stamp}release taken {release} · {quality} · {track} · ~{mbit} Mbit/s",
        "digest.queue": "{stamp}pool {pool}: queued {queued}, dropped {lost}",
        "digest.runtime": "{stamp}runtime {secs} - {got}",
        "digest.runtime_facts": "from the facts sheet",
        "digest.runtime_guess": "a guess: the facts sheet says nothing",
        "digest.drop": "{stamp}release dropped {release}: {why}",
        "digest.mute": (
            "{stamp}nobody has an English voice track (checked {checked})"
            " - playing release {release}, audio {lang}"
        ),
        "digest.switch": "{stamp}“{frm}” has nothing to play ({why}) - moving to “{to}”",
        # Прогрев.
        "digest.warm_off": (
            "{stamp}warmup is switched off by the setting, so this run will have no warmup events"
        ),
        "digest.evict": "{stamp}the warmup budget evicted “{who}”: {freed} freed for {need}",
        "digest.skew": (
            "{stamp}v{slot} landed off the grid: start {off} s from the boundary {want} - {end}"
        ),
        "digest.skew_hole": "the spot was left cold",
        "digest.skew_redone": "the piece was laid down again",
        "digest.warmed": "{stamp}warmed {secs} of {dur} ({share} %, {size})",
        "digest.warm_stalled": "{head} - warmup stalled: {why}",
        # Показ: куски и план кодирования.
        "digest.plan_copy": "copy",
        "digest.plan_recode": "recode",
        "digest.plan_splice": "splice",
        "digest.plan_shrink": "shrink",
        "digest.src_packed": "live packing",
        "digest.src_warmed": "the warmed piece",
        "digest.src_warmed_copy": "the warmed copy",
        "digest.src_warmed_recode": "the warmed recode",
        "digest.seam": "{stamp}v{slot}: the source changed to {src}",
        "digest.plan_spots": ", spot recode: {named}",
        "digest.plan_spot_count": ", spot recode {count}",
        "digest.plan": "{stamp}pieces: packing - {pack}, warmup - {warm}{tail}",
        # Показ: всё, что мешало играть.
        "digest.buffering": "{stamp}rebuffer at {pos}",
        "digest.freeze": (
            "{stamp}stall at {pos}: {lost} s lost over {secs} s"
            " ({state}, {front} s ready ahead), {total} s over the whole show"
        ),
        "digest.offline_source": "source",
        "digest.offline_net": "network",
        "digest.offline_why": "a break",
        "digest.offline": "{stamp}{head}: {why}",
        "digest.resupply_ok": "the swarm is back",
        "digest.resupply_wait": "the service has not given the swarm back yet",
        "digest.resupply": "{stamp}added the swarm by magnet again - {end}",
        "digest.nudge": (
            "{stamp}watchdog nudge {hit}: {pos} -> {to}"
            " (stuck for {stuck} s, {front} s ready ahead)"
        ),
        "digest.reload_code": ", code {error}",
        "digest.reload_no_code": ", no code",
        "digest.reload": (
            "{stamp}the receiver dropped out at {pos}{error} - LOAD retry {tries}{end}"
        ),
        "digest.reload_failed": " - it did not work out: {why}",
        "digest.refetch_failed": " - it did not work out: {why}",
        "digest.why_unnamed": "the reason was not named",
        "digest.refetch": "{stamp}piece refetch at {pos} (attempt {tries}){end}",
        "digest.dark_at": "the show went dark at {pos}",
        "digest.dark_blank": "the show gave no frame at all",
        "digest.dark_why": "the receiver dropped the show",
        "digest.dark": "{stamp}{head}: {why}",
        "digest.revive_ok": "the show was raised",
        "digest.revive_failed": "the receiver did not take the show",
        "digest.revive": "{stamp}{took} from {pos} (attempt {tries}, {waited} s of darkness)",
        "digest.seek_shown": " picture after {wait} s",
        "digest.seek_blank": " no picture ever came: {why}",
        "digest.seek": "{stamp}seek {frm} -> {to},{back}",
        # Блок сеанса: шапка и итоговая строка.
        "digest.session_head": "session {sid} · {clock}",
        "digest.session_title": " · “{title}”",
        "digest.phase_total": ", {count} in all",
        "digest.total": "total: rebuffers {count}",
        "digest.total_seams": ", source seams {count}",
        "digest.total_shrunk": (
            ", shrinks {shrunk}, shrunk splice: attempts {tried}, wins {won}, not tried {skipped}"
        ),
        "digest.watched": "watched to the end",
        "digest.stopped_at": "stopped at {where}",
        "digest.end_of": " of {dur}",
        # Счётчики итоговой строки: слово на событие.
        "digest.count_buffering": "rebuffers",
        "digest.count_offline": "network breaks",
        "digest.count_resupply": "swarm re-adds by magnet",
        "digest.count_dark": "show blackouts",
        "digest.count_revive": "show revivals",
        "digest.count_nudge": "watchdog nudges",
        "digest.count_reload": "LOAD retries",
        "digest.count_refetch": "piece refetches",
        "digest.count_seek": "seeks",
        "digest.count_evict": "warmup evictions",
        "digest.count_skew": "pieces off the grid",
    }
