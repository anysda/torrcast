#!/usr/bin/env bash
# install.sh — установка torrcast на стенд/LXC. Идемпотентен: повторный запуск
# ничего не ломает и не пересоздаёт то, что уже на месте (§6 ТЗ).
#
# Этапы: зависимости → TorrServer → Prowlarr → конфиг и ключи → юниты → cast.
# Ноль регистраций и внешних ключей: apikey Prowlarr генерится здесь же.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${TORRCAST_PREFIX:-/opt/torrcast}"
CONFIG_DIR="${TORRCAST_CONFIG_DIR:-/etc/torrcast}"
STATE_DIR="${TORRCAST_STATE_DIR:-/var/lib/torrcast}"
BIN_DIR="${TORRCAST_BIN_DIR:-/usr/local/bin}"
PYTHON="${TORRCAST_PYTHON:-python3.12}"

APT_PACKAGES=(ffmpeg curl ca-certificates jq)

log()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
skip() { printf '    уже на месте: %s\n' "$*"; }
die()  { printf '\033[31mошибка:\033[0m %s\n' "$*" >&2; exit 1; }

need_root() {
    [ "$(id -u)" -eq 0 ] || die "запускать от root: sudo ./install.sh"
}

# --- 1. Зависимости ---------------------------------------------------------
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

    command -v "$PYTHON" >/dev/null 2>&1 || die "нужен $PYTHON (см. requires-python в pyproject.toml)"
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

    # Симлинк перезаписываем всегда: это дёшево и чинит битую ссылку.
    ln -sfn "$PREFIX/venv/bin/cast" "$BIN_DIR/cast"
}

# --- 3. TorrServer ----------------------------------------------------------
install_torrserver() {
    log "TorrServer (:8090, кэш в RAM)"
    # TODO(этап 2): скачать бинарь нужной архитектуры в $PREFIX/bin/TorrServer,
    # положить unit torrserver.service (--path в tmpfs, на диск не пишем),
    # проверять уже установленную версию и не качать повторно.
    if systemctl is-enabled --quiet torrserver.service 2>/dev/null; then
        skip "torrserver.service"
    else
        printf '    TODO: установка TorrServer ещё не реализована\n'
    fi
}

# --- 4. Prowlarr ------------------------------------------------------------
install_prowlarr() {
    log "Prowlarr (:9696, публичные индексеры)"
    # TODO(этап 1): установка Prowlarr, добавление RuTor и публичных индексеров
    # через его API, при необходимости — маршрут запросов через zapret-контур.
    if systemctl is-enabled --quiet prowlarr.service 2>/dev/null; then
        skip "prowlarr.service"
    else
        printf '    TODO: установка Prowlarr ещё не реализована\n'
    fi
}

# --- 5. Конфиг, ключи, состояние --------------------------------------------
setup_config() {
    log "конфиг и ключи"
    install -d -m 0755 "$CONFIG_DIR" "$STATE_DIR"

    if [ -f "$CONFIG_DIR/config.json" ]; then
        skip "$CONFIG_DIR/config.json (адрес ТВ не трогаем)"
        return
    fi

    # Внутренний ключ Prowlarr↔cast генерим сами — регистраций у нас нет.
    local apikey
    apikey="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    umask 077
    cat >"$CONFIG_DIR/config.json" <<JSON
{
  "tv": null,
  "receiver": "chromecast",
  "torrserver_url": "http://127.0.0.1:8090",
  "prowlarr_url": "http://127.0.0.1:9696",
  "prowlarr_apikey": "$apikey",
  "hls_base_url": "https://torrcast.anysda.space"
}
JSON
}

# --- 6. Юниты и https --------------------------------------------------------
setup_units() {
    log "юниты и https"
    # TODO(этап 2): раздача HLS (caddy/nginx) с CORS '*' и LE-сертом по DNS-01,
    # split-DNS torrcast.anysda.space → адрес стенда в AdGuard.
    # Постоянных своих демонов нет: воспроизведение поднимает transient-юнит
    # torrcast-play через systemd-run, гасит его `cast stop`.
    printf '    TODO: https-раздача HLS ещё не настроена\n'
}

main() {
    need_root
    install_packages
    install_torrcast
    install_torrserver
    install_prowlarr
    setup_config
    setup_units
    log "готово. Осталось: cast --tv <ip-телевизора>"
}

main "$@"
