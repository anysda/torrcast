[日本語](README-jp.md) | [Español](README-es.md) | [Русский](README-ru.md)

# torrcast

`cast` is a command-line tool that finds a movie, series or anime by name and plays it on
your TV - with no cloud in the data path and no clicking through torrents. The stream goes
from the swarm to your computer and from there to the TV over the route the TV sees you
on, with no third-party server in between.

The movie is cached on disk only while you watch it. During playback, torrcast downloads
and, where necessary, transcodes the whole movie in the background. Once warming is
complete, the rest plays without internet access, including seeks and without buffering.
The cache is removed after playback. There is no media library or download queue: the
disk holds exactly what is playing, and only while it is playing.

The idea is simple: **ask for something and it starts playing**. One command, one
question - often none - and then a picture on the screen. No release selection, download
queue, or audio-track housekeeping.

The second principle is **smooth playback over peak sharpness**. Playback must not
buffer. If a release is too heavy for the receiver, torrcast transcodes it on the fly
and says so. Quality is reduced only as a last resort and only as much as necessary.

There are no silent substitutions. Every automatic decision gets one honest line, for
example: `release 1 actually 574p - taking 2 (actually 1080p)`, `attention: ~36 Mbit/s -
heavy chunks get recoded on the fly`, or `video hevc - recoding it whole on the fly`.

## Installation

```sh
curl -fsSL https://torrcast.anysda.space | sh
```

A bare Debian 12 installation does **not** include `curl`; install it first. The
bootstrap requires `curl`, `tar`, `sha256sum`, and `bash`. The one-liner asks GitLab for
the latest version, downloads that exact release tarball, verifies its SHA-256 checksum,
and runs the `install.sh` inside it. When not run as root, the bootstrap restarts itself
through `sudo`; where there is no `sudo`, it stops and prints the exact command to run as
root.

The endpoint names the language of the product it installs.
`https://torrcast.anysda.space` installs an English `cast`: menus, messages and the voice
track it looks for are all English. `https://rutorrcast.anysda.space` installs the same
release with Russian as the product language. Either way the choice is not final:
`cast --en` and `cast --ru` switch the installed copy at any time.

From source:

```sh
git clone https://gitlab.anysda.space/anysda/torrcast && cd torrcast
sudo ./install.sh
```

`sudo ./install.sh -en` and `sudo ./install.sh -ru` name the language by hand: the key
sets both the installer's own output and the `language` field of the configuration. With
no key, a fresh installation stores English, and a repeat installation keeps the language
that is already in the configuration.

Installation discovers receivers through mDNS and by scanning local subnets on port
8009. One receiver is saved automatically. If several are found, the installer lists
their names and addresses and continues without choosing. Save an address directly with
`cast --tv <ip>`, or use `cast --tv` and choose a number.

The final screen of the installer speaks about the receiver itself. The saved one is named
by name and address, or by address alone when the device announced no name, as well as on a
repeat installation, where the configuration holds an address only. Of several found ones it
lists as many as fit under the command list and counts the rest: "and 2 more". An empty
search is not left in silence: the screen says to turn the TV on and names `cast --tv`; on a
narrow terminal the wording shrinks, but the command never drops out of it. A mock stand is
named as such: it casts nowhere. The same screen names the door to the other language -
`cast --ru` after an English installation.

`install.sh` is idempotent: running it again updates only what changed. No registration
or external API keys are required: Prowlarr generates its own API key, and installation
reads it out and stores it in the torrcast configuration. The indexers it configures need
no account, no captcha and no key: Knaben, RuTor, Nyaa.si and YTS are reached directly,
and two small local read-only adapters, installed alongside torrcast and listening on
localhost only, add AniLibria (anime with a Russian voice) and JacRed (an open catalog of
Russian releases and voices). If a provider blocks an indexer by name, installation sets
up a local bypass and says whether the name answers through it.

TorrServer and Prowlarr are pinned to versions tested with the rest of the system. Both
pins are in the settings block at the top of `install.sh`. If the pinned Prowlarr release
is gone from GitHub, installation says so and takes the latest instead. TorrServer is
never substituted: when its pinned build is missing, an already installed binary stays and
installation says so, and on a machine without one installation stops.

The package phase ends with a check. The script compares every file of the installed
package with the sources next to `install.sh` and prints a line like `venv vs repository
check: N files match (sha256 ...)`. A mismatch names the files that differ and fails
instead of reporting success.

The package lives in `/opt/torrcast/venv`; `/usr/local/bin/cast` is a symlink to
`/opt/torrcast/venv/bin/cast`.

## Requirements

- Linux with systemd: Debian 12 or newer, or Ubuntu with Python 3.11 or newer available
  from the system package manager. Installation uses `apt`.
- Python 3.11 or newer. `install.sh` takes the freshest of `python3.13`, `python3.12`,
  `python3.11`; `TORRCAST_PYTHON` names an interpreter by hand.
- `ffmpeg` 6.1 or newer: `-readrate_initial_burst` is required. If the system version is
  older, is confined to a snap, or fails an MPEG-TS smoke test, `install.sh` puts a static
  build in `/usr/local/bin`.
- Root privileges for installation of systemd units, packages, and directories under
  `/opt`, `/etc`, and `/var/lib`.
- Memory. Measurements are taken on an 8 GiB machine; a smaller one works with a smaller
  cache. The live HLS segment window sits in `/dev/shm`, next to two ffmpeg processes, so
  when the torrent cache goes to memory, installation subtracts 1.75 GiB for the system,
  the player and those processes before sizing it. That cache is what protects playback
  from an internet outage, and it is placed where more of it fits: normally on disk, or in
  memory on a machine with plenty of RAM and a tight disk. Its size is computed from the
  machine and stays between 256 MiB and 8 GiB; `TORRCAST_TS_CACHE` (bytes) and
  `TORRCAST_TS_CACHE_DIR` override the size and the place.
- About 33 GB of free disk: 30 GB for warming (`/var/lib/torrcast/warm`; `warm_dir` and
  `warm_budget_gb` in the config) and 3 GiB of partition space that is never touched. When
  the disk allows, installation also puts up to 8 GiB of torrent cache there; otherwise it
  shrinks the cache or moves it to memory. The warming budget is shared by all titles, and
  a new one evicts the longest untouched of the others. If space runs short, warming stops
  with an explicit line - `disk budget of 30 GB is used up`, or `the partition has N GB
  free - that's the last reserve` - while playback continues from the live window.
- A TV or set-top box with a built-in **Chromecast** receiver on the same network.

> **Receiver note.** Two receiver profiles are measured and shipped: `cautious (Samsung
> Q70D)` and `Android TV box (Xiaomi TV Stick)`. torrcast reads the receiver's passport
> and picks one of them; a receiver it does not recognise gets the cautious profile. Such
> a receiver may work, but is not guaranteed.

## Commands

```text
cast <query> [sNeM] [--voice [N|STUDIO]] [--new] [--dry] [--pick N] [--menu] [--release N] [--file N]
cast                    # same as cast status
cast stop               # stop casting and save the position
cast status             # what plays, position/duration, file, track, stream, warmed share
cast doctor             # check terminal, locale, ffmpeg, services, receiver, and stream
cast log [--since WHEN] # sessions since 2d / 12h / 30m / YYYY-MM-DD
cast --tv               # find receivers; take a single one, or choose by number
cast --tv <ip>          # save an address directly
cast --en               # the whole product in English: text, bot replies and voice tracks
cast --ru               # the whole product in Russian
cast -tg                # open Telegram bot setup
cast -h, --help         # help with every public option
cast --version          # version
```

`sNeM` means season N, episode M, for example `s2e5`. It is part of the positional query,
not an option. `2x5` is an accepted form of the same request.

The happy path asks nothing when torrcast is confident. Phase lines are redrawn in place
on a live terminal and closed with the time they took; the run below is abbreviated,
because release numbers, timings and seed counts vary with indexer and swarm answers:

```text
$ cast matrix
searching “matrix”... 2.4 s
taking “The Matrix (1999)” - 3 pictures matched; another one: cast releases matrix and --pick N
...
packing... 3.1 s
waiting for the TV... 1.2 s
playing “The Matrix” (1999) · 1080p · eng - on TV   (start 9 s)
```

After search, the command names the chosen title and proceeds directly to release
selection. `--menu` asks for a title explicitly. A menu also appears on its own when
there is no honest default, such as when the requested franchise part is absent from the
results and any pick would play a different movie:

```text
$ cast matrix --menu
searching “matrix”... 2.4 s
  1. The Matrix (1999) · IMDb 8.7 · 2 h 16 min
     The Matrix is a 1999 science fiction action film written and directed by the
     Wachowskis.
  2. The Matrix Reloaded (2003) · IMDb 7.2 · 2 h 18 min
     ...
  3. The Matrix Revolutions (2003) · IMDb 6.7 · 2 h 9 min
     ...
Enter - “The Matrix (1999)”, item 1 of 3
What are we watching? [1]:
```

The list is chronological, and the number in square brackets is what Enter takes: the
**first franchise part whose own swarm is alive**. A franchise is watched from its
beginning, and parts with dead swarms are stepped over. The line right above the question
spells that pick out by name, because the default is often not the first row.

Rating, runtime, and a one-sentence description arrive in the background from open,
keyless sources: Wikipedia, Wikidata, and the IMDb ratings export that `install.sh` puts
on disk. The menu waits for the description, because it takes several lines and they
cannot be pushed under an item someone is already reading. It does not wait for rating and
runtime: those are written into the printed line in place, and the line changes under the
cursor. The wait is a ceiling, not a delay - 1.5 s, and 2.7 s in English, where the
description costs a second lookup wave - and the menu appears the moment the descriptions
are in, or at once when there is nothing to say.

Titles that share a name but differ in year are separate pictures. The liveliest one is
taken, because swarm activity is the best guess at what was meant. This is never silent:
the line names the picture with its year, the seed count of its best release, how many
other pictures go under that name, and the `--menu` command that lists them. So
`cast mummy` can take the liveliest "Mummy" and say so, while `cast mummy --menu` asks. A
number in the query is read as a franchise part - or, for a series, as a season.

Where there is no honest default, the menu has to be answered: Enter takes nothing and the
question repeats until a number is given. `cast matrix --pick 2` names the item up front
and asks nothing; the number is checked against the order that was shown, so a number that
now stands for a different picture is refused by name instead of being played silently.
Without a terminal - over SSH with no pty, from cron - a question is refused out loud, and
the refusal names both ways out: the exact title, or `--pick N`.

`start N s` in the playback line is the time to the **first live frame on the screen**,
not to the moment packaging began: the receiver reports `PLAYING` earlier than it shows a
picture, and that number would be flattering.

An unfinished title resumes silently, on the same release, file and track, from the saved
position. The playback line says so and ends with the way out of it:

```text
playing “Cyberpunk” · s1e2 · 1080p · track 1 · from 0:03:20 · pick another: --menu - on TV   (start 6 s)
```

`--new` plays the same release, file, and track from the start. `--menu`, `--pick N`,
`--release N`, and `--file N` ask for a picture or a release of their own and are not
answered by the bookmark. An explicit episode is a different request: it jumps inside the
saved release.

### Series

Name an episode inside the query: `cast <series> s2e5` or `cast <series> 2x5`. There is no
episode menu: `cast <series>` plays the next episode of the recorded torrent, and after
`cast stop` it resumes at the saved position.

Episodes continue by themselves. The next file of the same torrent starts without a
question and without a new receiver connection - the receiver application stays up between
episodes and is closed only when the show ends. The show unit names what follows:
`next episode: s2e6`.

A season running out is not the end of the show. The unit searches for the next season by
itself, asking for the same title and the first episode of the next season, and plays it
from there:

```text
«Doctor Who» - season 2 watched, searching season 3
```

If the next season is not there, the reason is said out loud - `«Doctor Who» - season 2 was
the last: ...` - and playback ends. A later `cast <series>` on an exhausted torrent starts it
over and says so: `“Doctor Who” - s2e13 was the last one in the release, so playing from the
start`.

### Voices

Release selection is automatic, and every rejection is named:

```text
release 2 does not fit (av1) - taking 5
```

Receivers that cannot decode HEVC get a full-stream transcode. A named HEVC release enters
the queue only as a last hope - when no live ordinary release carries the requested episode -
because a full transcode occupies the CPU from the first second to the credits and starts a
few seconds slower. A 2160p release plays the same way, through a full transcode scaled down
to 1080p; it is taken when there is no 1080p, and it never outranks a live 1080p. A release
heavier than the bitrate ceiling does not reach the queue at all. A zero-seed
release sinks below its live neighbours, and when the swarm of the chosen one stays silent,
selection moves down the queue within its own budget rather than giving up on the first
release.

Voice selection is automatic too, and it follows the product language. An English
installation puts English audio first, then the picture's own original language, then
Russian; audio description and crew commentary are ranked last. Inside a tier the plainer
track wins: an original ahead of a dub, and among Russian tracks a dub ahead of multi-voice,
two-voice and single-voice. `cast --ru` puts the Russian ladder on top instead. The playback
line names the selected voice.

The same requirement reaches release selection. Under English, a release whose audio
passport does not confirm an English track is skipped and the queue moves on. When none of
the checked releases has one, torrcast plays the best of them and says so:

```text
no English voice in any of the checked releases (4) - turning on release 2, sound Japanese
```

An explicit voice is remembered for that picture, and a later `cast` reuses it. Automatic
selection never writes to that memory. When the remembered voice is missing from a new
release, torrcast says `no “eng · Original” voice track in this release - taking the usual
one` and keeps the memory.

```text
cast voices <query>             # voice tracks of the release that would play
cast <query> --voice N          # take track N and remember it
cast <query> --voice STUDIO     # take a track by studio name or label, and remember it
cast <query> --voice            # numbered menu of tracks
```

`cast voices` prints the release it would take and its numbered tracks, marking the
automatic `[default]` and the `[remembered]` one. A name given to `--voice` is matched
whole, ignoring case and spaces, and not as a substring: `MVO` does not match
`MVO (LostFilm)`.

### Session log

torrcast keeps its own playback trace for investigation after the TV has been turned off:

```text
cast log                 # the last three sessions
cast log --since 2d      # everything since a boundary (2d / 12h / 30m / YYYY-MM-DD)
```

Without `--since`, the last three sessions are shown. With it, the boundary moves back and
the session count is not capped. A session is one film or one episode: each episode opens its
own entry, while the search and release selection of a `cast` run stand under the parent
identifier that those entries extend, so nothing of one run is scattered.

A session shows the query with the number of rows and pictures it brought, each indexer's
result count and time or its silence, the queue with the reasons candidates were dropped, the
release taken with its quality, track and bitrate, every rebuffer, network break, stall and
receiver dropout, errors, and whether it was watched to the end or stopped at a position.
Every line carries its offset from the start of the session.

The trace is stored beside the state as one JSONL file per day, kept for seven days and
capped at 64 MiB in total, oldest first. Nothing is uploaded. Writes go through a bounded
background queue, so playback never waits for the disk; when that queue overflows, the number
of dropped records goes into the trace itself, so a gap is never silent. If nothing played
for a week, `cast log` prints `no trace - not a single session over the week`.

### Debug controls

These controls expose internals only when explicitly requested:

```text
cast releases <query>              # table of releases per picture, then exit
cast <query> --release N           # use release N; numbers come from cast releases
cast <query> --release N --file N  # also take file N of that release
cast <query> --dry                 # the whole resolve without casting
cast <query> --new                 # the same release, file and track from the start
cast <query> --menu                # list the pictures and ask, instead of choosing
```

A release or file named by hand is never substituted: the selection gates do not judge it and
the queue holds nothing else. Pause and seek with the TV remote. Exit codes are `0` for
success, `1` when nothing was found, `2` for a failure torrcast could not work around
(a service or the receiver), and `3` when the person cancels a question. `cast doctor`
returns `2` when any of its checks fails.

## How it works

```text
query -> search (Prowlarr) -> parse (torrent names, franchises, sNeM)
      -> stream (TorrServer) -> ffmpeg -> HLS -> cast (Chromecast)
                            \-> warm (whole movie to disk, background)
```

There is no permanent playback daemon. For each show, `cast` starts a transient
`torrcast-play` unit that holds ffmpeg, an HLS server and a position watcher. The serving
address is derived from the route to the TV, so the receiver is handed a bare IP of the
interface it can actually see and DNS is never in the playback path. The command may exit
while playback continues; the unit's logs are `journalctl -u torrcast-play`, and `cast
stop` stops the unit, which writes the position out on its way down. The only permanent
services are TorrServer, Prowlarr, the local AniLibria and JacRed search adapters that
Prowlarr queries, and, for trackers whose hostname does not survive SNI inspection, a
local TLS shim that pins only the names that need it.

Warming waits for the first picture, then reads ahead at four times real time under
`nice`. Politeness alone does not free a processor, so warming also freezes outright
(`SIGSTOP`) whenever the live show's reserve dips or the live encoder is working: the
place being watched right now always wins. The segment grid is deterministic, so segment
`vN` is the same place in the film no matter where packing started, and a warmed piece
and a live piece are interchangeable under the same name. Seeking into a warmed area
needs no network. Copy versus transcode is decided piece by piece from the keyframe map,
so only the heavy pieces are re-encoded and the joins between copied and re-encoded
pieces stay continuous in timestamps and in audio.

`cast status` reports how much of the film is warmed and says when it is warmed whole. If
the source disappears beyond the warmed area, the screen goes dark and torrcast says so,
in the journal and in `cast status`, with how long it has been dark and when it will give
up. A receiver's own patience runs out sooner than that, so once the source is confirmed
back torrcast reloads playback at the saved second. It does this only on a free receiver
and never interrupts someone else's playback. Attempts are capped per outage; when they
run out it goes dark honestly and the next `cast` resumes from the saved place.

Progress lives in `/var/lib/torrcast/state.json`, written atomically; a bookmark at 95
percent of the runtime counts as watched. The remembered voice is a track label, not a
track number, because the next run may pick a different release in which the same voice
is numbered differently. If that label is absent from the new release, torrcast names the
voice that is playing instead.

Configuration is `/etc/torrcast/config.json`, and only the TV address is required: the
receiver and an optional profile key, the Prowlarr and TorrServer URLs, the Prowlarr API
key, the transport (`http` by default; `https` works but wants a certificate the TV
trusts), the serving address, port and segment directory, the segment grid and buffer
settings, the bitrate and transcode thresholds, and the warm switch, directory, disk
budget and rate.

Each receiver's measured properties form a profile: the segment weight ceiling, codecs
that have to be transcoded, bitrate thresholds, how long the receiver waits before it
drops the session, and stall thresholds. The device's own passport (maker, model, name)
selects the profile; a device that stays silent or is not recognised gets the cautious
one. `cast doctor` names the active profile and where it came from, and `cast log`
carries the same line into every session digest. `receiver_profile` pins a profile by
key, and an unknown key falls back to the cautious one. A threshold written into the
configuration by hand outranks the profile: the profile only fills in values left equal
to the cautious default.

## Development

```sh
.venv/bin/ruff check
.venv/bin/ruff format --check
.venv/bin/mypy
.venv/bin/pytest
scripts/dead-code
```

All five must return code 0. Run `mypy` with no arguments: `[tool.mypy] files` in
`pyproject.toml` defines its coverage (`torrcast`, `tgbot`, `tests`, `scripts`). Naming
paths on the command line silently narrows that coverage.

`scripts/dead-code` runs four stages, and the scope of each is the point of it. Uncalled
names are looked for in the package together with `scripts`, but deliberately without
tests, so code whose only caller is its own mirror test is removed with that test. The
second stage looks for names no test calls, the third for package modules nobody imports,
and the fourth for fixtures no test asks for. Callers that no import graph can see are
named explicitly: `http.server` request handlers in `scripts/vulture-whitelist.py`, and
the console entry points, `python -m`, the probes in `scripts/`, and the names the
installer and the indexer definitions mention as strings among the graph roots.

`scripts/test-gate` runs all of it plus the structure gate, the CLI and installer
contracts, the wiring mirrors, and the machine and ffmpeg test sets.

The layers are `domain` (pure models and rules), `ports` (external contracts), `usecases`
(scenarios), `adapters` (the only place allowed to touch the network, the disk and
subprocesses), `cli`, and `runtime` (wiring). Of the package layers only `runtime` may
import `adapters`. `scripts/structure-gate` enforces sixteen rules, among them one public
class or function per module, a module named after it, a 200-line ceiling, a mirror test
for every module, and that import table. Every rule has a negative probe in
`tests/test_structure_gate.py`. `scripts/where.py` says where a symbol is declared.

The `scripts/` directory also holds probes for segment grids and keyframe maps, cold
start and transcode benchmarks, torrent tracker checks, audio track collection, and live
receiver smoke runs. A probe takes the path to its input on the command line, and when it
writes output it drops `<output>.passport.json` beside it: the commit, a fingerprint
computed over the package files themselves, the probe's own name and SHA-256, the
timestamp, the command line, and the size, line count and SHA-256 of every input and of
the output. The commit can be missing, because code gets copied to machines that have no
repository; the fingerprint never is, and it is what proves two runs used the same code.

The passport also states whether the run itself was valid, and says so explicitly when
nobody measured that, because silence would read as "valid". A live receiver measurement
is taken by two instruments, torrcast's own trace and the receiver's own log, and the
second one can stop silently. A run whose receiver log went blind is reported as a
spoilt measurement and its stall count is not printed at all, rather than passing off a
zero earned by a dead instrument. A companion guard, `scripts/probesign.py`, checks that
every receiver threshold in the tree names the probe it was measured with.

## License

[MIT](LICENSE). The license covers torrcast's own code and grants no rights to anything
watched with it. Sources and their legality are the user's responsibility.
