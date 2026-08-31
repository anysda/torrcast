[Русский](README-ru.md)

# torrcast

`cast` is a command-line tool that finds a movie or series by name and plays it on
your TV - with no cloud in the data path and no clicking through torrents. The stream
goes from the torrent to your computer and then to the TV, without leaving your local
network.

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
example: "release N says 1080p but is smaller - using M (real 1080p)", "warning: about
N Mbit/s - transcoding heavy pieces on the fly", or "video is HEVC - transcoding the
whole stream on the fly".

## Installation

On a machine that already has `curl`:

```sh
curl -fsSL https://torrcast.anysda.space | sh
```

A bare Debian 12 installation does **not** include `curl`; install it first. The
bootstrap requires `curl`, `tar`, `sha256sum`, and `bash`. The one-liner asks GitLab for
the latest version, downloads that exact release tarball, verifies its SHA-256 checksum,
and runs the `install.sh` inside it. When not run as root, the bootstrap restarts itself
through `sudo`.

The endpoint names the language of the product it installs. `https://torrcast.anysda.space`
installs an English `cast`: menus, messages and the preferred voice track are all English.
`https://rutorrcast.anysda.space` installs the same release with Russian as the product
language. Either way the choice is not final: `cast --en` and `cast --ru` switch the
installed copy at any time.

To install from source, use the same `install.sh`:

```sh
git clone https://gitlab.anysda.space/anysda/torrcast && cd torrcast
sudo ./install.sh
```

Use `sudo ./install.sh -en` for English installer output or `sudo ./install.sh -ru` for
Russian installer output. English is the default.

Installation discovers receivers through mDNS and by scanning local subnets on port
8009. One receiver is saved automatically. If several are found, the installer lists
their names and addresses and continues without choosing. Save an address directly with
`cast --tv <ip>`, or use `cast --tv` and choose a number.

The final screen of the installer speaks about the receiver itself. The saved one is named
by name and address, or by address alone when the device announced no name, as well as on a
repeat installation, where the configuration holds an address only. Of several found ones it
lists as many as fit under the logo and counts the rest: "and 2 more". An empty search is not
left in silence: the screen says to turn the TV on and names `cast --tv`; on a narrow
terminal the wording shrinks, but the command never drops out of it. A mock stand is named
as such: it casts nowhere. The same screen names the door to the other language - `cast --ru`
after an English installation.

`install.sh` is idempotent: running it again updates only what changed. No registration
or external API keys are required. It generates the Prowlarr key, stores it in the
torrcast configuration, and configures public indexers that require no account: Knaben,
RuTor, Nyaa.si, and YTS. AniLibria and JacRed provide Russian anime voices through two
small local adapters installed alongside torrcast. If a provider blocks an indexer by
name, installation sets up and verifies a local bypass.

TorrServer and Prowlarr use pinned versions tested with the rest of the system. Both pins
are near the top of `install.sh`. If a pinned GitHub release is gone, installation says
so and uses the latest release instead.

Installation ends with a package check. The script compares every `.py` file in the venv
with the adjacent sources and prints a line like `venv vs repo: N .py files match
(sha256 ...)`. A mismatch fails with the file names instead of reporting success.

The package lives in `/opt/torrcast/venv`; `/usr/local/bin/cast` is a symlink to it.

## Requirements

- Linux with systemd: Debian 12 or newer, or Ubuntu with Python 3.11 or newer available
  from the system package manager. Installation uses `apt`.
- Python 3.11 or newer.
- `ffmpeg` 6.1 or newer. `-readrate_initial_burst` is required. If the system version is
  older, `install.sh` puts a static build in `/usr/local/bin`.
- Root privileges for installation of systemd units, packages, and directories under
  `/opt`, `/etc`, and `/var/lib`.
- About 8 GiB of RAM or more. The live HLS segment window is in `/dev/shm`, next to two
  ffmpeg processes. The torrent cache protects playback from an internet outage.
  Installation places it where more space is available, normally on disk, or in memory
  on a machine with abundant RAM and a tight disk. Its size is automatic; override it
  with `TORRCAST_TS_CACHE`.
- About 33 GB of free disk: 30 GB for warming (`/var/lib/torrcast/warm`, configurable)
  and 3 GiB of reserved free space. When possible, installation also places up to 8 GiB
  of torrent cache on disk; otherwise it reduces the cache or moves it to memory. The
  warming budget is shared, and a new movie evicts the oldest. If space runs short,
  warming stops with an explicit message while playback continues from the live window.
- A TV or set-top box with a built-in **Chromecast** receiver on the same network.

> **Receiver note.** Development and live measurements use a Samsung Q70D with built-in
> Chromecast and an Android TV box. torrcast selects measured profiles for them. An
> unknown receiver gets a conservative profile; it may work, but is not guaranteed.

## Commands

Run the whole gate with `scripts/test-gate`. Run only tests affected by a change with
`pytest --testmon`.

```text
cast <query> [sNeM] [--voice [N|STUDIO]] [--new] [--dry] [--pick N] [--menu] [--release N] [--file N]
cast                    # same as cast status
cast stop               # stop casting and save the position
cast status             # current item, position/duration, and source
cast doctor             # check terminal, locale, ffmpeg, services, receiver, and stream
cast log [--since WHEN] # sessions since 2d / 12h / 30m / YYYY-MM-DD
cast --tv               # discover receivers; take one automatically or choose a number
cast --tv <ip>          # save an address directly
cast --en               # the whole product in English: text, bot replies and voice tracks
cast --ru               # the whole product in Russian
cast -tg                # open Telegram bot setup
cast -h                 # short help
cast --help             # help with every public option
cast --version          # version
```

`sNeM` means season N, episode M, for example `s2e5`. It is part of the positional query,
not an option. `2x5` and `2 сезон 5 серия` are accepted forms of the same request.

The happy path asks nothing when torrcast is confident. The following abbreviated run
omits results that vary with indexer and swarm responses:

```text
$ cast matrix
searching for "matrix"...
...
```

After search, the command names the chosen title and proceeds directly to release
selection. `--menu` asks for a title explicitly. A menu also appears automatically when
there is no honest default, such as when the requested franchise part is absent and any
choice would play a different movie:

```text
$ cast matrix --menu
  1. The Matrix (1999)
  2. The Matrix Reloaded (2003)
  3. The Matrix Revolutions (2003)
  ...
What shall we watch? [1]: 1
...
```

Playback then handles packaging and receiver readiness by itself and announces a start
like "playing Title (year) - quality - language - voice - on TV (started at N s)".

The number in parentheses is the **first live franchise part**. Playback starts at the
beginning, but parts with dead swarms are skipped. Rating, runtime, and a short
description arrive in the background from open, keyless sources: Wikipedia, Wikidata,
and the IMDb rating export installed by `install.sh`. The menu waits for the description
because it cannot be inserted under an item after it has been read. It does not wait for
rating or runtime; those may appear in place. The whole menu waits at most 1.5 seconds.

Titles with one name but different years are separate movies. The liveliest one is used
because swarm activity indicates what people probably meant. This is never silent: the
line names its year, the best release's seed count, how many other matches exist, and the
option that shows them. `cast mummy` can choose the newest "Mummy" and say so, while
`cast mummy --menu` asks. A numbered sequel in the query is treated as that title.

When no honest default exists, the person must answer the displayed menu. There is no
default. `cast matrix --pick 2` supplies the menu item without asking. This is the only
way to answer such a question without a terminal, for example over SSH without a pty.

"Started at N s" means the first live picture on the screen, not merely that packaging
began.

An unfinished title resumes silently. The normal playback line names the saved position
and points to `--menu`. `--new` plays the same saved torrent, file, and track from the
beginning. `--menu`, `--pick N`, and an explicit episode select a title rather than
answering where to resume.

### Series

Name an episode in the query: `cast <series> s2e5`, `cast <series> 2x5`, or
`cast <series> 2 сезон 5 серия`. There is no episode menu: `cast <series>` plays the next
unseen episode, and after `cast stop` it resumes at the saved position.

Episodes continue automatically. The next file in the same torrent starts without a
question or a new receiver connection. When the torrent runs out of episodes, torrcast
says it was the last one and offers to start over.

### Voices

Release selection is automatic. A rejected release is named, for example "release N is
not usable (av1) - using M". Receivers that cannot decode HEVC get a live full-stream
transcode. Such a torrent is the last resort only when no live ordinary torrent contains
the requested episode. A live H.264 release always wins because full transcoding costs
CPU from start to credits and starts more slowly. A 2160p release is never that last
resort because it cannot be transcoded in real time. Zero-seed releases do not rise to
the top; if the selected swarm stays silent, selection continues through all candidates.

Voice selection is automatic too: Russian dub, multi-voice or voice-over, two-voice,
single-voice, other Russian, original, then a foreign dub. Audio description and crew
commentary are ranked last. The playback line names the selected voice.

An explicit voice is remembered for that title. A later `cast` reuses it. An explicit
option replaces the memory; automatic selection does not.

```text
cast voices <query>             # list voices in the selected release
cast <query> --voice 3          # use the third voice and remember it
cast <query> --voice STUDIO     # use a named studio and remember it
cast <query> --voice            # voice menu
```

### Session log

torrcast keeps its own playback trace for investigation after the TV has been turned off:

```text
cast log                 # the last three sessions
cast log --since 2d      # everything in two days (12h / 30m / YYYY-MM-DD)
```

Without `--since`, the last three sessions are shown. With it, the time boundary moves
back and the session count is unlimited. One session covers one complete `cast` command,
including playback. Search, release selection, and later screen events share an ID and
remain one record.

A session shows the query, each indexer's result count or silence, the chosen release and
rejection reasons, every rebuffer and network break with timestamps, errors, and whether
playback finished or stopped at a saved position.

The trace is stored beside state as one JSONL file per day, retained for seven days and
bounded in size. Nothing is uploaded. Writes go through a background queue, so playback
never waits for disk. If nothing played for a week, `cast log` says there is no trace.

### Debug controls

These controls expose internals only when explicitly requested:

```text
cast releases <query>              # table of releases, then exit
cast <query> --release N           # use release N
cast <query> --release N --file N  # also use file N in that torrent
cast <query> --dry                 # resolve everything without casting
cast <query> --new                 # saved torrent, file, and track from the beginning
cast <query> --menu                # title list and question instead of automatic choice
```

An explicitly selected release is never substituted. Pause and seek with the TV remote.
Exit codes are `0` for success, `1` for no result, `2` for an infrastructure failure
(Prowlarr, TorrServer, or receiver), and `3` when the person cancels a question. `cast
doctor` also returns `2` when any check fails.

## How it works

```text
query -> search (Prowlarr/Torznab) -> parse (torrent names, franchises, sNeM)
      -> stream (TorrServer, outage cache) -> ffmpeg -> HLS -> cast (Chromecast)
                                          \-> warm (whole movie to disk, background)
```

There is no permanent playback daemon. For each show, `cast` starts a transient
`torrcast-play` unit with ffmpeg, an HLS server over HTTP on a bare IP address, and a
position watcher. torrcast chooses the host interface visible to the TV, so DNS is not
in the playback path. The command may exit while playback continues. Logs are in
`journalctl -u torrcast-play`; `cast stop` stops the unit and saves the position.
Permanent services are limited to TorrServer, Prowlarr, the AniLibria and JacRed
adapters, and a local name bypass where required.

Warming begins **after** the first picture and uses spare CPU through `nice`, targeting
four times real time. The live position always has priority: if its reserve falls,
warming pauses. The segment grid is deterministic, so warm and live encoders produce the
same named piece of the movie. Seeking into a warm area is immediate and needs no
network. Copy-versus-transcode decisions are shared down to individual heavy pieces,
keeping one stable stream profile at every join.

`cast status` reports warming progress. If connectivity disappears beyond the warmed
area, torrcast says so and resumes when it returns. Since receiver patience is shorter,
torrcast can restart playback at the same second once the network is actually back. It
does so only on an idle receiver and never interrupts someone else's playback. If restart
fails, it exits honestly and the next `cast` resumes from the saved place.

Progress lives in `/var/lib/torrcast/state.json`; 95 percent watched counts as complete.
Voice memory stores a track signature, not a number, because another release may number
the same voice differently. If it no longer exists, torrcast says so.

Configuration is `/etc/torrcast/config.json`: receiver, Prowlarr and TorrServer
addresses, API key, transport, segment directory, and warm directory and budget.
Packaging speed, segment window, and transcode thresholds are measured receiver
properties in code, not preference settings.

Each receiver's measured properties form a profile: segment weight, codecs that require
transcoding, bitrate limits, receiver patience, and stall thresholds. The device identity
selects it automatically. Unknown devices get the most conservative profile. `cast
doctor` and `cast log` name the active profile. `receiver_profile` can pin one; an
explicit threshold in configuration takes precedence.

## Development

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
mypy
.venv/bin/pytest
scripts/dead-code
```

All five commands must return code 0. Check the code itself. Run `mypy` with no
arguments: `[tool.mypy] files` defines its coverage (`torrcast`, `tests`, and `scripts`).
Naming paths manually can silently narrow that coverage.

`scripts/dead-code` gives each stage deliberate coverage. Uncalled names are searched in
the package together with `scripts`, but without tests, so code called only by its mirror
test is removed with that test. Another stage checks tests, and a third checks modules
that nobody imports. Non-Python entry points such as `http.server` callbacks and
`python -m` are named explicitly in `scripts/vulture-whitelist.py` and graph roots.

`scripts/test-gate` runs everything, including installation layout and ffmpeg stages.

The layers are `domain` (pure models and rules), `ports` (external contracts),
`usecases` (scenarios), `adapters` (the only network, disk, and subprocess code), `cli`,
and `runtime` (wiring). Only `runtime` imports adapters. `scripts/structure-gate` enforces
one file per public rule, matching names, a 200-line ceiling, and a mirror test for each
module. Every rule has a negative probe in `tests/test_structure_gate.py`.
`scripts/where.py` identifies where a symbol is declared.

Before installation phases are tested on a target machine, the transferred file's
SHA-256 is compared with the working copy. Tests run in the development environment
that supplied that file.

The `scripts/` directory also contains playback probes for segment grids and keyframes,
startup and transcode measurements, torrent track inspection, and receiver queries.
Measurement inputs are not committed; probes accept their path. When writing output,
they add `<output>.passport.json` with the commit and code fingerprint, input
fingerprint, date, and probe version. A measurement without a passport cannot be
reproduced.

The passport always states whether the run itself was valid. Live receiver measurements
use both our trace and the receiver's own log. The latter can stop silently, so a run with
a truncated receiver log is rejected rather than claiming zero stalls from a dead
instrument.

## License

[MIT](LICENSE). The license covers torrcast code and grants no rights to content watched
with it. The user is responsible for sources and legality.
