#!/usr/bin/env bash
# install.sh — установка torrcast на Debian/Ubuntu (в том числе в LXC). Идемпотентен:
# повторный запуск ничего не ломает и не пересоздаёт то, что уже на месте.
#
# Фазы: зависимости → пакет → TorrServer → Prowlarr → индексеры → конфиг → раздача.
# Ноль регистраций и внешних ключей: apikey Prowlarr генерит сам себе, мы его
# вычитываем из его же config.xml и кладём в конфиг torrcast.
#
# Песочница (проверка фаз без root и без прода):
#   TORRCAST_PREFIX=/tmp/t TORRCAST_CONFIG_DIR=/tmp/t/etc TORRCAST_STATE_DIR=/tmp/t/var \
#   TORRCAST_BIN_DIR=/tmp/t/bin TORRCAST_NO_ROOT=1 TORRCAST_NO_SYSTEMD=1 \
#   TORRCAST_PHASES="torrserver prowlarr indexers config" ./install.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${TORRCAST_PREFIX:-/opt/torrcast}"
CONFIG_DIR="${TORRCAST_CONFIG_DIR:-/etc/torrcast}"
STATE_DIR="${TORRCAST_STATE_DIR:-/var/lib/torrcast}"
BIN_DIR="${TORRCAST_BIN_DIR:-/usr/local/bin}"
#: Интерпретатор ищем, а не прибиваем: на Debian 12 есть только python3.11,
#: python3.12 в её репозиториях нет вовсе. Нижняя граница — 3.11
#: (requires-python), на ней зелены тесты и mypy --strict.
PYTHON="${TORRCAST_PYTHON:-}"
#: Индекс пакетов Python. В части сетей штатный индекс не отвечает вовсе, поэтому
#: рядом лежат полные зеркала (индекс + файлы) — установка сама выберет живое.
PIP_INDEX="${TORRCAST_PIP_INDEX:-https://pypi.org/simple}"
PIP_MIRRORS=("https://pypi.tuna.tsinghua.edu.cn/simple" "https://mirrors.aliyun.com/pypi/simple")

TS_HOST="${TORRCAST_TS_HOST:-127.0.0.1}"
TS_PORT="${TORRCAST_TS_PORT:-8090}"
PL_HOST="${TORRCAST_PL_HOST:-127.0.0.1}"
PL_PORT="${TORRCAST_PL_PORT:-9696}"
TS_URL="http://$TS_HOST:$TS_PORT"
PL_URL="http://$PL_HOST:$PL_PORT"
#: Кэш TorrServer держим в RAM, на диск не пишем. 4 ГиБ — половина от 8 ГиБ памяти:
#: если её меньше, задай свой размер через TORRCAST_TS_CACHE.
TS_CACHE="${TORRCAST_TS_CACHE:-4294967296}"

# Индексеры: definitionName в схеме Prowlarr + базовый URL. Только открытые: ни
# регистрации, ни капчи, ни ключа - трекеры с логином здесь не появятся принципиально.
# Knaben - метапоиск (агрегирует чужие каталоги и отдаёт infoHash), остальные прямые.
# Недоступный из этой сети индексер просто не добавится и работать не помешает.
INDEXERS=("Knaben|https://knaben.org/" "rutor|https://rutor.info/")

PHASES="${TORRCAST_PHASES:-packages torrcast torrserver sources prowlarr indexers config hls}"

# Источники, которые домашний канал может резать (см. фазу `sources`).
PL_DEFS_URL="${TORRCAST_PL_DEFS_URL:-https://indexers.prowlarr.com/master/11}"
DEFS_TARBALL="${TORRCAST_DEFS_TARBALL:-https://codeload.github.com/Prowlarr/Indexers/tar.gz/refs/heads/master}"
SHIM_DIR="${TORRCAST_SHIM_DIR:-/etc/torrcast-shim}"
SHIM_PORT="${TORRCAST_SHIM_PORT:-443}"

# Трекеры, чьё имя может не пройти по TLS. Поля:
#   имя | путь пробы | тело POST (пусто - GET) | кандидаты обхода через запятую.
# Проба обязана просить ЗАМЕТНОЕ тело (десятки КБ): мелкий ответ проходит и через
# троттлинг, обрыв ловится только на объёме. Кандидаты - то, что умеет sni-shim.py:
# `direct` (стучаться на IP origin'а: для IP-адреса SNI не отправляется вовсе) и
# запасное имя, ведущее в тот же origin, - для тех, кто без SNI не отвечает.
# Новый такой трекер заводится одной строкой здесь и строкой в INDEXERS.
SHIMS=(
    'api.knaben.org|/v1|{"query":"матрица","search_type":"score","size":50}|direct,https://knaben.eu'
    'rutor.info|/search/matrix||direct'
)
#: Нужно ли засеивать определения индексеров руками — решает фаза `sources`.
SEED_DEFS=0
#: Браузерная подпись: без неё часть трекеров отвечает отказом ещё на пробе.
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"

# Раздача HLS: сегменты в tmpfs (фильм на диск не пишем). Транспорт по умолчанию —
# голый http на IP: ни серта, ни имени, ни DNS в пути показа. Адрес раздачи не
# настраивается — код сам берёт тот интерфейс, с которого хост виден телевизору.
# TORRCAST_HLS_BASE_URL — запасной выход, если прямой путь не заработает.
HLS_DIR="${TORRCAST_HLS_DIR:-/dev/shm/torrcast}"
HLS_PORT="${TORRCAST_HLS_PORT:-8080}"
HLS_TRANSPORT="${TORRCAST_TRANSPORT:-http}"
HLS_BASE_URL="${TORRCAST_HLS_BASE_URL:-}"
HLS_HOST="${TORRCAST_HLS_HOSTNAME:-torrcast.local}"
TLS_DIR="$CONFIG_DIR/tls"

log()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
skip() { printf '    уже на месте: %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
die()  { printf '\033[31mошибка:\033[0m %s\n' "$*" >&2; exit 1; }
has()  { [[ " $PHASES " == *" $1 "* ]]; }

need_root() {
    [ -n "${TORRCAST_NO_ROOT:-}" ] && return 0
    [ "$(id -u)" -eq 0 ] || die "запускать от root: sudo ./install.sh"
}

# Служба: в системе — юнит systemd, в песочнице — просто фоновый процесс,
# чтобы фазы проверялись живьём, а не «как будто».
run_service() {  # $1 имя, $2 описание, $3 команда
    if [ -n "${TORRCAST_NO_SYSTEMD:-}" ]; then
        pgrep -f -- "$3" >/dev/null 2>&1 && { skip "процесс $1 (песочница)"; return 0; }
        info "запускаю $1 фоном (песочница)"
        # shellcheck disable=SC2086
        setsid nohup $3 >"$PREFIX/$1.log" 2>&1 </dev/null &
        return 0
    fi
    write_unit "$1" "$2" "$3"
    systemctl enable --now "$1.service"
}

# Погасить службу, чтобы следующий run_service поднял её заново: `enable --now` и
# pgrep в песочнице живой процесс не трогают, а после обновления кода это и нужно.
stop_service() {  # $1 имя, $2 маска процесса для песочницы
    if [ -n "${TORRCAST_NO_SYSTEMD:-}" ]; then
        pkill -f -- "$2" >/dev/null 2>&1 || true
    else
        systemctl stop "$1.service" >/dev/null 2>&1 || true
    fi
}

wait_http() {  # $1 url, $2 секунд
    local i=0
    until curl -fsS -o /dev/null "$1" 2>/dev/null; do
        i=$((i + 1)); [ "$i" -ge "${2:-60}" ] && return 1; sleep 1
    done
}

# --- 1. Зависимости ---------------------------------------------------------
#: python3-venv обязателен: на голом Debian `python3 -m venv` без него не работает.
APT_PACKAGES=(ffmpeg curl ca-certificates jq tar openssl python3-venv)

# Самый свежий интерпретатор не ниже 3.11. Явный TORRCAST_PYTHON уважаем как есть.
pick_python() {
    [ -n "$PYTHON" ] && return 0
    local candidate
    for candidate in python3.13 python3.12 python3.11 python3; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
            PYTHON="$candidate"
            return 0
        fi
    done
    die "нужен python 3.11 или новее (см. requires-python в pyproject.toml)"
}

#: ffmpeg не ниже 6.1 — из-за -readrate_initial_burst. В Debian 12 живёт 5.1, а без burst
#: темп упаковки лечится только паузой процесса — той самой, под которой приёмник намертво
#: виснет в BUFFERING. Статическая сборка кладётся в /usr/local/bin и перебивает пакетную
#: по PATH; пакет ffmpeg остаётся на месте как запасной вариант.
#: ⚠️ Сборка именно BtbN. Статик johnvansickle 7.0.2 на Xeon E5-2696 v4 ставится и версию
#: печатает, а на первом же MPEG-TS падает в segfault (проверено дважды, с записями в
#: dmesg) — то есть ломается ровно на том формате, в котором мы пакуем.
FFMPEG_MIN="${TORRCAST_FFMPEG_MIN:-6.1}"
FFMPEG_URL="${TORRCAST_FFMPEG_URL:-https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n7.1-latest-linux64-gpl-7.1.tar.xz}"

ffmpeg_version() {  # $1 — путь/имя бинаря; печатает голую версию либо ничего
    "$1" -version 2>/dev/null | head -1 | awk '{print $3}' | sed 's/^[^0-9]*//'
}

# Проверка сборки в деле, а не по строчке версии: пакуем секунду MPEG-TS (наш формат)
# и читаем её обратно. Segfault ловится здесь, а не на живом показе.
ffmpeg_smoke() {  # $1 — каталог для временного файла
    local clip="$1/smoke.ts"
    /usr/local/bin/ffmpeg -hide_banner -loglevel error -y \
        -f lavfi -i "testsrc=size=320x240:rate=25:duration=1" -f lavfi -i "sine=duration=1" \
        -c:v libx264 -pix_fmt yuv420p -preset ultrafast -c:a aac -f mpegts "$clip" || return 1
    /usr/local/bin/ffprobe -v error -show_entries stream=codec_name -of csv "$clip" >/dev/null || return 1
    info "сборка проверена: MPEG-TS пакуется и читается"
}

install_ffmpeg() {
    local have; have="$(ffmpeg_version ffmpeg)"
    if [ -n "$have" ] && dpkg --compare-versions "$have" ge "$FFMPEG_MIN" 2>/dev/null; then
        skip "ffmpeg $have (нужно ≥ $FFMPEG_MIN: -readrate_initial_burst)"
        return
    fi
    [ "$(uname -m)" = "x86_64" ] || die "статической сборки ffmpeg под $(uname -m) нет — \
поставь ffmpeg ≥ $FFMPEG_MIN сам"
    info "ffmpeg ${have:-нет} — беру статическую сборку: $FFMPEG_URL"
    # Каталог убираем сами: `trap ... RETURN` без `set -T` цепляется ко ВСЕМ функциям
    # сразу и падает на первом же чужом return («work: unbound variable»).
    local work; work="$(mktemp -d)"
    curl -fsSL -o "$work/ffmpeg.tar.xz" "$FFMPEG_URL" || die "не скачался ffmpeg: $FFMPEG_URL"
    tar -xf "$work/ffmpeg.tar.xz" -C "$work"
    local bin; bin="$(find "$work" -type f -name ffmpeg -perm -u+x | head -1)"
    [ -n "$bin" ] || die "в архиве ffmpeg нет бинаря ffmpeg"
    install -d -m 0755 /usr/local/bin
    install -m 0755 "$bin" /usr/local/bin/ffmpeg
    install -m 0755 "$(dirname "$bin")/ffprobe" /usr/local/bin/ffprobe
    hash -r
    local now; now="$(ffmpeg_version /usr/local/bin/ffmpeg)"
    dpkg --compare-versions "$now" ge "$FFMPEG_MIN" 2>/dev/null \
        || die "поставился ffmpeg $now — это всё ещё ниже $FFMPEG_MIN"
    ffmpeg_smoke "$work" || die "сборка ffmpeg $now не пережила MPEG-TS — другой URL"
    rm -rf "$work"
    info "ffmpeg $now → /usr/local/bin (пакетная $(ffmpeg_version /usr/bin/ffmpeg) осталась)"
}

install_packages() {
    log "зависимости"
    local missing=()
    for pkg in "${APT_PACKAGES[@]}"; do
        dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done
    if [ ${#missing[@]} -eq 0 ]; then
        skip "apt-пакеты (${APT_PACKAGES[*]})"
    else
        apt-get update -qq
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}"
    fi
    install_ffmpeg
    pick_python
    info "интерпретатор $PYTHON ($("$PYTHON" -c 'import sys; print(sys.version.split()[0])'))"
}

# --- 2. Пакет torrcast в собственный venv ------------------------------------

# Отвечает ли индекс пакетов. Спрашиваем страницу одного пакета, а не корень индекса:
# корневой листинг — десятки мегабайт, и замер упирался бы в его размер, а не в
# доступность. Молчаливо: неответ здесь — штатная ветка, а не ошибка.
index_alive() {  # $1 — базовый URL индекса
    curl -fsS -m 10 -o /dev/null "${1%/}/pip/" 2>/dev/null
}

# Откуда pip берёт пакеты в этот заход: штатный индекс, а если из этой сети он не
# отвечает — первое живое зеркало. Выбор кладётся в PIP_INDEX_URL, поэтому его видят и
# сборочные окружения pip (зависимости сборки тоже качаются из индекса). Заданный
# снаружи PIP_INDEX_URL не трогаем: выбор уже сделан за нас.
pick_pip_index() {
    [ -n "${PIP_INDEX_URL:-}" ] && return 0
    index_alive "$PIP_INDEX" && return 0
    local mirror
    for mirror in "${PIP_MIRRORS[@]}"; do
        if index_alive "$mirror"; then
            export PIP_INDEX_URL="$mirror"
            info "⚠ pypi недоступен — ставлю через зеркало ${mirror#https://}"
            return 0
        fi
    done
    info "⚠ pypi недоступен, и зеркала тоже — пробую штатным путём"
}

install_torrcast() {
    log "пакет torrcast → $PREFIX"
    pick_python  # фаза может гоняться и в одиночку, без `packages`
    if [ ! -x "$PREFIX/venv/bin/python" ]; then
        install -d -m 0755 "$PREFIX"
        "$PYTHON" -m venv "$PREFIX/venv"
    else
        skip "venv $PREFIX/venv"
    fi
    pick_pip_index
    "$PREFIX/venv/bin/pip" install --quiet --upgrade pip
    # Первый вызов ставит зависимости, второй — САМ пакет, всегда заново.
    # ⚠️ Оба флага второго вызова нужны, и оба пойманы живой выкаткой:
    # без --force-reinstall pip видит ту же версию из pyproject.toml (от правок кода она
    # не меняется), говорит «Requirement already satisfied» и уходит; а с ним, но без
    # --no-cache-dir, он ставит СВОЁ прежнее колесо из кэша — то есть опять не наш код.
    # Оба раза ./install.sh рапортовал «готово», а в venv оставалась прежняя нарезка HLS,
    # и замеры шли по коду, которого в репе уже не было.
    "$PREFIX/venv/bin/pip" install --quiet "$REPO_DIR"
    "$PREFIX/venv/bin/pip" install --quiet --force-reinstall --no-deps --no-cache-dir "$REPO_DIR"
    install -d -m 0755 "$BIN_DIR"
    # Симлинк перезаписываем всегда: это дёшево и чинит битую ссылку.
    ln -sfn "$PREFIX/venv/bin/cast" "$BIN_DIR/cast"
    verify_torrcast
}

# Слепок дерева исходников: «sha256 + относительный путь» на каждый .py, порядок
# фиксирован сортировкой, поэтому два каталога сравниваются построчно.
py_manifest() {  # $1 — каталог пакета torrcast
    (
        cd "$1" || return 1
        LC_ALL=C find . -name __pycache__ -prune -o -name '*.py' -print0 |
            LC_ALL=C sort -z | xargs -0r sha256sum
    )
}

# Сверка «что реально лежит в venv» ↔ «что лежит в репе». Без неё установка врёт:
# pip умеет отрапортовать успех, не тронув ни одного файла (см. комментарий выше),
# и это ловилось только сверкой хэшей руками после каждой выкатки. Расхождение —
# это провал установки, а не повод для предупреждения: дальше по скрипту нет ничего,
# что чинило бы venv, а показ пойдёт по чужому коду.
verify_torrcast() {
    local installed repo_side venv_side changed count sum
    # -P убирает текущий каталог из sys.path: без него `import torrcast`, запущенный
    # из каталога репы, нашёл бы исходники репы и сверка сравнивала бы их сами с собой.
    installed="$("$PREFIX/venv/bin/python" -P -c \
        'import pathlib, torrcast; print(pathlib.Path(torrcast.__file__).resolve().parent)')" ||
        die "пакет torrcast не импортируется из $PREFIX/venv — установка не состоялась"
    [ -d "$REPO_DIR/torrcast" ] || die "рядом с install.sh нет каталога torrcast/ — нечего сверять"
    [ -d "$installed" ] || die "torrcast импортируется, но каталога $installed нет"

    repo_side="$(py_manifest "$REPO_DIR/torrcast")"
    venv_side="$(py_manifest "$installed")"
    [ -n "$repo_side" ] || die "в $REPO_DIR/torrcast нет ни одного .py — сверять нечего"
    if [ "$repo_side" != "$venv_side" ]; then
        # Имена расходящихся файлов: строки, встречающиеся только с одной стороны.
        changed="$(comm -3 \
            <(printf '%s\n' "$repo_side" | LC_ALL=C sort) \
            <(printf '%s\n' "$venv_side" | LC_ALL=C sort) |
            awk '{print $NF}' | LC_ALL=C sort -u)"
        printf '%s\n' "$changed" | while read -r f; do
            [ -n "$f" ] && info "расходится: ${f#./}"
        done
        info "в репе:  $REPO_DIR/torrcast"
        info "в venv:  $installed"
        die "venv не совпадает с исходниками: pip отрапортовал успех, но код не обновился"
    fi

    count="$(printf '%s\n' "$repo_side" | grep -c .)"
    sum="$(printf '%s\n' "$repo_side" | sha256sum | cut -c1-12)"
    info "сверка venv ↔ репа: $count файлов .py совпадают (sha256 $sum)"
}

# --- 3. TorrServer ----------------------------------------------------------
TS_RELEASE="${TORRCAST_TS_RELEASE:-https://api.github.com/repos/YouROK/TorrServer/releases/latest}"

install_torrserver() {
    log "TorrServer ($TS_URL, кэш в RAM)"
    install -d -m 0755 "$PREFIX/bin" "$PREFIX/torrserver"

    if [ -x "$PREFIX/bin/TorrServer" ]; then
        skip "бинарь TorrServer $("$PREFIX/bin/TorrServer" --help 2>&1 | head -1)"
    else
        local arch url
        case "$(uname -m)" in
            x86_64)  arch=amd64 ;;
            aarch64) arch=arm64 ;;
            armv7l)  arch=arm7 ;;
            *) die "нет сборки TorrServer под $(uname -m)" ;;
        esac
        url="$(curl -fsSL "$TS_RELEASE" \
            | jq -r --arg n "TorrServer-linux-$arch" '.assets[]|select(.name==$n)|.browser_download_url')"
        [ -n "$url" ] && [ "$url" != null ] || die "не нашёл сборку TorrServer-linux-$arch"
        info "качаю $url"
        curl -fsSL -o "$PREFIX/bin/TorrServer.new" "$url"
        chmod +x "$PREFIX/bin/TorrServer.new"
        mv "$PREFIX/bin/TorrServer.new" "$PREFIX/bin/TorrServer"
    fi

    run_service torrserver "TorrServer для torrcast" \
        "$PREFIX/bin/TorrServer --port $TS_PORT --ip $TS_HOST --path $PREFIX/torrserver"
    wait_http "$TS_URL/echo" 60 || die "TorrServer не поднялся на $TS_URL"

    # Кэш в RAM, публичные ретрекеры в magnet'ы, DHT и PEX включены.
    # ConnectionsLimit: дефолтные 25 соединений — это потолок скорости на ПЕРВЫХ секундах,
    # когда пиры ещё разбираются, кто что отдаёт, а нам нужны и хвост файла (Cues), и
    # начало (первый сегмент) прямо сейчас. Холодный старт упирается ровно в это место,
    # поэтому потолок поднят.
    local sets
    sets="$(curl -fsS -X POST "$TS_URL/settings" -d '{"action":"get"}' \
        | jq -c --argjson c "$TS_CACHE" '.CacheSize=$c|.UseDisk=false|.RetrackersMode=1
                                        |.DisableDHT=false|.DisablePEX=false|.EnableDLNA=false
                                        |.ConnectionsLimit=100')"
    curl -fsS -X POST "$TS_URL/settings" -H 'Content-Type: application/json' \
        -d "{\"action\":\"set\",\"sets\":$sets}" >/dev/null
    info "кэш $((TS_CACHE / 1024 / 1024)) МиБ в RAM, ретрекеры включены"
}

# --- 3.5. Источники: проверяем, что доступно, и обходим только то, что бито ----
#
# В разных сетях доступно разное: то, что у одного провайдера открыто, у другого режется
# по SNI. Поэтому ничего не обходится «на всякий случай»: сначала замер, обход ставится
# только если источник реально не отвечает.

pinned() {  # $1 имя - прибито ли уже к 127.0.0.1
    grep -qE "^127\.0\.0\.1[[:space:]]+$1(\$|[[:space:]])" /etc/hosts
}

hosts_pin() {  # $1 имя — прибить к 127.0.0.1, идемпотентно
    if pinned "$1"; then
        skip "/etc/hosts: $1"
    else
        printf '127.0.0.1 %s\n' "$1" >>/etc/hosts
        info "/etc/hosts: $1 → 127.0.0.1"
    fi
}

# Отвечает ли имя ЦЕЛИКОМ. Успех - curl дочитал ответ до конца: обрыв посреди тела он
# считает ошибкой, даже если заголовки были 200. Ровно так троттлинг и выглядит.
probe_whole() {  # $1 имя, $2 путь, $3 тело POST (пусто - GET)
    if [ -n "$3" ]; then
        curl -fsS -m 25 -o /dev/null -A "$UA" -H 'Content-Type: application/json' \
            -X POST -d "$3" "https://$1$2" 2>/dev/null
    else
        curl -fsS -m 25 -o /dev/null -A "$UA" "https://$1$2" 2>/dev/null
    fi
}

# Прежний шим умел ровно один трекер и звался по нему. Общий садится на тот же порт,
# так что старую службу гасим - иначе он просто не встанет.
retire_old_shim() {
    [ -e /etc/systemd/system/knaben-shim.service ] || [ -d /etc/knaben-shim ] || return 0
    systemctl disable --now knaben-shim.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/knaben-shim.service /usr/local/share/ca-certificates/knaben-shim.crt
    rm -rf /etc/knaben-shim
    systemctl daemon-reload >/dev/null 2>&1 || true
    update-ca-certificates --fresh >/dev/null 2>&1 || true
    info "прежний одиночный шим убран - его место занимает общий"
}

setup_shim() {  # $@ - маршруты вида имя=кандидат[,кандидат…]
    local routes=("$@") spec sans="" changed=0
    install -d -m 0755 "$SHIM_DIR"
    pick_python  # фаза может гоняться и в одиночку, без `packages`
    [ -n "${TORRCAST_NO_SYSTEMD:-}" ] || retire_old_shim

    # Код шима приезжает из репы на КАЖДОМ заходе (деплой только репа→прод). Изменился
    # он, набор имён или маршруты - службу гасим: юнит-то прежний, и сама по себе она
    # осталась бы на старом.
    if cmp -s "$REPO_DIR/scripts/sni-shim.py" "$SHIM_DIR/sni-shim.py"; then
        skip "код шима $SHIM_DIR/sni-shim.py"
    else
        install -m 0755 "$REPO_DIR/scripts/sni-shim.py" "$SHIM_DIR/sni-shim.py"
        info "код шима обновлён из репы"
        changed=1
    fi

    # Серт один на все имена сразу: перевыпускаем, когда набор имён изменился.
    for spec in "${routes[@]}"; do sans="$sans${sans:+,}DNS:${spec%%=*}"; done
    if [ -s "$SHIM_DIR/shim.crt" ] && [ "$sans" = "$(cat "$SHIM_DIR/names" 2>/dev/null)" ]; then
        skip "серт шима на ${#routes[@]} имён"
    else
        openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
            -keyout "$SHIM_DIR/shim.key" -out "$SHIM_DIR/shim.crt" \
            -subj "/CN=${routes[0]%%=*}" -addext "subjectAltName=$sans" 2>/dev/null
        chmod 600 "$SHIM_DIR/shim.key"
        printf '%s\n' "$sans" >"$SHIM_DIR/names"
        info "серт шима выпущен на: ${routes[*]%%=*}"
        changed=1
    fi
    # Prowlarr — .NET, и доверяет он системному хранилищу; своего для процесса ему не
    # задать (SSL_CERT_FILE он игнорирует — проверено). Ключ остаётся доступным только root.
    install -m 0644 "$SHIM_DIR/shim.crt" /usr/local/share/ca-certificates/torrcast-shim.crt
    update-ca-certificates >/dev/null 2>&1

    [ "$(cat "$SHIM_DIR/routes" 2>/dev/null)" = "$(printf '%s\n' "${routes[@]}")" ] || changed=1
    printf '%s\n' "${routes[@]}" >"$SHIM_DIR/routes"
    for spec in "${routes[@]}"; do hosts_pin "${spec%%=*}"; done
    [ "$changed" = 1 ] && stop_service torrcast-shim "$SHIM_DIR/sni-shim.py"
    run_service torrcast-shim "TLS-шим для трекеров, чьё имя не проходит по SNI" \
        "$PYTHON $SHIM_DIR/sni-shim.py $SHIM_DIR/shim.crt $SHIM_DIR/shim.key $SHIM_PORT ${routes[*]}"
}

check_sources() {
    log "источники: что доступно из этой сети"

    if curl -fsS -m 15 -o /dev/null "$PL_DEFS_URL" 2>/dev/null; then
        info "каталог индексеров Prowlarr доступен — он возьмёт определения сам"
    else
        # Без этой строки КАЖДЫЙ запрос схемы ждёт таймаута .NET — 100 секунд.
        info "⚠ каталог индексеров Prowlarr недоступен — определения возьмём с GitHub"
        hosts_pin indexers.prowlarr.com
        SEED_DEFS=1
    fi

    local spec host path body ups routes=()
    for spec in "${SHIMS[@]}"; do
        IFS='|' read -r host path body ups <<<"$spec"
        if pinned "$host"; then
            # Замер пошёл бы через уже стоящий шим и всегда отвечал бы «всё хорошо» - а
            # код из репы так бы и не доехал. Прибито - значит ведём через шим и дальше.
            info "$host уже за шимом - маршрут остаётся"
            routes+=("$host=$ups")
        elif probe_whole "$host" "$path" "$body"; then
            info "$host отвечает целиком - обход не нужен"
        else
            info "⚠ $host отдаёт ответ не целиком (режется по имени в SNI) - веду через шим"
            routes+=("$host=$ups")
        fi
    done
    if [ "${#routes[@]}" -eq 0 ]; then
        info "все трекеры доступны по имени - шим не нужен"
        return
    fi
    setup_shim "${routes[@]}"

    # «Шим поднят» и «через него отвечает» - разные утверждения. Проверяем вторым
    # заходом: имя уже прибито к шиму, поэтому та же проба идёт сквозь него. Служба
    # только что запущена, сокета может ещё не быть - спрашиваем не один раз.
    local i
    for spec in "${SHIMS[@]}"; do
        IFS='|' read -r host path body ups <<<"$spec"
        printf '%s\n' "${routes[@]}" | grep -qx "$host=$ups" || continue
        i=0
        until probe_whole "$host" "$path" "$body"; do
            i=$((i + 1))
            [ "$i" -ge 12 ] && break
            sleep 1
        done
        if [ "$i" -lt 12 ]; then
            info "через шим $host отвечает целиком"
        else
            info "⚠ $host не отвечает и через шим - его индексер останется пустым"
        fi
    done
}

# Определения индексеров (Cardigann) — из репы Prowlarr/Indexers на GitHub.
# ⚠️ Класть ПЛОСКО в корень `Definitions/`: листинг Prowlarr читает только верхний
# уровень (SearchOption.TopDirectoryOnly), и `Definitions/v11/rutor.yml` не виден.
# Рестарт не нужен — схема пересобирается на каждый запрос.
seed_definitions() {
    local dir="$PREFIX/prowlarr-data/Definitions"
    if [ "$(find "$dir" -maxdepth 1 -name '*.yml' 2>/dev/null | wc -l)" -gt 100 ]; then
        skip "определения индексеров ($(find "$dir" -maxdepth 1 -name '*.yml' | wc -l) шт.)"
        return
    fi
    log "определения индексеров с GitHub"
    install -d -m 0755 "$dir"
    local tmp; tmp="$(mktemp -d)"
    if curl -fsSL -o "$tmp/defs.tar.gz" "$DEFS_TARBALL" \
       && tar -xzf "$tmp/defs.tar.gz" -C "$tmp" --wildcards '*/definitions/v11/*.yml'; then
        find "$tmp" -path '*/definitions/v11/*.yml' -exec install -m 0644 {} "$dir/" \;
        info "разложено $(find "$dir" -maxdepth 1 -name '*.yml' | wc -l) определений"
    else
        info "⚠ определения не скачались — останутся только встроенные индексеры"
    fi
    rm -rf "$tmp"
}

# --- 4. Prowlarr ------------------------------------------------------------
# Качаем с GitHub, как и TorrServer. Родной prowlarr.servarr.com части адресов отдаёт
# 403: зависеть от того, чей IP спрашивает, установка не должна. Сборка та же самая,
# версия совпадает. Запасной путь остался вторым.
PL_RELEASE="${TORRCAST_PL_RELEASE:-https://api.github.com/repos/Prowlarr/Prowlarr/releases/latest}"
PL_FALLBACK="${TORRCAST_PL_FALLBACK:-https://prowlarr.servarr.com/v1/update/master/updatefile?os=linux&runtime=netcore&arch=x64}"

install_prowlarr() {
    log "Prowlarr ($PL_URL, публичные индексеры)"
    install -d -m 0755 "$PREFIX/prowlarr-data"

    if [ -x "$PREFIX/prowlarr/Prowlarr" ]; then
        skip "бинарь Prowlarr"
    else
        local url
        url="$(curl -fsSL "$PL_RELEASE" 2>/dev/null \
            | jq -r '[.assets[]?|select(.name|test("linux-core-x64\\.tar\\.gz$"))][0].browser_download_url // empty')"
        if [ -z "$url" ]; then
            info "GitHub сборку не отдал — иду на $PL_FALLBACK"
            url="$PL_FALLBACK"
        fi
        info "качаю $url"
        install -d -m 0755 "$PREFIX/prowlarr"
        curl -fsSL -o "$PREFIX/prowlarr.tar.gz" "$url"
        # В архиве верхний каталог `Prowlarr/` — срезаем, чтобы путь был предсказуем.
        tar -xzf "$PREFIX/prowlarr.tar.gz" -C "$PREFIX/prowlarr" --strip-components=1
        rm -f "$PREFIX/prowlarr.tar.gz"
        [ -x "$PREFIX/prowlarr/Prowlarr" ] || die "распаковка Prowlarr не дала бинаря"
    fi

    # Конфиг пишем ДО первого старта: иначе Prowlarr сядет на 0.0.0.0 и включит
    # форму логина. Слушаем только localhost, аутентификация внешняя (её нет).
    if [ -f "$PREFIX/prowlarr-data/config.xml" ]; then
        skip "$PREFIX/prowlarr-data/config.xml"
    else
        cat >"$PREFIX/prowlarr-data/config.xml" <<XML
<Config>
  <BindAddress>$PL_HOST</BindAddress>
  <Port>$PL_PORT</Port>
  <EnableSsl>False</EnableSsl>
  <LaunchBrowser>False</LaunchBrowser>
  <AuthenticationMethod>External</AuthenticationMethod>
  <AuthenticationRequired>DisabledForLocalAddresses</AuthenticationRequired>
  <AnalyticsEnabled>False</AnalyticsEnabled>
  <Branch>master</Branch>
  <LogLevel>info</LogLevel>
</Config>
XML
    fi

    run_service prowlarr "Prowlarr для torrcast" \
        "$PREFIX/prowlarr/Prowlarr -nobrowser -data=$PREFIX/prowlarr-data"
    wait_http "$PL_URL/ping" 120 || die "Prowlarr не поднялся на $PL_URL"
}

# apikey Prowlarr генерит себе сам при первом старте — просто вычитываем.
prowlarr_apikey() {
    sed -n 's:.*<ApiKey>\(.*\)</ApiKey>.*:\1:p' "$PREFIX/prowlarr-data/config.xml" | head -1
}

# --- 5. Индексеры через API (ноль ручных шагов в вебе) ----------------------
install_indexers() {
    [ "$SEED_DEFS" = 1 ] && seed_definitions
    log "индексеры Prowlarr"
    local key schema existing
    key="$(prowlarr_apikey)"
    [ -n "$key" ] || die "не вычитал apikey из config.xml Prowlarr"

    schema="$(curl -fsS "$PL_URL/api/v1/indexer/schema?apikey=$key")"
    existing="$(curl -fsS "$PL_URL/api/v1/indexer?apikey=$key")"

    local spec def url body name
    for spec in "${INDEXERS[@]}"; do
        def="${spec%%|*}"; url="${spec##*|}"
        name="$(jq -r --arg d "$def" '.[]|select(.definitionName==$d)|.name' <<<"$schema")"
        if [ -z "$name" ] || [ "$name" = null ]; then
            info "⚠ $def нет в схеме этой версии Prowlarr — пропускаю"
            continue
        fi
        if jq -e --arg n "$name" 'any(.[]; .name==$n)' <<<"$existing" >/dev/null; then
            skip "индексер $name"
            continue
        fi
        body="$(jq -c --arg d "$def" --arg u "$url" '
            .[]|select(.definitionName==$d)
            |{name,implementation,configContract,definitionName,priority,protocol,
              enable:true, appProfileId:1, tags:[], added:"0001-01-01T00:00:00Z",
              fields:[.fields[]|{name,value:(if .name=="baseUrl" then $u else .value end)}]}
        ' <<<"$schema")"
        if curl -fsS -X POST "$PL_URL/api/v1/indexer?apikey=$key" \
             -H 'Content-Type: application/json' -d "$body" >/dev/null; then
            info "добавлен $name"
        else
            info "⚠ $name не добавился (недоступен из этой сети?) — не блокер"
        fi
    done
    info "индексеров сейчас: $(curl -fsS "$PL_URL/api/v1/indexer?apikey=$key" | jq 'length')"

    # Живая проверка: «индексер заведён» и «поиск что-то находит» — разные утверждения.
    # Первое бывает правдой при неправде второго — например когда сеть режет индексер.
    # Отказ самой проверки установку не роняет: это отчёт, а не условие.
    local out found
    out="$(curl -fsS -m 120 -G "$PL_URL/api/v1/search" \
        --data-urlencode "apikey=$key" --data-urlencode "query=матрица" \
        --data-urlencode "type=search" --data-urlencode "limit=100" 2>/dev/null)" || out=""
    found="$(jq 'length' <<<"${out:-[]}" 2>/dev/null)" || found=0
    if [ "${found:-0}" -gt 0 ] 2>/dev/null; then
        info "проверочный поиск «матрица»: $found раздач"
        jq -r 'group_by(.indexer)[]|"    \(.[0].indexer): \(length)"' <<<"$out" 2>/dev/null || true
    else
        info "⚠ проверочный поиск НИЧЕГО не нашёл — индексеры недоступны из этой сети"
    fi
}

# --- 6. Конфиг, ключи, состояние --------------------------------------------
setup_config() {
    log "конфиг и ключи"
    install -d -m 0755 "$CONFIG_DIR" "$STATE_DIR"
    local key; key="$(prowlarr_apikey)"

    # Темп упаковки и окно сегментов — дефолты КОДА (torrcast/state.py), а не пользовательская
    # настройка: иначе обновление молча упирается в старые числа из конфига (ровно это и
    # случилось с hls_readrate=1.5). Вычищаем их отовсюду. Туда же транспорт: раздача по
    # http на IP — устройство системы, а не вкус, и старый https-адрес из конфига обязан
    # уйти. Потолок битрейта из того же класса: это замеренное свойство приёмника (Q70D
    # ребуферит уже на 17.8 Мбит/с). Оставь его в конфиге — и опущенный до 16 дефолт молча
    # упрётся в старые 20. Настройки перекодирования — тоже замеры процессора и приёмника,
    # а не вкус.
    local tuned='del(.hls_readrate, .hls_window, .hls_burst, .hls_keep, .bitrate_warn_mbit,'
    tuned="$tuned .bitrate_hard_mbit, .recode, .recode_mbit, .recode_at_mbit, .recode_preset,"
    tuned="$tuned .recode_ahead,"
    tuned="$tuned .recode_cache_mb)"
    tuned="$tuned | .transport=\$t | .hls_port=(\$p|tonumber) | .hls_base_url=\$b"

    if [ -f "$CONFIG_DIR/config.json" ]; then
        # Адрес ТВ и прочий выбор пользователя не трогаем — обновляем только ключ.
        skip "$CONFIG_DIR/config.json (обновляю apikey, транспорт и темп беру из кода)"
        local tmp; tmp="$(mktemp "$CONFIG_DIR/.config.json.XXXX")"
        jq --arg k "$key" --arg t "$HLS_TRANSPORT" --arg p "$HLS_PORT" --arg b "$HLS_BASE_URL" \
            "$tuned | .prowlarr_apikey=\$k" "$CONFIG_DIR/config.json" >"$tmp"
        mv "$tmp" "$CONFIG_DIR/config.json"
        return
    fi

    umask 077
    cat >"$CONFIG_DIR/config.json" <<JSON
{
  "tv": null,
  "receiver": "chromecast",
  "torrserver_url": "$TS_URL",
  "prowlarr_url": "$PL_URL",
  "prowlarr_apikey": "$key",
  "transport": "$HLS_TRANSPORT",
  "hls_base_url": "$HLS_BASE_URL",
  "hls_port": $HLS_PORT,
  "hls_cert": "$TLS_DIR/torrcast.crt",
  "hls_key": "$TLS_DIR/torrcast.key",
  "hls_dir": "$HLS_DIR"
}
JSON
    info "apikey Prowlarr перенесён в $CONFIG_DIR/config.json"
}

# --- 7. Юниты и https --------------------------------------------------------
write_unit() {  # $1 имя, $2 описание, $3 команда
    local path="/etc/systemd/system/$1.service"
    local body
    body="$(cat <<UNIT
[Unit]
Description=$2
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$3
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
)"
    if [ -f "$path" ] && [ "$(cat "$path")" = "$body" ]; then
        skip "юнит $1.service"
        return
    fi
    printf '%s\n' "$body" >"$path"
    systemctl daemon-reload
}

# Своего демона раздачи нет: сервер живёт внутри процесса `cast` ровно на время
# показа — отдельного caddy/nginx с их конфигами не заводим.
# Здесь только то, что должно существовать до первого запуска: каталог сегментов, а при
# выключенной по умолчанию опции `transport: https` — ещё и серт.
setup_hls() {
    log "раздача HLS ($HLS_TRANSPORT, порт $HLS_PORT, сегменты в $HLS_DIR)"
    install -d -m 0755 "$HLS_DIR"
    if [ "$HLS_TRANSPORT" != "https" ]; then
        info "адрес раздачи собирается по маршруту до ТВ — ни серта, ни имени, ни DNS"
        return
    fi
    install -d -m 0700 "$TLS_DIR"

    if [ -s "$TLS_DIR/torrcast.crt" ] && [ -s "$TLS_DIR/torrcast.key" ]; then
        skip "серт $TLS_DIR/torrcast.crt (до $(openssl x509 -noout -enddate \
            -in "$TLS_DIR/torrcast.crt" | cut -d= -f2))"
        return
    fi

    # Self-signed = рабочий дефолт для mock-приёмника. Chromecast его молча не примет:
    # сюда кладутся файлы настоящего серта (или правится путь в config.json) — и всё.
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -keyout "$TLS_DIR/torrcast.key" -out "$TLS_DIR/torrcast.crt" \
        -subj "/CN=$HLS_HOST" -addext "basicConstraints=critical,CA:TRUE" \
        -addext "subjectAltName=DNS:$HLS_HOST,DNS:localhost,IP:127.0.0.1" 2>/dev/null
    chmod 600 "$TLS_DIR/torrcast.key"
    info "выпущен self-signed на $HLS_HOST — mock-приёмке этого достаточно"
    info "⚠ живому ТВ нужен серт LE: Chromecast self-signed молча не играет"
}

main() {
    need_root
    has packages   && install_packages
    has torrcast    && install_torrcast
    has torrserver && install_torrserver
    has sources    && check_sources
    has prowlarr   && install_prowlarr
    has indexers   && install_indexers
    has config     && setup_config
    has hls        && setup_hls
    log "готово. Осталось: cast --tv <ip-телевизора>"
}

main "$@"
