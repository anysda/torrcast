#!/bin/sh
# scripts/release.sh [--dry-run] <tag>   - публикация релиза torrcast, шесть шагов
# из TC-886. Тело одно: пайплайн зовёт его так же по тегу, только токен приедет
# из секретов, а не из окружения руками.
#
# 1. тег - semver (vX.Y.Z), и его коммит лежит на master
# 2. клон репы ПО ТЕГУ в mktemp -d (не рабочее дерево)
# 3. версия из тега - в дерево клона одной командой (scripts/set-version.py): version.py
#    (источник), install.sh, manifest.json интеграции Home Assistant, uv.lock. pyproject.toml
#    номер не хранит - hatchling берёт его динамически из version.py ([tool.hatch.version])
# 4. тарбол + sha256 + zip интеграции для HACS
# 5. Release на теге
# 6. четыре ассета (тарбол, sha256, install, zip) и сверка releases/latest снаружи
#
# --dry-run: 1-4 по-настоящему, 5-6 только печатает - так скрипт проверяем без
# токена и без права писать в GitHub.
set -eu

GITHUB_API="${TORRCAST_GITHUB_API:-https://api.github.com}"
GITHUB_UPLOADS="${TORRCAST_GITHUB_UPLOADS:-https://uploads.github.com}"
GITHUB_WEB="${TORRCAST_GITHUB_WEB:-https://github.com}"
PROJECT_PATH="${TORRCAST_PROJECT_PATH:-anysda/torrcast}"
GITHUB_REPO="${TORRCAST_GITHUB_REPO:-$GITHUB_WEB/$PROJECT_PATH.git}"

die()  { printf 'ошибка: %s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*" >&2; }
need() { command -v "$1" >/dev/null 2>&1 || die "нужен $1, его нет в PATH"; }

dry_run=0
tag=""
notes=""
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) dry_run=1 ;;
        --notes)
            shift
            [ $# -gt 0 ] || die "--notes нужен файл с описанием релиза"
            notes="$1"
            ;;
        -*) die "неизвестный флаг: $1" ;;
        *) tag="$1" ;;
    esac
    shift
done
[ -n "$tag" ] || die "нужен тег: scripts/release.sh [--dry-run] [--notes ФАЙЛ] vX.Y.Z"
[ -z "$notes" ] || [ -f "$notes" ] || die "файла с описанием нет: $notes"

# --- 1. тег: формат и предок master -----------------------------------------
check_tag_format() {  # $1 - тег
    printf '%s' "$1" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$' \
        || die "тег не semver: $1 (нужен vX.Y.Z)"
}

# --- 1+2. клон ПО ТЕГУ, с проверкой, что коммит лежит на master -------------
clone_at_tag() {  # $1 - каталог назначения, $2 - тег
    dst="$1" t="$2"
    git clone --quiet "$GITHUB_REPO" "$dst" || die "не клонируется $GITHUB_REPO"
    (
        cd "$dst"
        git rev-parse -q --verify "refs/tags/$t" >/dev/null 2>&1 \
            || die "тега $t нет в $GITHUB_REPO"
        git merge-base --is-ancestor "refs/tags/$t" origin/master \
            || die "тег $t не лежит на master"
        git checkout --quiet "$t"
    )
}

# --- 3. версия из тега в дерево клона -----------------------------------------
# Одна и та же команда держит версию в согласии и в рабочем дереве при обычной правке
# (TC), и здесь: своя копия подстановок означала бы два места, которые снова смогут
# разойтись, - ровно то, от чего этот выпуск и затевался.
substitute_version() {  # $1 - каталог клона, $2 - версия без v
    src="$1" ver="$2"
    ( cd "$src" && python3 scripts/set-version.py "$ver" ) \
        || die "версия $ver не разнеслась по дереву клона"
}

# --- 4. zip интеграции для HACS ----------------------------------------------
# В корне архива лежит СОДЕРЖИМОЕ `custom_components/torrcast` (manifest.json рядом с
# `__init__.py`), а не сам каталог: так собирает релизы сам HACS, и так их и ждёт
# `zip_release` из `hacs.json`. Архив кладётся питоном, который скрипту нужен и без
# него, - лишней зависимости от `zip` тут не заводится.
build_hass_zip() {  # $1 - рабочий каталог (внутри - src/ клон)
    work="$1" home="$1/src/custom_components/torrcast"
    need python3
    find "$home" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    ( cd "$home" && python3 -m zipfile -c "$work/torrcast-hass.zip" ./* )
}

# --- 4. тарбол белым списком + sha256 ----------------------------------------
# Едут: torrcast/, tgbot/, hass/ (их ставит hatchling, see pyproject packages), install.sh,
# install (bootstrap), pyproject.toml, все четыре README с гифкой из docs/, ченджлог
# (docs/changelog: его читает последний экран обновления), LICENSE и пять
# файлов из scripts/,
# которых install.sh реально зовёт по REPO_DIR (sni-shim.py и определения индексеров).
# tests/, scripts/test-gate и прочая разработческая обвязка НЕ едут.
build_tarball() {  # $1 - рабочий каталог (внутри - src/ клон), $2 - версия без v
    work="$1" ver="$2" src="$1/src" pkg="$1/pkg"
    mkdir "$pkg" "$pkg/scripts" "$pkg/docs"
    cp -a "$src/torrcast" "$src/tgbot" "$src/hass" "$pkg/"
    cp "$src/install.sh" "$src/install" "$src/pyproject.toml" "$src/LICENSE" "$pkg/"
    cp "$src/README.md" "$pkg/"
    cp "$src/docs/README-jp.md" "$src/docs/README-es.md" "$src/docs/README-ru.md" \
       "$src/docs/demo.gif" "$src/docs/changelog" "$pkg/docs/"
    cp "$src/scripts/sni-shim.py" "$src/scripts/anilibria.yml" "$src/scripts/jacred.yml" \
       "$src/scripts/anilibria-indexer.py" "$src/scripts/jacred-indexer.py" "$pkg/scripts/"
    find "$pkg" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    find "$pkg" -name '*.pyc' -delete

    ( cd "$pkg" && tar -czf "$work/torrcast-$ver.tar.gz" -- * )
    ( cd "$work" && sha256sum "torrcast-$ver.tar.gz" > "torrcast-$ver.tar.gz.sha256" )
}

# --- 5. Release на теге -------------------------------------------------------
release_body() {  # $1 - тег; описание - из $notes
    need python3
    TC_TAG="$1" TC_NOTES="$notes" python3 -c '
import json
import os

body = {"tag_name": os.environ["TC_TAG"], "name": os.environ["TC_TAG"]}
notes = os.environ["TC_NOTES"]
if notes:
    with open(notes, encoding="utf-8") as fh:
        body["body"] = fh.read()
print(json.dumps(body, ensure_ascii=False))
'
}

# Печатает id созданного релиза. Разбор - питоном, а не sed: в ответе GitHub полей
# "id" много (автор, каждый ассет), и первое попавшееся - не то, что нужно.
create_release() {  # $1 - тег, $2 - заголовок токена
    need python3
    curl -fsSL -X POST -H "$2" -H 'Content-Type: application/json' \
        -H 'X-GitHub-Api-Version: 2022-11-28' \
        --data "$(release_body "$1")" \
        "$GITHUB_API/repos/$PROJECT_PATH/releases" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
}

# --- 6. ассеты релиза + сверка releases/latest снаружи ------------------------
# Ассет `install` кладётся под этим именем не для красоты: короткий адрес установщика
# редиректит на `releases/latest/download/install`, и имя там - часть адреса.
upload_asset() {  # $1 - id релиза, $2 - путь к файлу, $3 - имя ассета, $4 - заголовок токена
    curl -fsSL -X POST -H "$4" -H 'Content-Type: application/octet-stream' \
        -H 'X-GitHub-Api-Version: 2022-11-28' \
        --data-binary "@$2" \
        "$GITHUB_UPLOADS/repos/$PROJECT_PATH/releases/$1/assets?name=$3" >/dev/null \
        || die "не залился ассет $3"
}

# Сверка тем же способом, каким версию узнаёт бутстрап: `/releases/latest` обязан
# перенаправить на `/releases/tag/<тег>`. Спрашиваем БЕЗ токена - так же, как аноним.
#
# 🔴 С повторами, и это куплено потерей. Заведённый релиз виден в API сразу, а вот
# перенаправление `/releases/latest` отдаётся из кэша и догоняет за десятки секунд:
# 31-08-2026 первый же выпуск с этого скрипта упал ровно здесь, опубликовав при этом
# всё как надо. Без повторов сверка ловит не «релиз не тот», а «спросили слишком рано»,
# и красит красным исправный выпуск. Потолок ожидания есть: молчание кэша дольше него -
# уже не задержка, а расхождение, и о нём надо знать.
check_latest_points_at() {  # $1 - тег
    pause="${TORRCAST_LATEST_RETRY_PAUSE:-5}"
    tries="${TORRCAST_LATEST_RETRY_TRIES:-24}"
    n=1
    while : ; do
        loc="$(curl -fsS -o /dev/null -w '%{redirect_url}' \
                    "$GITHUB_WEB/$PROJECT_PATH/releases/latest")" \
            || die "releases/latest не отвечает"
        case "$loc" in
            */releases/tag/"$1") return 0 ;;
        esac
        [ "$n" -lt "$tries" ] \
            || die "releases/latest и через $((tries * pause)) с ведёт на «$loc», а не на тег $1"
        info "    releases/latest ещё ведёт на «$loc», жду $pause с ($n из $tries)"
        n=$((n + 1))
        sleep "$pause"
    done
}

main() {
    need git
    need curl
    need tar
    need sha256sum
    need python3

    check_tag_format "$tag"
    info "[1] тег $tag - semver, проверяю предка на master"

    work="$(mktemp -d)"
    cleanup() { [ "$dry_run" -eq 1 ] || rm -rf "$work"; }
    trap cleanup EXIT

    info "[2] клонирую $GITHUB_REPO по тегу $tag"
    clone_at_tag "$work/src" "$tag"

    ver="${tag#v}"
    info "[3] подставляю версию $ver в дерево"
    substitute_version "$work/src" "$ver"

    info "[4] собираю tarball + sha256 + zip интеграции"
    build_tarball "$work" "$ver"
    build_hass_zip "$work"

    if [ "$dry_run" -eq 1 ]; then
        info "--dry-run: шаги 5-6 не выполняю, только печатаю намерение"
        info "  [5] завёл бы Release на $tag в $GITHUB_API/repos/$PROJECT_PATH/releases"
        info "  [6] залил бы ассеты torrcast-$ver.tar.gz, torrcast-$ver.tar.gz.sha256, install и torrcast-hass.zip, сверил бы releases/latest = $tag"
        info "тарбол, sha256 и zip оставлены на диске: $work - прибери сам после проверки"
        return 0
    fi

    [ -n "${GITHUB_TOKEN:-}" ] || die "нужен токен: переменная GITHUB_TOKEN"
    auth="Authorization: Bearer $GITHUB_TOKEN"

    info "[5] завожу Release на $tag"
    id="$(create_release "$tag" "$auth")" || die "релиз не завёлся"
    [ -n "$id" ] || die "GitHub не назвал id созданного релиза"

    info "[6] заливаю ассеты и сверяю releases/latest"
    upload_asset "$id" "$work/torrcast-$ver.tar.gz" "torrcast-$ver.tar.gz" "$auth"
    upload_asset "$id" "$work/torrcast-$ver.tar.gz.sha256" "torrcast-$ver.tar.gz.sha256" "$auth"
    upload_asset "$id" "$work/src/install" "install" "$auth"
    upload_asset "$id" "$work/torrcast-hass.zip" "torrcast-hass.zip" "$auth"
    check_latest_points_at "$tag"

    info "готово: $tag опубликован"
}

main "$@"
