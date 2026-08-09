#!/usr/bin/env bash
# install.sh — установка torrcast на Debian/Ubuntu (в том числе в LXC). Идемпотентен:
# повторный запуск ничего не ломает и не пересоздаёт то, что уже на месте.
#
# Фазы: локаль → зависимости → пакет → TorrServer → Prowlarr → индексеры → конфиг →
# раздача → приветствие.
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
#: Зеркала намеренно из разных геозон: первое вне китайского сегмента, два других
#: китайские - блокировка одной зоны не убивает разом все резервы. Ручной выбор -
#: через TORRCAST_PIP_INDEX.
PIP_INDEX="${TORRCAST_PIP_INDEX:-https://pypi.org/simple}"
PIP_MIRRORS=("https://pypi-mirror.gitverse.ru/simple" "https://pypi.tuna.tsinghua.edu.cn/simple" "https://mirrors.aliyun.com/pypi/simple")

TS_HOST="${TORRCAST_TS_HOST:-127.0.0.1}"
TS_PORT="${TORRCAST_TS_PORT:-8090}"
PL_HOST="${TORRCAST_PL_HOST:-127.0.0.1}"
PL_PORT="${TORRCAST_PL_PORT:-9696}"
TS_URL="http://$TS_HOST:$TS_PORT"
PL_URL="http://$PL_HOST:$PL_PORT"
#: Кэш TorrServer держим в RAM, на диск не пишем. Размер НЕ прибит числом: он считается
#: от фактической памяти машины (:func:`ts_cache_size`), потому что машина бывает и на
#: 4 ГБ, и на 32. Ручное переопределение - TORRCAST_TS_CACHE (байты).
#:
#: ⚠️ Замер: RSS TorrServer примерно ВДВОЕ больше кэша, который он держит - кэш лежит в
#: куче Go, и рядом с каждым куском живёт его копия в работе (readahead) плюс мусор,
#: который сборщик забирает уже после. Прибитые 4 ГиБ «половина от 8 ГиБ памяти»
#: половиной не были: 4 ГиБ кэша - 7.45 ГБ RSS при потолке 8 ГБ, и машина вставала колом
#: на четвёртой минуте показа. Отсюда делитель ниже.
#: Две далеко разнесённые головы чтения по одной раздаче (живая упаковка и прогрев)
#: держат занятыми оба конца кэша, поэтому запас «на одну голову» не годится.
TS_MEM_OVERHEAD=2
#: МиБ, которые НЕ отдаём под кэш: сама система, python показа, два ffmpeg, сегменты в
#: /dev/shm. Замер под показом с прогревом: 0.5-1.2 ГиБ, берём с запасом.
TS_MEM_RESERVE=1792
#: Нижняя и верхняя границы кэша. Нижняя - чтобы на 4-гигабайтной машине осталось чем
#: кормить показ; верхняя - потому что дальше расти незачем: запас на обрыв уже часовой,
#: а память нужнее машине.
TS_CACHE_MIN=268435456
TS_CACHE_MAX=8589934592

# --- Версии соседей: пины ----------------------------------------------------
# TorrServer и Prowlarr ставятся не «последние какие есть», а те, на которых обвязка
# API проверена живьём. Свежий мажор соседа может молча сменить формат ответа - и
# сломается это уже у чужого человека на чистой машине, а не у нас.
#
# Как поднять версию: поменять тег в нужной строке ниже - и прогнать install.sh на
# чистой машине. Правка одна, оба пина лежат тут; самопроверка в конце установки
# скажет, годится ли новая версия.
# Разовое переопределение: TORRCAST_TS_VERSION=… TORRCAST_PL_VERSION=… ./install.sh
#
# Теги пишутся ровно так, как они названы у авторов: у TorrServer без «v», у
# Prowlarr с «v».
TS_VERSION="${TORRCAST_TS_VERSION:-MatriX.142.2}"
PL_VERSION="${TORRCAST_PL_VERSION:-v2.5.2.5491}"

# Индексеры: definitionName в схеме Prowlarr + базовый URL. Только открытые: ни
# регистрации, ни капчи, ни ключа - трекеры с логином здесь не появятся принципиально.
# Knaben - метапоиск (агрегирует чужие каталоги и отдаёт infoHash), остальные прямые.
# Недоступный из этой сети индексер просто не добавится и работать не помешает.
INDEXERS=(
    "Knaben|https://knaben.org/"       # метапоиск: широкий хвост каталога
    "rutor|https://rutor.info/"        # русские раздачи и озвучки
    "nyaasi|https://nyaa.si/"          # аниме
    # У YTS адрес API отдельной настройкой, и умолчание там - имя, которое в этой сети
    # угоняет DNS (чужой адрес с самоподписанным сертом). Живое имя одно, оба его адреса
    # отвечают 200 за 0.9-1.4 с, но тело рвётся на объёме - см. строку в SHIMS.
    "yts|https://yts.gg/|apiurl=yts.gg"
)
# Индексеры, которые НЕ держат установку: доводятся в фоне, уже после «готово». Prowlarr
# сопровождает добавление пробным обращением к трекеру и ждёт его до своего таймаута -
# замер: 100.06 с на одном yts, и `forceSave=true` его не отключает (проверено живьём).
# Ждать этого человеку незачем: yts не закрывает в пуле ни одной дыры - +2.1% раздач и
# НОЛЬ запросов, где он единственный источник играбельного HD (кириллицы у него нет,
# сериалов нет). Ключевой индексер сюда не попадает никогда: его непроход обязан быть
# виден в самой установке словами, а не найден потом в журнале.
LATE_INDEXERS=("yts")
# На этом индексере держится примерно половина каталога - весь западный хвост и аниме:
# прямые трекеры из списка его не перекрывают, замены среди метапоисков в открытом пуле
# нет. Поиск без него продолжает работать (деградируем, а не умираем), но выдача
# заметно беднее - поэтому его непроход обязан быть виден словами, а не строкой в общем
# потоке. То же состояние показывает `cast doctor`.
KEY_INDEXER="Knaben"
# Список короткий не по лени: пул прочёсан целиком и машинно. В схеме Prowlarr 622
# определения, из них открытых (privacy=public) - 86, и каждое прощупано с той самой
# машины, где стоит torrcast: базовый адрес плюс все зеркала из схемы (74 адреса на
# интересных для кино определениях), потом добавление в Prowlarr и живые поиски.
# Итог прочёса: отвечают целиком 17, из них годных для кино - ноль сверх взятых.
# Куда делись остальные 69:
#   * 51 не отвечает - тело обрывается на первых ~14 КБ и висит до таймаута. Это блок
#     по ИМЕНИ в TLS, и обойти его нашим шимом нельзя: почти все сидят за CDN, который
#     без имени в рукопожатии просто не отвечает (проверено обращением на IP origin'а -
#     из 53 сработал ровно один, и тот из списка ниже). Так лежат eztv, uindex, filemood,
#     torrent9, megapeer, opensharing, tokyotosho, dmhy, mikan, Anidex, nekobt, u3c3,
#     torrentkitty, rintornet, newstudio, torrent-pirat и прочие.
#   * 15 встречают JS-проверкой браузера (Cloudflare «Just a moment», DDoS-Guard):
#     1337x, LimeTorrents, KickassTorrents, The Pirate Bay, TorrentDownloads, magnetcat,
#     TorrentProject2, zamundarip, 52bt, torrentcore, blueroms, btetree, extratorrent.
#     Headless-браузер ради них не городим - это уже не установка одним скриптом.
#   * остальные отвечают, но каталога не добавляют: internetarchive заводится, только
#     каждый поиск у него 16-30 с (штатный поиск - 1-3 с) и на контрольных названиях он
#     не нашёл ничего; magnetdownload, 0magnet, bangumi-moe, nipponsei, showrss в
#     Prowlarr виснут до таймаута на 4 поисках из 5; anisource, Catorrent и
#     TorrentProject2 отвечают быстро и пусто; sosulki и byrutor живы и быстры, но у
#     первого две раздачи на пять запросов, а второй - каталог игр («Сталкер» у него
#     про GSC Game World); TorrentsCSV отвечает за долю секунды из консоли, но в
#     Prowlarr примерно каждый десятый поиск висит до таймаута, а один такой индексер
#     задерживает весь поиск; NZBIndex - usenet, а мы качаем торренты.
#   * ACG.RIP отрезает часть сетей на уровне TCP (:443 обрывается мгновенно, из других
#     сетей отвечает) - обход означал бы возить трафик через чужую страну, а установка
#     обязана работать из коробки без таких костылей. По той же причине не взят
#     torrent.by: он единственный, кого шим бы вытащил, но и по имени, и через шим он
#     отдаёт пустую страницу.
# Трекеры с логином, капчей или ключом сюда не попадают ни при каких условиях, а
# semi-private (59 определений) не рассматриваются вовсе: там регистрация.

PHASES="${TORRCAST_PHASES:-locale packages torrcast torrserver sources prowlarr indexers config hls facts motd}"

#: Локаль. Без UTF-8 в системе консоль крошит кириллицу: русское название приезжает
#: в `cast` битым ещё до разбора аргументов. Целью берём ru_RU.UTF-8: в C.UTF-8 строки
#: сравниваются побайтно, и русские названия в списках выстраиваются не по алфавиту
#: («Ёлки» после «Яги»). Своя задаётся TORRCAST_LOCALE.
LOCALE="${TORRCAST_LOCALE:-ru_RU.UTF-8}"
#: Куда честно отступаем, если цель не собралась: C.UTF-8 есть в любой современной glibc
#: и не тянет за собой переводы. Сортировка станет побайтной, кириллица останется целой.
LOCALE_FALLBACK="${TORRCAST_LOCALE_FALLBACK:-C.UTF-8}"

#: Приветствие при входе по ssh. Печатает его pam_motd, поэтому файл кладём целиком.
MOTD_FILE="${TORRCAST_MOTD:-/etc/motd}"
#: Где приветствие собирается динамически (Ubuntu): pam_motd прогоняет этот каталог по
#: именам, а статический файл печатает уже после него. Есть каталог - кладём скрипт в него.
MOTD_D="${TORRCAST_MOTD_D:-/etc/update-motd.d}"

# Выгрузка оценок IMDb под справку в меню франшизы (torrcast/facts.py). Открытая,
# без ключа и регистрации, обновляется у них ежедневно; 8.6 МБ в архиве.
IMDB_RATINGS_URL="${TORRCAST_IMDB_RATINGS_URL:-https://datasets.imdbws.com/title.ratings.tsv.gz}"
IMDB_RATINGS_PATH="${TORRCAST_IMDB_RATINGS_PATH:-/var/lib/torrcast/imdb-ratings.tsv}"
# Ниже скольких голосов оценку не берём. Не вкусовщина, а размер: с порогом файл
# худеет с 30 МБ до 2 (106 тысяч строк вместо полутора миллионов), а всё, что человек
# станет искать в торрентах, набирает тысячи голосов с запасом.
IMDB_MIN_VOTES="${TORRCAST_IMDB_MIN_VOTES:-1000}"

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
    'nyaa.si|/?f=0&c=0_0&q=naruto||direct'
    'rutor.info|/search/matrix||direct'
    # У этого запасного имени нет, а без имени в рукопожатии его CDN отвечает 403 с обоих
    # адресов (замер, 0.1 с) - отсюда `named`. Ходить через шим ему нужно ради сжатия:
    # голая выдача этой пробы обрывается на 15 КБ и висит до таймаута, а сжатая - 4.8 КБ
    # и целиком за 0.9 с. Prowlarr сжатия не просит, шим просит за него.
    'yts.gg|/api/v2/list_movies.json?query_term=matrix&limit=50||named'
)
#: Нужно ли засеивать определения индексеров руками - решает фаза `sources`.
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
# Для того, что установку не роняет, но заметно урезает результат: обычная строка
# info тонет в потоке установки, а это надо увидеть.
loud() { printf '\033[1;33mвнимание:\033[0m %s\n' "$*" >&2; }
has()  { [[ " $PHASES " == *" $1 "* ]]; }

need_root() {
    [ -n "${TORRCAST_NO_ROOT:-}" ] && return 0
    [ "$(id -u)" -eq 0 ] || die "запускать от root: sudo ./install.sh"
}

# Маска процесса для pgrep -f/pkill -f. Голая строка запуска шаблоном не годится: она
# ищется как регулярка в ЛЮБОМ месте командной строки, поэтому под неё попадает чужой
# процесс, который наш путь всего лишь упоминает в аргументах - редактор с открытым
# файлом, grep по нему, less по логу. Прибиваем к началу строки запуска и требуем
# границу слова в конце, а метасимволы (точки в путях, скобки) экранируем.
proc_mask() {  # $1 - начало строки запуска; печатает шаблон для -f
    printf '^%s( |$)' "$(printf '%s' "$1" | sed 's/[][^$.*+?(){}|\]/\\&/g')"
}

# Память ЭТОЙ машины, байты. Не только /proc/meminfo: под cgroup (контейнер, LXC) машине
# видно больше, чем ей на деле дадут, - берём меньшее из двух. Ошибиться тут дорого:
# именно на разнице между «памятью в meminfo» и реальным потолком контейнер и вставал.
host_memory() {
    local mem lim
    mem=$(( $(awk '/^MemTotal:/{print $2}' /proc/meminfo) * 1024 ))
    while read -r lim; do
        case "$lim" in ''|*[!0-9]*) continue ;; esac
        [ "$lim" -gt 0 ] && [ "$lim" -lt "$mem" ] && mem="$lim"
    done <<EOF
$(cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null)
EOF
    printf '%s' "$mem"
}

# Сколько памяти позволено самой службе раздачи, байты: всё, кроме запаса на остальных.
ts_mem_budget() {
    local budget
    budget=$(( $(host_memory) - TS_MEM_RESERVE * 1024 * 1024 ))
    [ "$budget" -lt $(( TS_CACHE_MIN * TS_MEM_OVERHEAD )) ] \
        && budget=$(( TS_CACHE_MIN * TS_MEM_OVERHEAD ))
    printf '%s' "$budget"
}

# Размер кэша раздачи, байты: бюджет службы, делённый на замеренный перерасход.
ts_cache_size() {
    local cache
    cache=$(( $(ts_mem_budget) / TS_MEM_OVERHEAD ))
    [ "$cache" -lt "$TS_CACHE_MIN" ] && cache="$TS_CACHE_MIN"
    [ "$cache" -gt "$TS_CACHE_MAX" ] && cache="$TS_CACHE_MAX"
    printf '%s' "$cache"
}

# Служба: в системе — юнит systemd, в песочнице — просто фоновый процесс,
# чтобы фазы проверялись живьём, а не «как будто».
run_service() {  # $1 имя, $2 описание, $3 команда, $4 - лишние строки секции [Service]
    if [ -n "${TORRCAST_NO_SYSTEMD:-}" ]; then
        pgrep -f -- "$(proc_mask "$3")" >/dev/null 2>&1 \
            && { skip "процесс $1 (песочница)"; return 0; }
        info "запускаю $1 фоном (песочница)"
        # Потолки памяти в песочнице ставит не systemd, поэтому Environment= разбираем
        # сами: без них служба в песочнице росла бы иначе, чем в системе, и замер
        # песочницы ничего бы не говорил о живой машине. Строки MemoryMax= тут нечему
        # применить - в песочнице cgroup своего юнита нет.
        local line
        while IFS= read -r line; do
            case "$line" in Environment=*) export "${line#Environment=}" ;; esac
        done <<EOF
${4:-}
EOF
        # shellcheck disable=SC2086
        setsid nohup $3 >"$PREFIX/$1.log" 2>&1 </dev/null &
        return 0
    fi
    # Изменившийся юнит - это не только daemon-reload: `enable --now` уже поднятую
    # службу не перезапустит, и она осталась бы жить со СТАРЫМИ потолками памяти. На
    # чистой машине перезапускать нечего, на обновлении - обязательно.
    # ⚠️ Поэтому спрашиваем ДО правки юнита, работала ли служба. Рестарт того, что
    # `enable --now` секунду назад подняло само, не просто лишний: он глушит службу
    # посреди её первого запуска, а systemd ждёт остановки до TimeoutStopSec. Prowlarr в
    # этот момент раскатывает свою базу и на SIGTERM не отзывается - замер на чистой
    # машине: 90 секунд установки ровно тут, на ожидании SIGKILL.
    local fresh=0 was_up=0
    systemctl is-active --quiet "$1.service" && was_up=1
    write_unit "$1" "$2" "$3" "${4:-}" && fresh=1
    systemctl enable --now "$1.service"
    [ "$fresh" = 1 ] && [ "$was_up" = 1 ] && systemctl restart "$1.service"
    return 0
}

# Погасить службу, чтобы следующий run_service поднял её заново: `enable --now` и
# pgrep в песочнице живой процесс не трогают, а после обновления кода это и нужно.
stop_service() {  # $1 имя, $2 начало строки запуска для песочницы
    if [ -n "${TORRCAST_NO_SYSTEMD:-}" ]; then
        pkill -f -- "$(proc_mask "$2")" >/dev/null 2>&1 || true
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

# Скачивание из сети - с повторами. Канал моргает: одна и та же ссылка отдаёт то
# файл, то отказ на рукопожатии TLS («self-signed certificate» на github.com -
# поймано на чистой машине, следующая же попытка прошла). Установка обязана
# переживать такое сама: без этого один моргнувший байт роняет весь заход.
DL_TRIES="${TORRCAST_DL_TRIES:-4}"
fetch() {  # $@ - аргументы curl; возвращает код последней попытки
    local i=1
    while :; do
        curl -fsSL --retry 2 --retry-connrefused --connect-timeout 20 "$@" && return 0
        [ "$i" -ge "$DL_TRIES" ] && return 1
        # В stderr, а не в stdout: вывод fetch бывает и телом ответа, которое тут же
        # читает jq - строка про повтор посреди JSON ломала бы разбор.
        info "не скачалось (попытка $i из $DL_TRIES) - пробую снова" >&2
        sleep $((i * 3))
        i=$((i + 1))
    done
}

# Описание релиза с GitHub: сначала пиненный тег, и только если его там больше нет -
# latest, вслух и с предупреждением. Пропавший тег (снесли, переименовали) не должен
# останавливать установку: живая незнакомая версия полезнее мёртвой установки, а
# несовместимость поймает самопроверка в конце - падение будет честным и с адресом.
# Печатает JSON в stdout, все свои слова - в stderr, иначе jq подавится.
gh_release() {  # $1 - владелец/репозиторий, $2 - тег пина, $3 - имя для сообщений
    local api="https://api.github.com/repos/$1/releases" body code
    body="$(mktemp)"
    code="$(curl -fsSL --retry 2 --retry-connrefused --connect-timeout 20 \
                 -o "$body" -w '%{http_code}' "$api/tags/$2" 2>/dev/null)" || true
    if [ "$code" = 200 ] && [ -s "$body" ]; then
        cat "$body"; rm -f "$body"; return 0
    fi
    rm -f "$body"
    info "⚠ $3: пиненная версия $2 недоступна на GitHub (ответ ${code:-нет}) - беру latest" >&2
    info "⚠ версия непроверенная; если обвязка API не сойдётся - установка упадёт ниже" >&2
    fetch "$api/latest"
}

# --- 0. Локаль --------------------------------------------------------------

# `locale -a` печатает имена в своём написании (`c.utf8`, `ru_RU.utf8`), поэтому
# сравниваем приведёнными: без регистра и без дефисов.
locale_key() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -d '-'; }

locale_present() {  # $1 - имя локали
    local want line
    want="$(locale_key "$1")"
    while read -r line; do
        [ "$(locale_key "$line")" = "$want" ] && return 0
    done < <(locale -a 2>/dev/null)
    return 1
}

# Собрать локаль, если её ещё нет. Возвращает 0, только когда после всех попыток она
# реально есть в системе: собрать может быть нечем (нет ни locale-gen, ни localedef -
# так бывает на урезанных образах), и это штатная ветка, а не ошибка.
locale_build() {  # $1 - имя локали
    locale_present "$1" && return 0
    if ! command -v locale-gen >/dev/null 2>&1 && ! command -v localedef >/dev/null 2>&1; then
        apt-get update -qq
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq locales
    fi
    if ! locale_present "$1" && [ -f /etc/locale.gen ] \
        && command -v locale-gen >/dev/null 2>&1; then
        info "собираю $1 через locale-gen"
        grep -qE "^[[:space:]]*$1([[:space:]]|\$)" /etc/locale.gen \
            || printf '%s %s\n' "$1" "${1#*.}" >> /etc/locale.gen
        locale-gen >/dev/null 2>&1 || true
    fi
    if ! locale_present "$1" && command -v localedef >/dev/null 2>&1; then
        info "собираю $1 через localedef"
        localedef -i "${1%%.*}" -f "${1#*.}" "$1" >/dev/null 2>&1 || true
    fi
    locale_present "$1"
}

# Приводим систему к UTF-8. Идемпотентно: собранную локаль не пересобираем, готовую
# строку в конфигах не переписываем.
setup_locale() {
    log "локаль UTF-8 ($LOCALE)"
    locale_build "$LOCALE" || true
    # Цель не вышла - отступаем на C.UTF-8, и вслух: русская сортировка пропадёт, но
    # показывать это как успех нельзя.
    if ! locale_present "$LOCALE" && [ "$LOCALE" != "$LOCALE_FALLBACK" ]; then
        info "$LOCALE в этой системе не собралась - беру $LOCALE_FALLBACK, сортировка будет побайтной"
        LOCALE="$LOCALE_FALLBACK"
        locale_build "$LOCALE" || true
    fi
    # Не вышло и с ней - берём любую готовую UTF-8: кириллица в консоли важнее, чем
    # конкретное имя локали.
    if ! locale_present "$LOCALE"; then
        local ready; ready="$(locale -a 2>/dev/null | grep -i -m1 'utf-\?8$' || true)"
        [ -n "$ready" ] || die "в системе нет ни одной UTF-8 локали и собрать её не вышло"
        info "$LOCALE не собралась - беру готовую $ready"
        LOCALE="$ready"
    fi

    # Вход по ssh берёт LANG отсюда (pam_env с envfile=/etc/default/locale).
    if [ "$(sed -n 's/^LANG=//p' /etc/default/locale 2>/dev/null | head -1)" = "$LOCALE" ]; then
        skip "LANG=$LOCALE в /etc/default/locale"
    elif command -v update-locale >/dev/null 2>&1; then
        update-locale "LANG=$LOCALE"
        info "LANG=$LOCALE → /etc/default/locale"
    else
        printf 'LANG=%s\n' "$LOCALE" > /etc/default/locale
        info "LANG=$LOCALE → /etc/default/locale"
    fi
    # Подстраховка для систем, где строки с envfile в pam.d нет: /etc/environment
    # pam_env читает всегда.
    if ! grep -qs "^LANG=$LOCALE\$" /etc/environment; then
        [ -f /etc/environment ] && sed -i '/^LANG=/d' /etc/environment
        printf 'LANG=%s\n' "$LOCALE" >> /etc/environment
    fi
    export LANG="$LOCALE"
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
#: Запасной источник на ДРУГОМ хосте (не GitHub): если BtbN недоступен целиком (блок,
#: снятый релиз) - берём портативную статическую сборку jellyfin-ffmpeg. Это своя сборка
#: проекта, не johnvansickle, и на MPEG-TS её всё равно проверяет ffmpeg_smoke ниже.
FFMPEG_URL2="${TORRCAST_FFMPEG_URL2:-https://repo.jellyfin.org/files/ffmpeg/linux/latest-7.x/amd64/jellyfin-ffmpeg_7.1.4-3_portable_linux64-gpl.tar.xz}"

ffmpeg_version() {  # $1 — путь/имя бинаря; печатает голую версию либо ничего
    "$1" -version 2>/dev/null | head -1 | awk '{print $3}' | sed 's/^[^0-9]*//'
}

# Проверка сборки в деле, а не по строчке версии: пакуем секунду MPEG-TS (наш формат)
# и читаем её обратно. Segfault ловится здесь, а не на живом показе.
ffmpeg_smoke() {  # $1 — каталог для файла, $2/$3 — ffmpeg/ffprobe (по умолчанию свои)
    local clip="$1/smoke.ts" ff="${2:-/usr/local/bin/ffmpeg}" fp="${3:-/usr/local/bin/ffprobe}"
    "$ff" -hide_banner -loglevel error -y \
        -f lavfi -i "testsrc=size=320x240:rate=25:duration=1" -f lavfi -i "sine=duration=1" \
        -c:v libx264 -pix_fmt yuv420p -preset ultrafast -c:a aac -f mpegts "$clip" || return 1
    "$fp" -v error -show_entries stream=codec_name -of csv "$clip" >/dev/null || return 1
    info "сборка проверена: MPEG-TS пакуется и читается"
}

#: Сборка из snap проходит проверку по версии, а конфайнмент не пускает её ни в каталог
#: пакета, ни в состояние, ни в /dev/shm с сегментами: установка отчитывается зелёным,
#: а показ разваливается на первом же файле. Такой ffmpeg считаем негодным независимо
#: от версии - и ставим свою статическую сборку.
ffmpeg_confined() {  # $1 — имя/путь бинаря; 0 = заперт в снапе
    local real; real="$(readlink -f "$(command -v -- "$1" 2>/dev/null || true)" 2>/dev/null || true)"
    case "$real" in
        /snap/*|/var/lib/snapd/*) return 0 ;;
        *) return 1 ;;
    esac
}

#: Уже стоящую свою сборку спрашиваем ПО ПУТИ, а не по PATH: на PATH её заслоняет
#: любой другой ffmpeg (снап, пакетный), и повторный заход качал бы те же десятки
#: мегабайт заново. Проверка та же, что и для чужой сборки: версия плюс MPEG-TS в деле,
#: то есть «уже на месте» говорится только про годный бинарь.
#: ⚠️ Спрашивать версию у отсутствующего файла нельзя: под `set -e` установка оборвётся
#: на коде 127 - отсюда проверка на -x до вопроса.
ffmpeg_ours_ok() {  # 0 = /usr/local/bin/ffmpeg на месте, годной версии и живой
    [ -x /usr/local/bin/ffmpeg ] && [ -x /usr/local/bin/ffprobe ] || return 1
    local mine probe rc=1
    mine="$(ffmpeg_version /usr/local/bin/ffmpeg || true)"
    [ -n "$mine" ] || return 1
    dpkg --compare-versions "$mine" ge "$FFMPEG_MIN" 2>/dev/null || return 1
    probe="$(mktemp -d)"
    # Строку про пройденный MPEG-TS уводим в stderr: stdout тут - это версия, которую
    # читает вызывающий, и чужая строка в нём стала бы «версией».
    ffmpeg_smoke "$probe" /usr/local/bin/ffmpeg /usr/local/bin/ffprobe >&2 && rc=0
    rm -rf "$probe"
    [ "$rc" = 0 ] || return 1
    printf '%s' "$mine"
}

install_ffmpeg() {
    local have reject="" mine
    # Своя сборка уже стоит - ничего не качаем. Переставить принудительно: удалить
    # /usr/local/bin/ffmpeg (так же переставляются TorrServer и Prowlarr) и запустить
    # установку снова.
    if mine="$(ffmpeg_ours_ok)"; then
        skip "статическая сборка ffmpeg $mine в /usr/local/bin \
(переставить - удали файл и запусти снова)"
        return
    fi
    # `|| true` не для красоты: ffmpeg на PATH может не быть вовсе (в репозитории он
    # заведомо стар, и мы его не ставили), а под `set -e` пустой ответ отсюда оборвал бы
    # установку на коде 127.
    have="$(ffmpeg_version ffmpeg || true)"
    if [ -n "$have" ] && ffmpeg_confined ffmpeg; then
        info "ffmpeg $have из snap: в $PREFIX, $STATE_DIR и $HLS_DIR его конфайнмент \
не пустит - беру статическую сборку"
        reject=1
    fi
    if [ -z "$reject" ] && [ -n "$have" ] \
        && dpkg --compare-versions "$have" ge "$FFMPEG_MIN" 2>/dev/null; then
        # Версия - только полдела: проверяем найденный на PATH бинарь в деле, тем же
        # MPEG-TS, что и свою сборку. Не пережил - ставим свою.
        local ff fp probe
        ff="$(command -v ffmpeg)"; fp="$(command -v ffprobe || true)"
        probe="$(mktemp -d)"
        if [ -n "$fp" ] && ffmpeg_smoke "$probe" "$ff" "$fp"; then
            rm -rf "$probe"
            skip "ffmpeg $have (нужно ≥ $FFMPEG_MIN: -readrate_initial_burst)"
            return
        fi
        rm -rf "$probe"
        info "ffmpeg $have не прошёл проверку MPEG-TS - беру статическую сборку"
        reject=1
    fi
    [ "$(uname -m)" = "x86_64" ] || die "статической сборки ffmpeg под $(uname -m) нет — \
поставь ffmpeg ≥ $FFMPEG_MIN сам"
    info "ffmpeg ${have:-нет} — беру статическую сборку"
    # Каталог убираем сами: `trap ... RETURN` без `set -T` цепляется ко ВСЕМ функциям
    # сразу и падает на первом же чужом return («work: unbound variable»).
    local work; work="$(mktemp -d)"
    # Идём по источникам на разных хостах: первый отдавший годный архив с бинарём и
    # побеждает. Так падение одного хоста (BtbN снят/заблокирован) не валит установку.
    local url bin=""
    for url in "$FFMPEG_URL" "$FFMPEG_URL2"; do
        [ -n "$url" ] || continue
        info "качаю статический ffmpeg: ${url#https://}"
        if fetch -o "$work/ffmpeg.tar.xz" "$url" \
            && tar -xf "$work/ffmpeg.tar.xz" -C "$work" 2>/dev/null \
            && bin="$(find "$work" -type f -name ffmpeg -perm -u+x | head -1)" \
            && [ -n "$bin" ]; then
            break
        fi
        info "источник не дал годного архива: ${url#https://} - пробую следующий"
        rm -rf "${work:?}"/* 2>/dev/null || true
        bin=""
    done
    [ -n "$bin" ] || die "статическую сборку ffmpeg не удалось получить ни с одного источника"
    install -d -m 0755 /usr/local/bin
    install -m 0755 "$bin" /usr/local/bin/ffmpeg
    install -m 0755 "$(dirname "$bin")/ffprobe" /usr/local/bin/ffprobe
    hash -r
    local now; now="$(ffmpeg_version /usr/local/bin/ffmpeg)"
    dpkg --compare-versions "$now" ge "$FFMPEG_MIN" 2>/dev/null \
        || die "поставился ffmpeg $now — это всё ещё ниже $FFMPEG_MIN"
    ffmpeg_smoke "$work" || die "сборка ffmpeg $now не пережила MPEG-TS — другой URL"
    rm -rf "$work"
    local packaged; packaged="$(ffmpeg_version /usr/bin/ffmpeg || true)"
    info "ffmpeg $now → /usr/local/bin${packaged:+ (пакетная $packaged осталась)}"
}

# Версия ffmpeg, которую отдаст apt этой системы, - голая, без эпохи и ревизии
# дистрибутива. Эпоху отрезать обязательно: у Debian это `7:5.1.6-0+deb12u1`, и
# `dpkg --compare-versions` честно скажет, что 7:5.1.6 больше 6.1 - сравнивая эпохи, а
# не то, что нам нужно. Ничего не печатает, если пакета в репозитории нет вовсе.
# ⚠️ LC_ALL=C обязателен: фаза `locale` уже включила русскую локаль, и apt печатает
# «Кандидат:» вместо «Candidate:» - разбор молча возвращал пустоту, а установка тянула
# ненужный пакет ffmpeg (пойман замером: минута на пустом месте).
apt_candidate_version() {  # $1 - имя пакета
    LC_ALL=C apt-cache policy "$1" 2>/dev/null |
        sed -n 's/^ *Candidate: *//p' | head -1 |
        sed 's/^[0-9]*://; s/-.*//; s/^(none)$//'
}

install_packages() {
    log "зависимости"
    local want=() missing=() pkg updated=0
    # Пакетный ffmpeg берём, только если он годен: он тут запасной аэродром, чтобы не
    # качать статическую сборку там, где системный уже свежее нижней границы (Ubuntu
    # 24.04 - 6.1.1). Где он заведомо стар (Debian 12 - 5.1), ставить его незачем:
    # статическую сборку мы всё равно возьмём, а он тянет за собой полторы сотни пакетов.
    # Замер на чистой Debian 12: apt с ffmpeg - 55 с, без него - 9 с, и ни один из этих
    # пакетов дальше не нужен.
    # На пустой машине списки apt ещё не скачаны и версии не видно - тогда обновляем их
    # прямо здесь (позже они всё равно понадобятся) и спрашиваем ещё раз.
    local apt_ff; apt_ff="$(apt_candidate_version ffmpeg)"
    if [ -z "$apt_ff" ] && ! dpkg -s ffmpeg >/dev/null 2>&1; then
        apt-get update -qq; updated=1
        apt_ff="$(apt_candidate_version ffmpeg)"
    fi
    for pkg in "${APT_PACKAGES[@]}"; do
        if [ "$pkg" = ffmpeg ] && [ -n "$apt_ff" ] \
            && ! dpkg -s ffmpeg >/dev/null 2>&1 \
            && ! dpkg --compare-versions "$apt_ff" ge "$FFMPEG_MIN" 2>/dev/null; then
            info "в репозитории ffmpeg $apt_ff (нужно ≥ $FFMPEG_MIN) - пакет не ставлю, \
беру статическую сборку"
            continue
        fi
        want+=("$pkg")
    done
    for pkg in "${want[@]}"; do
        dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done
    if [ ${#missing[@]} -eq 0 ]; then
        skip "apt-пакеты (${want[*]})"
    else
        [ "$updated" = 1 ] || apt-get update -qq
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
install_torrserver() {
    local budget
    TS_CACHE="${TORRCAST_TS_CACHE:-$(ts_cache_size)}"
    budget=$(( TS_CACHE * TS_MEM_OVERHEAD ))
    log "TorrServer ($TS_URL, кэш в RAM $((TS_CACHE / 1024 / 1024)) МиБ)"
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
        url="$(gh_release YouROK/TorrServer "$TS_VERSION" TorrServer \
            | jq -r --arg n "TorrServer-linux-$arch" \
                   '.assets[]|select(.name==$n)|.browser_download_url')" || url=""
        [ -n "$url" ] && [ "$url" != null ] \
            || die "не нашёл сборку TorrServer-linux-$arch (пин $TS_VERSION, latest тоже не отдал)"
        info "качаю $url"
        fetch -o "$PREFIX/bin/TorrServer.new" "$url" || die "не скачался TorrServer: $url"
        chmod +x "$PREFIX/bin/TorrServer.new"
        mv "$PREFIX/bin/TorrServer.new" "$PREFIX/bin/TorrServer"
    fi

    # Два потолка вокруг кэша, и оба не для красоты.
    # GOMEMLIMIT - мягкий: он не запрещает расти, а заставляет сборщик мусора Go
    # работать раньше и чаще, и именно он снимает тот самый двукратный перерасход над
    # кэшем. Ставится по бюджету службы, то есть кэш живёт свободно, а всё лишнее
    # собирается, не дожидаясь, пока память кончится у машины.
    # MemoryMax - жёсткий, на случай, когда мягкого не хватило (кэш вырос сам, чужая
    # утечка, раздача с гигантским куском). Служба тогда умирает и поднимается заново
    # (Restart=on-failure): показ прервётся, но машина останется живой - а вставший колом
    # хозяин без ssh это ровно то, что мы чиним.
    run_service torrserver "TorrServer для torrcast" \
        "$PREFIX/bin/TorrServer --port $TS_PORT --ip $TS_HOST --path $PREFIX/torrserver" \
        "Environment=GOMEMLIMIT=${budget}B
MemoryMax=$(( budget + 256 * 1024 * 1024 ))
MemorySwapMax=0"
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
    info "кэш $((TS_CACHE / 1024 / 1024)) МиБ в RAM при $(( $(host_memory) / 1024 / 1024 )) МиБ памяти машины, потолок службы $((budget / 1024 / 1024)) МиБ, ретрекеры включены"
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
    # Маска - начало строки запуска, без маршрутов: у живого процесса они прежние, а
    # погасить надо именно его.
    [ "$changed" = 1 ] && stop_service torrcast-shim "$PYTHON $SHIM_DIR/sni-shim.py"
    run_service torrcast-shim "TLS-шим для трекеров, чьё имя не проходит по SNI" \
        "$PYTHON $SHIM_DIR/sni-shim.py $SHIM_DIR/shim.crt $SHIM_DIR/shim.key $SHIM_PORT ${routes[*]}"
}

# Пробы независимы, а каждая ждёт СВОЙ таймаут (до 25 с на трекер) - последовательно
# это набегало в минуту с лишним чистого ожидания на пустом месте. Гоняем их разом, а
# ответы разбираем потом и в исходном порядке: параллельность не должна превращать
# журнал установки в чересполосицу. Печатает каталог с файлами «имя» → код возврата.
#: Сколько раз проба через уже поднятый шим повторяется, прежде чем признать его
#: молчание: служба только что запущена, сокета может ещё не быть.
SHIM_PROBE_TRIES=12
#: ⚠️ Повторяем только МГНОВЕННЫЕ провалы - те, ради которых лестница и заведена: пока
#: сокета нет, проба падает за доли секунды. Проба, отвисевшая свои 25 секунд, говорит
#: обратное: шим на месте, а хост через него не отвечает, - и одиннадцать повторов по 25
#: секунд ничего не меняют, только держат человека (замер повторного захода: nyaa.si -
#: 204 секунды ровно здесь, с тем же итогом). Порог с запасом на первое рукопожатие.
SHIM_PROBE_FAST=5
probe_all() {  # $1 - 1 = долбиться до ответа (через шим), 0 = одна проба; дальше строки SHIMS
    local retry="$1"; shift
    local dir spec host path body ups pids=()
    dir="$(mktemp -d)"
    for spec in "$@"; do
        IFS='|' read -r host path body ups <<<"$spec"
        # Код возврата уводим в файл, а сама подоболочка завершается успешно: под
        # `set -e` упавшая фоновая проба уронила бы установку на `wait`.
        (
            rc=1 i=0 began=0
            while :; do
                began="$SECONDS"
                if probe_whole "$host" "$path" "$body"; then rc=0; break; fi
                i=$((i + 1))
                { [ "$retry" = 1 ] && [ "$i" -lt "$SHIM_PROBE_TRIES" ] \
                    && [ $((SECONDS - began)) -lt "$SHIM_PROBE_FAST" ]; } || break
                sleep 1
            done
            printf '%s' "$rc" >"$dir/$host"
            true
        ) &
        pids+=("$!")
    done
    # Ждём поимённо: в песочнице рядом живут фоновые «службы», и голый `wait` завис бы
    # на них до скончания века.
    wait "${pids[@]}"
    printf '%s' "$dir"
}

check_sources() {
    log "источники: что доступно из этой сети"

    if curl -fsS -m 15 -o /dev/null "$PL_DEFS_URL" 2>/dev/null; then
        info "каталог индексеров Prowlarr доступен - он возьмёт определения сам"
    else
        # Без этой строки КАЖДЫЙ запрос схемы ждёт таймаута .NET — 100 секунд.
        info "⚠ каталог индексеров Prowlarr недоступен - определения возьмём с GitHub"
        hosts_pin indexers.prowlarr.com
        SEED_DEFS=1
    fi

    local spec host path body ups routes=() ask=() probes=""
    for spec in "${SHIMS[@]}"; do
        IFS='|' read -r host path body ups <<<"$spec"
        # Замер пошёл бы через уже стоящий шим и всегда отвечал бы «всё хорошо» - а
        # код из репы так бы и не доехал. Прибито - значит ведём через шим и дальше,
        # спрашивать нечего.
        pinned "$host" || ask+=("$spec")
    done
    if [ "${#ask[@]}" -gt 0 ]; then probes="$(probe_all 0 "${ask[@]}")"; fi
    for spec in "${SHIMS[@]}"; do
        IFS='|' read -r host path body ups <<<"$spec"
        if pinned "$host"; then
            info "$host уже за шимом - маршрут остаётся"
            routes+=("$host=$ups")
        elif [ "$(cat "$probes/$host" 2>/dev/null)" = 0 ]; then
            info "$host отвечает целиком - обход не нужен"
        else
            info "⚠ $host отдаёт ответ не целиком (режется по имени в SNI) - веду через шим"
            routes+=("$host=$ups")
        fi
    done
    if [ -n "$probes" ]; then rm -rf "$probes"; fi
    if [ "${#routes[@]}" -eq 0 ]; then
        info "все трекеры доступны по имени - шим не нужен"
        return
    fi
    setup_shim "${routes[@]}"

    # «Шим поднят» и «через него отвечает» - разные утверждения. Проверяем вторым
    # заходом: имя уже прибито к шиму, поэтому та же проба идёт сквозь него. Служба
    # только что запущена, сокета может ещё не быть - спрашиваем не один раз.
    local through=()
    for spec in "${SHIMS[@]}"; do
        IFS='|' read -r host path body ups <<<"$spec"
        printf '%s\n' "${routes[@]}" | grep -qx "$host=$ups" || continue
        through+=("$spec")
    done
    if [ "${#through[@]}" -eq 0 ]; then return 0; fi
    probes="$(probe_all 1 "${through[@]}")"
    for spec in "${through[@]}"; do
        IFS='|' read -r host path body ups <<<"$spec"
        if [ "$(cat "$probes/$host" 2>/dev/null)" = 0 ]; then
            info "через шим $host отвечает целиком"
        else
            info "⚠ $host не отвечает и через шим - его индексер останется пустым"
        fi
    done
    rm -rf "$probes"
}

# Определения индексеров (Cardigann) - из репы Prowlarr/Indexers на GitHub.
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
    if fetch -o "$tmp/defs.tar.gz" "$DEFS_TARBALL" \
       && tar -xzf "$tmp/defs.tar.gz" -C "$tmp" --wildcards '*/definitions/v11/*.yml'; then
        find "$tmp" -path '*/definitions/v11/*.yml' -exec install -m 0644 {} "$dir/" \;
        info "разложено $(find "$dir" -maxdepth 1 -name '*.yml' | wc -l) определений"
    else
        info "⚠ определения не скачались - останутся только встроенные индексеры"
    fi
    rm -rf "$tmp"
}

# --- 4. Prowlarr ------------------------------------------------------------
# Качаем с GitHub, как и TorrServer. Родной prowlarr.servarr.com части адресов отдаёт
# 403: зависеть от того, чей IP спрашивает, установка не должна. Сборка та же самая,
# версия совпадает. Запасной путь остался вторым.
PL_FALLBACK="${TORRCAST_PL_FALLBACK:-https://prowlarr.servarr.com/v1/update/master/updatefile?os=linux&runtime=netcore&arch=x64}"

install_prowlarr() {
    log "Prowlarr ($PL_URL, публичные индексеры)"
    install -d -m 0755 "$PREFIX/prowlarr-data"

    if [ -x "$PREFIX/prowlarr/Prowlarr" ]; then
        skip "бинарь Prowlarr"
    else
        local url
        url="$(gh_release Prowlarr/Prowlarr "$PL_VERSION" Prowlarr \
            | jq -r '[.assets[]?|select(.name|test("linux-core-x64\\.tar\\.gz$"))][0]
                     .browser_download_url // empty')" || url=""
        if [ -z "$url" ]; then
            info "GitHub сборку не отдал — иду на $PL_FALLBACK"
            url="$PL_FALLBACK"
        fi
        info "качаю $url"
        install -d -m 0755 "$PREFIX/prowlarr"
        fetch -o "$PREFIX/prowlarr.tar.gz" "$url" || die "не скачался Prowlarr: $url"
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
#: Проверочный поиск в конце фазы: чем спрашиваем и сколько ждём ОДИН индексер. Ждать
#: столько же, сколько ждёт сам Prowlarr (100 с у .NET), незачем: штатный поиск у живого
#: индексера занимает 1-3 секунды, а мёртвый не ответит и за сто. Взятые 25 - восьмикратный
#: запас к норме. Молчание за этот срок - не приговор индексеру, а честная строка в отчёте.
#: ⚠️ Спрашивать поимённо дороже, чем одним общим поиском: общий Prowlarr отдаёт мгновенно,
#: потому что молчащий индексер у него уже под штрафом и в опрос не попадает - то есть
#: «проверка» на повторном заходе не проверяла ровно то, ради чего затевалась.
PL_SEARCH_TIMEOUT="${TORRCAST_SEARCH_TIMEOUT:-25}"
PL_SEARCH_PROBE="${TORRCAST_SEARCH_PROBE:-матрица}"
#: Что доводится в фоне - строкой, которую печатает `main` сразу после «готово». Пусто -
#: догревать нечего, лишней строки не будет.
LATE_NOTE=""
#: Куда фоновое добавление пишет свой итог: установка к этому времени уже отчиталась, и
#: сказать «добавился» ей больше некуда.
LATE_LOG="${TORRCAST_LATE_LOG:-$STATE_DIR/late-indexers.log}"

late_indexer() {  # $1 - definitionName; 0 = добавляем в фоне, а не на глазах у человека
    # Ключевой не откладывается ни при каких условиях: фон не имеет права спрятать то,
    # без чего каталог наполовину пуст.
    [ "$1" = "$KEY_INDEXER" ] && return 1
    local late
    for late in "${LATE_INDEXERS[@]}"; do [ "$late" = "$1" ] && return 0; done
    return 1
}

# Добавить отложенные индексеры ПОСЛЕ выхода установки. Тела запросов уже собраны, так
# что подоболочке остаётся только сходить в свой Prowlarr - никакой сети, кроме той, что
# он дёрнет сам.
# ⚠️ Отвязываемся от установки по-настоящему: свои stdin/stdout/stderr в файл (иначе ssh,
# которым запускали установку, будет ждать закрытия трубы и «зависнет» после «готово») и
# игнор SIGHUP (иначе закрытая консоль убьёт нас на середине).
add_late() {  # $1 - apikey; дальше пары «имя<TAB>тело» строками на stdin
    local key="$1" pending
    pending="$(cat)"
    install -d -m 0755 "$(dirname "$LATE_LOG")"
    (
        trap '' HUP
        local iname ibody have
        while IFS=$'\t' read -r iname ibody; do
            [ -n "$iname" ] || continue
            # Между запуском и этой минутой мог пройти второй заход установки и добавить
            # его сам - тогда просто уходим, а не плодим второй такой же индексер.
            have="$(curl -fsS "$PL_URL/api/v1/indexer?apikey=$key" 2>/dev/null \
                | jq -r --arg n "$iname" 'any(.[]; .name==$n)' 2>/dev/null)" || have=""
            if [ "$have" = true ]; then
                printf '%s | %s уже на месте\n' "$(date '+%F %T')" "$iname"
                continue
            fi
            if curl -fsS -X POST "$PL_URL/api/v1/indexer?apikey=$key" \
                    -H 'Content-Type: application/json' -d "$ibody" >/dev/null 2>&1; then
                printf '%s | %s добавлен\n' "$(date '+%F %T')" "$iname"
            else
                printf '%s | %s не добавился (недоступен из этой сети?) - не блокер\n' \
                    "$(date '+%F %T')" "$iname"
            fi
        done <<<"$pending"
    ) >>"$LATE_LOG" 2>&1 </dev/null &
}

install_indexers() {
    [ "$SEED_DEFS" = 1 ] && seed_definitions
    log "индексеры Prowlarr"
    local key schema existing
    key="$(prowlarr_apikey)"
    [ -n "$key" ] || die "не вычитал apikey из config.xml Prowlarr"

    # Гейт версии: обвязка рассчитана на конкретный формат ответа Prowlarr. Если
    # поставилась версия, которая отвечает иначе (например, после отката пина на
    # latest), это должно быть видно здесь и словами, а не молчаливым выходом.
    schema="$(curl -fsS "$PL_URL/api/v1/indexer/schema?apikey=$key")" \
        || die "Prowlarr не отдал схему индексеров ($PL_URL/api/v1/indexer/schema) - API этой версии не тот, на который рассчитана установка"
    existing="$(curl -fsS "$PL_URL/api/v1/indexer?apikey=$key")" \
        || die "Prowlarr не отдал список индексеров ($PL_URL/api/v1/indexer)"
    jq -e 'type == "array" and length > 0 and all(.[]; has("definitionName"))' <<<"$schema" >/dev/null 2>&1 \
        || die "схема индексеров Prowlarr не в ожидаемом виде - API этой версии не тот, на который рассчитана установка"

    local spec def url extra over body name key_here=0
    local work pids=() queued=() late=()
    work="$(mktemp -d)"
    for spec in "${INDEXERS[@]}"; do
        IFS='|' read -r def url extra <<<"$spec"
        name="$(jq -r --arg d "$def" '.[]|select(.definitionName==$d)|.name' <<<"$schema")"
        if [ -z "$name" ] || [ "$name" = null ]; then
            info "⚠ $def нет в схеме этой версии Prowlarr - пропускаю"
            continue
        fi
        if jq -e --arg n "$name" 'any(.[]; .name==$n)' <<<"$existing" >/dev/null; then
            skip "индексер $name"
            [ "$def" = "$KEY_INDEXER" ] && key_here=1
            continue
        fi
        # Поля определения, которые перебиваем: базовый URL плюс то, что задано третьим
        # полем строки (`поле=значение`, через пробел). Остальные берутся из схемы как есть.
        over="$(jq -cn --arg u "$url" --arg e "${extra:-}" '
            ($e|split(" ")|map(select(length>0)|split("=")|{key:.[0],value:(.[1:]|join("="))})
             |from_entries) + {baseUrl:$u}')"
        body="$(jq -c --arg d "$def" --argjson o "$over" '
            .[]|select(.definitionName==$d)
            |{name,implementation,configContract,definitionName,priority,protocol,
              enable:true, appProfileId:1, tags:[], added:"0001-01-01T00:00:00Z",
              fields:[.fields[]|{name, value:(if $o[.name] != null then $o[.name] else .value end)}]}
        ' <<<"$schema")"
        # Тот, кому не место на критическом пути, уезжает в фон целиком (:func:`late_indexer`):
        # его тело собрано, а добавит его подоболочка уже после «готово».
        if late_indexer "$def"; then
            late+=("$(printf '%s\t%s' "$name" "$body")")
            continue
        fi
        # Добавление индексера Prowlarr сопровождает пробным обращением к трекеру и ждёт
        # его ДО СВОЕГО таймаута - у .NET это 100 секунд. Здесь остались те, ради кого
        # ждать стоит, и шлём мы их разом: очередь идёт по самому медленному, а не по
        # сумме. Ответы разбираем ниже и в исходном порядке.
        ( curl -fsS -X POST "$PL_URL/api/v1/indexer?apikey=$key" \
              -H 'Content-Type: application/json' -d "$body" >/dev/null 2>&1 \
            && printf 0 >"$work/add-$def" || printf 1 >"$work/add-$def"; true ) &
        pids+=("$!")
        queued+=("$def|$name")
    done
    if [ "${#pids[@]}" -gt 0 ]; then wait "${pids[@]}"; fi
    for spec in "${queued[@]}"; do
        IFS='|' read -r def name <<<"$spec"
        if [ "$(cat "$work/add-$def" 2>/dev/null)" = 0 ]; then
            info "добавлен $name"
            [ "$def" = "$KEY_INDEXER" ] && key_here=1
        else
            info "⚠ $name не добавился (недоступен из этой сети?) — не блокер"
        fi
    done

    # Живая проверка: «индексер заведён» и «поиск что-то находит» - разные утверждения.
    # Первое бывает правдой при неправде второго - например когда сеть режет индексер.
    # Отказ самой проверки установку не роняет: это отчёт, а не условие.
    # ⚠️ Спрашиваем КАЖДЫЙ индексер отдельно и разом, со своим таймаутом. Один общий
    # поиск отвечает по самому медленному: недоступный трекер держал ответ все 100
    # секунд .NET-таймаута, и проверка стоила дороже, чем половина установки. Теперь
    # молчание одного стоит $PL_SEARCH_TIMEOUT с и названо по имени.
    local list total=0 key_hits=0 key_answered=0 lines=() id iname n
    list="$(curl -fsS "$PL_URL/api/v1/indexer?apikey=$key")" || list='[]'
    info "индексеров сейчас: $(jq 'length' <<<"$list")"
    pids=()
    while IFS='|' read -r id def iname; do
        [ -n "$id" ] || continue
        ( curl -fsS -m "$PL_SEARCH_TIMEOUT" -G "$PL_URL/api/v1/search" \
              --data-urlencode "apikey=$key" --data-urlencode "query=$PL_SEARCH_PROBE" \
              --data-urlencode "type=search" --data-urlencode "limit=100" \
              --data-urlencode "indexerIds=$id" >"$work/search-$id" 2>/dev/null \
            || : >"$work/search-$id"; true ) &
        pids+=("$!")
    done < <(jq -r '.[]|"\(.id)|\(.definitionName)|\(.name)"' <<<"$list")
    if [ "${#pids[@]}" -gt 0 ]; then wait "${pids[@]}"; fi
    while IFS='|' read -r id def iname; do
        [ -n "$id" ] || continue
        n="$(jq 'length' <"$work/search-$id" 2>/dev/null)" || n=""
        if [ -z "$n" ]; then
            lines+=("    ⚠ $iname: не ответил за $PL_SEARCH_TIMEOUT с")
            continue
        fi
        lines+=("    $iname: $n")
        total=$((total + n))
        if [ "$def" = "$KEY_INDEXER" ]; then key_hits="$n"; key_answered=1; fi
    done < <(jq -r '.[]|"\(.id)|\(.definitionName)|\(.name)"' <<<"$list")
    rm -rf "$work"
    if [ "$total" -gt 0 ]; then
        info "проверочный поиск «$PL_SEARCH_PROBE»: $total раздач"
    else
        info "⚠ проверочный поиск НИЧЕГО не нашёл - индексеры недоступны из этой сети"
    fi
    if [ "${#lines[@]}" -gt 0 ]; then printf '%s\n' "${lines[@]}"; fi

    # Гейт веса: остальные индексеры друг друга подстраховывают, а этот - нет. Установку
    # не роняем (без него всё равно ищется), но и молчать нельзя: человек должен понимать,
    # что каталог у него урезан, а не гадать, почему западного кино и аниме не находится.
    if [ "$key_here" != 1 ]; then
        loud "$KEY_INDEXER не завёлся - каталог западных релизов и аниме будет неполным"
        info "поиск продолжит работать на остальных индексерах; повторный ./install.sh \
заведёт его, когда он снова будет доступен"
    elif [ "$key_answered" != 1 ]; then
        info "$KEY_INDEXER заведён, но проверить его нечем - он не ответил за $PL_SEARCH_TIMEOUT с"
    elif [ "${key_hits:-0}" -gt 0 ] 2>/dev/null; then
        info "$KEY_INDEXER отвечает: $key_hits раздач в проверочном поиске"
    else
        loud "$KEY_INDEXER заведён, но не отдал ничего - каталог западных релизов и аниме \
будет неполным"
        info "поиск продолжит работать на остальных индексерах; состояние видно в cast doctor"
    fi

    # Отложенные уходят в фон последними: к этой минуте всё, ради чего человек ждёт, уже
    # проверено и названо. Строку про них печатает `main` сразу после «готово» - обещать
    # готовность и молчать про догрев нельзя.
    if [ "${#late[@]}" -gt 0 ]; then
        printf '%s\n' "${late[@]}" | add_late "$key"
        local names=""
        for spec in "${late[@]}"; do names="$names${names:+, }${spec%%$'\t'*}"; done
        LATE_NOTE="в фоне доводится $names (минуты две) - поиск работает и без него, \
итог в $LATE_LOG и в cast doctor"
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
# Локаль службам задаём явно: systemd не наследует ни /etc/default/locale, ни
# /etc/environment, поэтому без Environment= процесс живёт в POSIX-локали - кириллица
# в его журнале и в именах файлов приезжает кракозябрами. Значение то же, которое
# выбрала фаза `locale`.
write_unit() {  # $1 имя, $2 описание, $3 команда, $4 - лишние строки секции [Service]
    local path="/etc/systemd/system/$1.service"
    local body
    body="$(cat <<UNIT
[Unit]
Description=$2
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=LANG=$LOCALE
${4:+$4
}ExecStart=$3
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
)"
    if [ -f "$path" ] && [ "$(cat "$path")" = "$body" ]; then
        skip "юнит $1.service"
        return 1
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

setup_facts() {
    log "справка к меню: оценки IMDb ($IMDB_RATINGS_PATH)"
    install -d -m 0755 "$(dirname "$IMDB_RATINGS_PATH")"
    # Свежее суток не перекачиваем: выгрузка обновляется раз в день, а качать 8.6 МБ
    # на каждый прогон установщика незачем.
    if [ -s "$IMDB_RATINGS_PATH" ] && [ -z "$(find "$IMDB_RATINGS_PATH" -mtime +0)" ]; then
        skip "$IMDB_RATINGS_PATH ($(wc -l < "$IMDB_RATINGS_PATH") оценок)"
        return
    fi
    local tmp="$IMDB_RATINGS_PATH.part"
    # Справка - украшение, а не механизм показа: не скачалось, режется по имени, нет
    # сети - установка идёт дальше, а меню просто печатается без рейтинга.
    if ! fetch --max-time 120 "$IMDB_RATINGS_URL" -o "$tmp.gz"; then
        rm -f "$tmp.gz"
        info "выгрузка IMDb не скачалась - меню будет без рейтинга, на показ не влияет"
        return
    fi
    if ! gzip -dc "$tmp.gz" | awk -F'\t' -v min="$IMDB_MIN_VOTES" \
        'NR==1 || $3+0 >= min { print $1 "\t" $2 "\t" $3 }' > "$tmp"; then
        rm -f "$tmp" "$tmp.gz"
        info "выгрузка IMDb битая - меню будет без рейтинга, на показ не влияет"
        return
    fi
    mv "$tmp" "$IMDB_RATINGS_PATH"
    rm -f "$tmp.gz"
    info "оценок: $(wc -l < "$IMDB_RATINGS_PATH") (от $IMDB_MIN_VOTES голосов)"
}

# Кто вошёл по ssh, должен сразу видеть, куда попал и что здесь спрашивать. Шпаргалка
# перечисляет ровно то, что понимает CLI (torrcast/cli.py) - выдуманных команд быть не
# должно, иначе приветствие врёт.
motd_banner() {
    printf '\033[1;32m'
    cat <<'ART'
 _                          _
| |_ ___  _ __ ___ __ _ ___| |_
| __/ _ \| '__/ __/ _` / __| __|
| || (_) | | | (_| (_| \__ \ |_
 \__\___/|_|  \___\__,_|___/\__|
ART
    printf '\n   торрент → ТВ без скачивания   ·   показ: cast <название>\n'
    printf '   cast status | stop | doctor | releases | voices'
    printf '   ·   ключи: --tv, --voice N, --new, --dry\n'
    printf '\033[0m\n'
}

setup_motd() {
    local target mode tmp
    tmp="$(mktemp)"
    if [ -d "$MOTD_D" ]; then
        # Динамическое приветствие печатается раньше статического файла, поэтому там, где
        # каталог есть, шпаргалка едет скриптом: иначе она уходит под дистрибутивный вывод
        # (справка, обновления, состояние диска). Номер 00 - первым в каталоге.
        # Статический файл в этой ветке не пишем: печатались бы оба, один под другим.
        target="$MOTD_D/00-torrcast"; mode=0755
        log "приветствие при входе ($target)"
        # Прежний заход мог положить шпаргалку в статический файл - её убираем, иначе
        # после перехода на скрипт она печаталась бы второй раз.
        if [ -f "$MOTD_FILE" ] && grep -qF 'cast status | stop | doctor' "$MOTD_FILE"; then
            : >"$MOTD_FILE"
            info "старое приветствие из $MOTD_FILE убрано - теперь его печатает скрипт"
        fi
        {
            printf '#!/bin/sh\n'
            printf '# приветствие torrcast; кладёт install.sh, печатает pam_motd при входе\n'
            printf "cat <<'TORRCAST_MOTD'\n"
            motd_banner
            printf 'TORRCAST_MOTD\n'
        } > "$tmp"
    else
        target="$MOTD_FILE"; mode=0644
        log "приветствие при входе ($target)"
        motd_banner > "$tmp"
    fi
    if cmp -s "$tmp" "$target"; then
        rm -f "$tmp"
        skip "$target"
        return
    fi
    install -m "$mode" "$tmp" "$target"
    rm -f "$tmp"
    info "приветствие обновлено"
}

main() {
    need_root
    has locale     && setup_locale
    has packages   && install_packages
    has torrcast    && install_torrcast
    has torrserver && install_torrserver
    has sources    && check_sources
    has prowlarr   && install_prowlarr
    has indexers   && install_indexers
    has config     && setup_config
    has hls        && setup_hls
    has facts      && setup_facts
    has motd       && setup_motd
    log "готово. Осталось: cast --tv - найдёт телевизоры в сети и спросит, который твой"
    # «Готово» сказано, когда `cast` и правда может играть. Если что-то ещё догревается -
    # это отдельная строка ПОСЛЕ него, а не задержка перед ним.
    if [ -n "$LATE_NOTE" ]; then info "$LATE_NOTE"; fi
}

main "$@"
