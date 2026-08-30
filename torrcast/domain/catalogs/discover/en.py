"""Английские надписи кластера поиска."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера поиска."""
    return {
        "discover.indexer_silent": "did not answer",
        "discover.indexer_banned": "unavailable",
        "discover.indexer_one_gone": "indexer {name} {why} - the listing may be worse for it",
        "discover.indexer_many_gone": (
            "indexers dropped out of the catalog: {listed} - the listing may be worse for it"
        ),
        "discover.indexer_one_late": (
            "indexer {name} is still on the way - the listing lacks it for now, it may still arrive"
        ),
        "discover.indexer_many_late": (
            "indexers still on the way: {listed} - the listing lacks them for now, "
            "they may still arrive"
        ),
        "discover.budget_gone": "not doing {what}: the search already spent the goal at {goal}s",
        "discover.budget_gone_anyway": (
            "doing {what} anyway, on its own {seconds}s: the search already spent "
            "the goal at {goal}s"
        ),
        "discover.franchise_more": " and more",
        "discover.franchise_no_number": (
            "“{name}”: pictures in the franchise: {total}, no number {index} - there is: "
            "{have}{more}"
        ),
        "discover.nothing_found": "nothing found for “{name}”",
        "discover.origin_would_be_blind": (
            "original “{alt}” - from the wiki blurb; without it there would be no second request"
        ),
        "discover.origin_instead_of_blind": (
            "original “{alt}” - from the wiki blurb; without it the search would be “{blind}”"
        ),
        "discover.search_phase": "searching “{query}”",
        "discover.relayout_note": "“{query}” is “{swapped}” in Russian layout",
        "discover.search_whole_label": "searching “{query}” whole",
        "discover.whole_number_note": "nothing found for “{name}” - searched “{query}” whole",
        "discover.second_budget_note": (
            "the search already spent the goal at {goal}s - retrying “{name}” anyway: "
            "the picture is searched under both its names"
        ),
        "discover.kin_line": "the catalog has {names} - cast {command}",
        "discover.prowlarr_not_configured": (
            "Prowlarr is not configured: apikey is empty, rerun ./install.sh"
        ),
        "discover.season_not_part": (
            "“{name}” is a series: reading number {index} as a season, not a part"
        ),
        "discover.nothing_parsed": "nothing parsed out for “{name}”",
        "discover.catalog_alias": "“{name}” is “{other}” in the catalog",
        "discover.glued_pictures": "“{also}” and “{title}” are the same picture, {count} releases",
        "discover.no_season_releases": "“{title}”: no releases with season {season}",
        "discover.swarm_counts": "releases in the listing: {total}, touched: {touched}",
        "discover.swarm_later": (
            "name the picture differently or come back later - a different query gathers a "
            "different listing, and the swarm may wake up"
        ),
        "discover.swarm_no_peers": (
            "{counts} - no peers anywhere, nothing to show: {later} ({shown})"
        ),
        "discover.swarm_out_of_time": (
            "{counts} out of {queue_len} queued - these are silent, no time was left for "
            "the rest (touched ones listed up to {peers} seeders), nothing to show: "
            "{later} ({shown})"
        ),
        "discover.swarm_seed_some": " (touched ones listed up to {peers} seeders)",
        "discover.swarm_seed_none": " (touched ones listed no seeders)",
        "discover.swarm_pick_other": "pick another release",
        "discover.swarm_pick_manual": "pick by hand",
        "discover.swarm_untouched_some": (
            "{counts} - these are silent, selection never reached the rest{seed}: {move} - "
            "cast releases <query>, then cast <query> --release N ({shown})"
        ),
        "discover.swarm_all_silent": (
            "{counts} (all) - none answered, though they list seeders (up to {peers}), "
            "nothing to show: {later} ({shown})"
        ),
        "discover.swarm_reason_no_episode": "no matching episode - {count}",
        "discover.swarm_reason_heavy": "heavier than the ceiling - {count}",
        "discover.swarm_untouched_unfit": (
            "{counts} - these are silent, and the rest have nothing playable ({reasons}), "
            "nothing to show: {later} ({shown})"
        ),
        "discover.unfit_none_fit": (
            "no fit release: releases in the listing {total}, selection rejected every one ({why})"
        ),
        "discover.unfit_incomplete_tail": (
            ", but the listing is incomplete - {late} still on the way"
        ),
        "discover.unfit_come_back": (
            "{line}: come back later - a full listing may still turn up a fit rip"
        ),
        "discover.unfit_final": (
            "{line} - the picture exists, but its releases do not fit: name it differently "
            "or come back later - a different query gathers a different listing, and a fit "
            "rip may appear"
        ),
        "discover.gate_other_picture": (
            "for “{name}” the wiki blurb found only a similar name “{other}” - "
            "not chasing someone else's picture"
        ),
        "discover.retry_nothing": "retry for “{alt}” gave nothing",
        "discover.retry_more_pictures": (
            "retry for “{alt}” brought more pictures: {now} instead of {before} - "
            "staying on the “{name}” listing"
        ),
        "discover.retry_no_new_releases": (
            "retry for “{alt}” brought no new releases of the picture"
        ),
        "discover.retry_other_picture": (
            "“{alt}” brought a different picture - staying on the “{name}” listing"
        ),
        "discover.retry_unconfirmed_name": (
            "the name “{alt}” came from the wiki blurb, nothing to check it against"
        ),
        "discover.retry_gain": "releases in Russian: {was} - retried with “{alt}”: now {now}",
        "discover.season_gap": (
            "“{title}” ({year}): releases {count}, but none of them names season {season} - "
            "named: {seasons}"
        ),
    }
