"""Find a release past a torrent boundary without changing the current show."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from torrcast.domain.args import Args
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.slugify import slugify
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.journal.slot import journal
from torrcast.ports.progress.slot import progress as progress_bar
from torrcast.usecases.cast_command._entry_for import _entry_for
from torrcast.usecases.playback.file_picker import file_picker
from torrcast.usecases.rank.pick_voice import pick_voice

if TYPE_CHECKING:
    from torrcast.domain.config import Config
    from torrcast.domain.entry import Entry
    from torrcast.domain.profile import Profile
    from torrcast.ports.torrent_engine import TorrentEngine
    from torrcast.usecases.select.plan import Plan
    from torrcast.usecases.select_bench.bench import Bench


def find_next(
    config: Config,
    key: str,
    torrserver: TorrentEngine,
    profile: Profile,
    entry: Entry,
    target: tuple[int, int],
    circle: Callable[..., list[Plan]],
    stand: Callable[..., Bench],
) -> tuple[Entry, int] | None:
    """Find the named next episode; the caller decides when to replace state."""
    season, (upcoming, episode) = entry.season, target
    assert season is not None
    same = upcoming == season
    words = (entry.query or slugify(entry.title)).replace("-", " ").split()
    args = Args(query=[*words, f"s{upcoming}e{episode}"])
    if not same:
        print(
            phrase("season.searching_next", title=entry.spoken, season=season, upcoming=upcoming),
            flush=True,
        )
    journal().mark("поиск следующего сезона", сезон=upcoming, серия=episode)
    with progress_bar() as progress:
        try:
            plans = circle(config, args, progress, profile)
        except NotFoundError as err:
            word = "season.no_episode_found" if same else "season.no_next_found"
            print(
                phrase(
                    word,
                    title=entry.spoken,
                    season=season,
                    upcoming=upcoming,
                    episode=episode,
                    err=err,
                ),
                flush=True,
            )
            return None
        except TorrcastError as err:
            print(
                phrase("season.search_failed", title=entry.spoken, upcoming=upcoming, err=err),
                flush=True,
            )
            return None
        plan = next((plan for plan in plans if plan.picture.key == key), None)
        if plan is None:
            print(
                phrase(
                    "season.no_episode_found" if same else "season.no_releases_found",
                    title=entry.spoken,
                    season=season,
                    upcoming=upcoming,
                    episode=episode,
                ),
                flush=True,
            )
            return None
        bench = stand(torrserver, choose=file_picker(args), profile=profile)
        try:
            prep = bench.resolve(plan, args, progress)
        except TorrcastError as err:
            bench.drop_all()
            print(
                phrase("season.could_not_start", title=entry.spoken, upcoming=upcoming, err=err),
                flush=True,
            )
            return None
        bench.keep_only(prep)
        audio, voice = pick_voice(
            prep.found, args, entry.voice, plan.picture.native, prep.release.studios
        )
        return (
            _entry_for(
                plan, prep, prep.release, prep.want, prep.found, audio, voice, entry.studio, args
            ),
            prep.number,
        )
