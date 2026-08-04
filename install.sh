#!/usr/bin/env bash
# install.sh — установка torrcast на стенд/LXC. Идемпотентен: повторный запуск
# ничего не ломает и не пересоздаёт то, что уже на месте (§6 ТЗ).
#
# Фазы: зависимости → пакет → TorrServer → Prowlarr → индексеры → конфиг → юниты.
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
PYTHON="${TORRCAST_PYTHON:-python3.12}"

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

PHASES="${TORRCAST_PHASES:-packages torrcast torrserver prowlarr indexers config units}"

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

wait_http() {  # $1 url, $2 секунд
    local i=0
    until curl -fsS -o /dev/null "$1" 2>/dev/null; do
        i=$((i + 1)); [ "$i" -ge "${2:-60}" ] && return 1; sleep 1
    done
}

# --- 1. Зависимости ---------------------------------------------------------
APT_PACKAGES=(ffmpeg curl ca-certificates jq tar)

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
    command -v "$PYTHON" >/dev/null 2>&1 || die "нужен $PYTHON (см. requires-python)"
}

# --- 2. Пакет torrcast в собственный venv ------------------------------------
install_torrcast() {
    log "пакет torrcast → $PREFIX"
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

# --- 4. Prowlarr ------------------------------------------------------------
PL_RELEASE="${TORRCAST_PL_RELEASE:-https://prowlarr.servarr.com/v1/update/master/updatefile?os=linux&runtime=netcore&arch=x64}"

install_prowlarr() {
    log "Prowlarr ($PL_URL, публичные индексеры)"
    install -d -m 0755 "$PREFIX/prowlarr-data"

    if [ -x "$PREFIX/prowlarr/Prowlarr" ]; then
        skip "бинарь Prowlarr"
    else
        info "качаю Prowlarr"
        install -d -m 0755 "$PREFIX/prowlarr"
        curl -fsSL -o "$PREFIX/prowlarr.tar.gz" "$PL_RELEASE"
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
}

# --- 6. Конфиг, ключи, состояние --------------------------------------------
setup_config() {
    log "конфиг и ключи"
    install -d -m 0755 "$CONFIG_DIR" "$STATE_DIR"
    local key; key="$(prowlarr_apikey)"

    if [ -f "$CONFIG_DIR/config.json" ]; then
        # Адрес ТВ и прочий выбор владельца не трогаем — обновляем только ключ.
        skip "$CONFIG_DIR/config.json (обновляю только apikey)"
        local tmp; tmp="$(mktemp "$CONFIG_DIR/.config.json.XXXX")"
        jq --arg k "$key" '.prowlarr_apikey=$k' "$CONFIG_DIR/config.json" >"$tmp"
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
  "hls_base_url": "https://torrcast.anysda.space",
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

setup_units() {
    log "юниты и https"
    # TODO(этап 2): раздача HLS (caddy/nginx) с CORS '*' и LE-сертом по DNS-01,
    # split-DNS torrcast.anysda.space → адрес стенда в AdGuard.
    # Постоянных своих демонов нет: воспроизведение поднимает transient-юнит
    # torrcast-play через systemd-run, гасит его `cast stop`.
    info "TODO(этап 2): https-раздача HLS ещё не настроена"
}

main() {
    need_root
    has packages   && install_packages
    has torrcast    && install_torrcast
    has torrserver && install_torrserver
    has prowlarr   && install_prowlarr
    has indexers   && install_indexers
    has config     && setup_config
    has units      && setup_units
    log "готово. Осталось: cast --tv <ip-телевизора>"
}

main "$@"
