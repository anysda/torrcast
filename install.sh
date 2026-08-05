#!/usr/bin/env bash
# install.sh — установка torrcast на стенд/LXC. Идемпотентен: повторный запуск
# ничего не ломает и не пересоздаёт то, что уже на месте (§6 ТЗ).
#
# Фазы: зависимости → пакет → TorrServer → Prowlarr → индексеры → конфиг → https.
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
#: Интерпретатор ищем, а не прибиваем: на Debian 12 (стенд по §8) есть только
#: python3.11, python3.12 в её репозиториях нет вовсе. Нижняя граница — 3.11
#: (requires-python), на ней зелены тесты и mypy --strict.
PYTHON="${TORRCAST_PYTHON:-}"

TS_HOST="${TORRCAST_TS_HOST:-127.0.0.1}"
TS_PORT="${TORRCAST_TS_PORT:-8090}"
PL_HOST="${TORRCAST_PL_HOST:-127.0.0.1}"
PL_PORT="${TORRCAST_PL_PORT:-9696}"
TS_URL="http://$TS_HOST:$TS_PORT"
PL_URL="http://$PL_HOST:$PL_PORT"
#: Кэш TorrServer держим в RAM, на диск не пишем (§3). 4 ГиБ — из 8 ГиБ стенда.
TS_CACHE="${TORRCAST_TS_CACHE:-4294967296}"

# Индексеры: definitionName в схеме Prowlarr + базовый URL. Knaben — метапоиск,
# агрегирует RuTracker/TPB/Nyaa/1337x и отдаёт infoHash; RuTor — прямой.
INDEXERS=("Knaben|https://knaben.org/" "rutor|https://rutor.info/")

PHASES="${TORRCAST_PHASES:-packages torrcast torrserver sources prowlarr indexers config https}"

# Источники, которые домашний канал может резать (см. фазу `sources`).
PL_DEFS_URL="${TORRCAST_PL_DEFS_URL:-https://indexers.prowlarr.com/master/11}"
DEFS_TARBALL="${TORRCAST_DEFS_TARBALL:-https://codeload.github.com/Prowlarr/Indexers/tar.gz/refs/heads/master}"
KNABEN_API_HOST="${TORRCAST_KNABEN_API_HOST:-api.knaben.org}"
KNABEN_FRONT="${TORRCAST_KNABEN_FRONT:-https://knaben.eu}"
SHIM_DIR="${TORRCAST_SHIM_DIR:-/etc/knaben-shim}"
#: Нужно ли засеивать определения индексеров руками — решает фаза `sources`.
SEED_DEFS=0

# https-раздача HLS: сегменты в tmpfs (фильм на диск не пишем), серт и ключ — файлы,
# путь к которым знает конфиг. На стенде сюда встают файлы LE, код тот же самый.
HLS_DIR="${TORRCAST_HLS_DIR:-/dev/shm/torrcast}"
HLS_PORT="${TORRCAST_HLS_PORT:-8443}"
HLS_HOST="${TORRCAST_HLS_HOSTNAME:-torrcast.anysda.space}"
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

# Служба: на стенде — юнит systemd, в песочнице — просто фоновый процесс,
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

#: ffmpeg не ниже 6.1 — из-за -readrate_initial_burst (§6 SPEC-v2). В Debian 12 живёт
#: 5.1, а без burst темп упаковки лечится только паузой процесса — той самой, под которой
#: приёмник намертво виснет в BUFFERING. Статическая сборка кладётся в /usr/local/bin и
#: перебивает пакетную по PATH; пакет ffmpeg остаётся на месте как запасной вариант.
FFMPEG_MIN="${TORRCAST_FFMPEG_MIN:-6.1}"
FFMPEG_URL="${TORRCAST_FFMPEG_URL:-https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz}"

ffmpeg_version() {  # $1 — путь/имя бинаря; печатает голую версию либо ничего
    "$1" -version 2>/dev/null | head -1 | awk '{print $3}' | sed 's/^[^0-9]*//'
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
    rm -rf "$work"
    hash -r
    local now; now="$(ffmpeg_version /usr/local/bin/ffmpeg)"
    dpkg --compare-versions "$now" ge "$FFMPEG_MIN" 2>/dev/null \
        || die "поставился ffmpeg $now — это всё ещё ниже $FFMPEG_MIN"
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
install_torrcast() {
    log "пакет torrcast → $PREFIX"
    pick_python  # фаза может гоняться и в одиночку, без `packages`
    if [ ! -x "$PREFIX/venv/bin/python" ]; then
        install -d -m 0755 "$PREFIX"
        "$PYTHON" -m venv "$PREFIX/venv"
    else
        skip "venv $PREFIX/venv"
    fi
    "$PREFIX/venv/bin/pip" install --quiet --upgrade pip
    "$PREFIX/venv/bin/pip" install --quiet "$REPO_DIR"
    install -d -m 0755 "$BIN_DIR"
    # Симлинк перезаписываем всегда: это дёшево и чинит битую ссылку.
    ln -sfn "$PREFIX/venv/bin/cast" "$BIN_DIR/cast"
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

    # Кэш в RAM, публичные ретрекеры в magnet'ы, DHT и PEX включены (§3).
    local sets
    sets="$(curl -fsS -X POST "$TS_URL/settings" -d '{"action":"get"}' \
        | jq -c --argjson c "$TS_CACHE" '.CacheSize=$c|.UseDisk=false|.RetrackersMode=1
                                        |.DisableDHT=false|.DisablePEX=false|.EnableDLNA=false')"
    curl -fsS -X POST "$TS_URL/settings" -H 'Content-Type: application/json' \
        -d "{\"action\":\"set\",\"sets\":$sets}" >/dev/null
    info "кэш $((TS_CACHE / 1024 / 1024)) МиБ в RAM, ретрекеры включены"
}

# --- 3.5. Источники: проверяем, что доступно, и обходим только то, что бито ----
#
# Домашний канал и канал через VPN — разные интернеты, и это выяснилось на стенде
# (docs/stage5.md). Поэтому ничего не обходится «на всякий случай»: сначала замер,
# обход ставится только если источник реально не отвечает.

hosts_pin() {  # $1 имя — прибить к 127.0.0.1, идемпотентно
    if grep -qE "^127\.0\.0\.1[[:space:]]+$1(\$|[[:space:]])" /etc/hosts; then
        skip "/etc/hosts: $1"
    else
        printf '127.0.0.1 %s\n' "$1" >>/etc/hosts
        info "/etc/hosts: $1 → 127.0.0.1"
    fi
}

# Отвечает ли API Knaben ЦЕЛИКОМ. Мелкий ответ проходит и через троттлинг, поэтому
# просим полсотни результатов: обрыв тела ловится только на объёме.
knaben_whole() {
    curl -fsS -m 25 -X POST "https://$KNABEN_API_HOST/v1" -H 'Content-Type: application/json' \
        -d '{"query":"матрица","search_type":"score","size":50}' -o /dev/null 2>/dev/null
}

setup_shim() {
    install -d -m 0755 "$SHIM_DIR"
    pick_python  # фаза может гоняться и в одиночку, без `packages`
    # Код шима приезжает из репы на КАЖДОМ заходе (деплой только репа→прод). Изменился —
    # службу гасим: юнит-то прежний, и сама по себе она осталась бы на старом коде.
    if cmp -s "$REPO_DIR/scripts/knaben-shim.py" "$SHIM_DIR/knaben-shim.py"; then
        skip "код шима $SHIM_DIR/knaben-shim.py"
    else
        install -m 0755 "$REPO_DIR/scripts/knaben-shim.py" "$SHIM_DIR/knaben-shim.py"
        info "код шима обновлён из репы"
        stop_service knaben-shim "$SHIM_DIR/knaben-shim.py"
    fi
    if [ -s "$SHIM_DIR/knaben.crt" ] && [ -s "$SHIM_DIR/knaben.key" ]; then
        skip "серт шима $SHIM_DIR/knaben.crt"
    else
        openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
            -keyout "$SHIM_DIR/knaben.key" -out "$SHIM_DIR/knaben.crt" \
            -subj "/CN=$KNABEN_API_HOST" -addext "subjectAltName=DNS:$KNABEN_API_HOST" 2>/dev/null
        chmod 600 "$SHIM_DIR/knaben.key"
    fi
    # Prowlarr — .NET, и доверяет он системному хранилищу; своего для процесса ему не
    # задать (SSL_CERT_FILE он игнорирует — проверено). Ключ лежит root-only на стенде.
    install -m 0644 "$SHIM_DIR/knaben.crt" /usr/local/share/ca-certificates/knaben-shim.crt
    update-ca-certificates >/dev/null 2>&1
    hosts_pin "$KNABEN_API_HOST"
    run_service knaben-shim "TLS-шим для $KNABEN_API_HOST (обход DPI по SNI)" \
        "$PYTHON $SHIM_DIR/knaben-shim.py $KNABEN_FRONT $KNABEN_API_HOST $SHIM_DIR/knaben.crt $SHIM_DIR/knaben.key"
    # Юнит только что запущен — сокета может ещё не быть, поэтому спрашиваем не один раз.
    local i=0
    while [ "$i" -lt 15 ]; do
        if knaben_whole; then
            info "через шим API отвечает целиком"
            return
        fi
        i=$((i + 1))
        sleep 1
    done
    info "⚠ шим поднят, но API так и не отвечает"
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

    if [ -e "$SHIM_DIR/knaben-shim.py" ]; then
        # Замер пошёл бы через уже стоящий шим и всегда отвечал бы «всё хорошо» — а код
        # из репы так бы и не доехал. Стоит шим — идём в setup_shim, он и обновит.
        info "шим для $KNABEN_API_HOST уже стоит — обновляю из репы"
        setup_shim
    elif knaben_whole; then
        info "$KNABEN_API_HOST отвечает целиком — обход не нужен"
    else
        info "⚠ $KNABEN_API_HOST обрывает ответ на первых килобайтах (DPI по SNI)"
        setup_shim
    fi
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
# Качаем с GitHub, как и TorrServer. Родной prowlarr.servarr.com отдаёт домашнему
# адресу 403 (с egress через VPN — 200): зависеть от того, чей IP спрашивает, установка
# не должна. Сборка та же самая, версия совпадает. Запасной путь остался вторым.
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
    # На стенде первое было правдой, а второе нет (docs/stage5.md).
    local found
    found="$(curl -fsS -m 90 -G "$PL_URL/api/v1/search" \
        --data-urlencode "apikey=$key" --data-urlencode "query=матрица" \
        --data-urlencode "type=search" --data-urlencode "limit=100" 2>/dev/null | jq 'length' 2>/dev/null)"
    if [ -n "$found" ] && [ "$found" -gt 0 ] 2>/dev/null; then
        info "проверочный поиск «матрица»: $found раздач"
    else
        info "⚠ проверочный поиск НИЧЕГО не нашёл — индексеры недоступны из этой сети"
    fi
}

# --- 6. Конфиг, ключи, состояние --------------------------------------------
setup_config() {
    log "конфиг и ключи"
    install -d -m 0755 "$CONFIG_DIR" "$STATE_DIR"
    local key; key="$(prowlarr_apikey)"

    # Темп упаковки и окно сегментов — дефолты КОДА (torrcast/state.py), а не настройка
    # стенда: иначе выкатка нового поведения молча упирается в старые числа из конфига
    # (ровно это и случилось с hls_readrate=1.5, §7 A SPEC-v2). Вычищаем их отовсюду.
    local tuned='del(.hls_readrate, .hls_window, .hls_burst, .hls_keep)'

    if [ -f "$CONFIG_DIR/config.json" ]; then
        # Адрес ТВ и прочий выбор владельца не трогаем — обновляем только ключ.
        skip "$CONFIG_DIR/config.json (обновляю apikey, темп упаковки беру из кода)"
        local tmp; tmp="$(mktemp "$CONFIG_DIR/.config.json.XXXX")"
        jq --arg k "$key" "$tuned | .prowlarr_apikey=\$k" "$CONFIG_DIR/config.json" >"$tmp"
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
  "hls_base_url": "https://$HLS_HOST:$HLS_PORT",
  "hls_port": $HLS_PORT,
  "hls_cert": "$TLS_DIR/torrcast.crt",
  "hls_key": "$TLS_DIR/torrcast.key",
  "hls_dir": "$HLS_DIR",
  "bitrate_warn_mbit": 20.0
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

# Своего демона раздачи нет: https-сервер живёт внутри процесса `cast` ровно на время
# показа — отдельного caddy/nginx с их конфигами не заводим (§6, бюджет кода).
# Здесь только то, что должно существовать до первого запуска: каталог и серт.
setup_https() {
    log "https-раздача HLS ($HLS_HOST:$HLS_PORT, сегменты в $HLS_DIR)"
    install -d -m 0755 "$HLS_DIR"
    install -d -m 0700 "$TLS_DIR"

    if [ -s "$TLS_DIR/torrcast.crt" ] && [ -s "$TLS_DIR/torrcast.key" ]; then
        skip "серт $TLS_DIR/torrcast.crt (до $(openssl x509 -noout -enddate \
            -in "$TLS_DIR/torrcast.crt" | cut -d= -f2))"
        return
    fi

    # Self-signed = рабочий дефолт для mock-приёмки. Chromecast его молча не примет:
    # на стенде сюда кладутся файлы LE (или правится путь в config.json) — и всё.
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
    has https      && setup_https
    log "готово. Осталось: cast --tv <ip-телевизора>"
}

main "$@"
