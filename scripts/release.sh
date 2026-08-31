#!/bin/sh
# scripts/release.sh [--dry-run] <tag>   - публикация релиза torrcast, шесть шагов
# из TC-886. Тело одно: позже .gitlab-ci.yml (TC-892) зовёт его так же по тегу,
# только токен приедет как CI_JOB_TOKEN вместо GITLAB_TOKEN.
#
# 1. тег - semver (vX.Y.Z), и его коммит лежит на master
# 2. клон репы ПО ТЕГУ в mktemp -d (не рабочее дерево)
# 3. версия из тега - в три места: version.py, pyproject.toml, install.sh
# 4. тарбол + sha256
# 5. заливка тарбола и sha256 в generic-реестр
# 6. Release на теге (asset install + asset tarball), сверка permalink/latest снаружи
#
# --dry-run: 1-4 по-настоящему, 5-6 только печатает - так скрипт проверяем без
# токена и без права писать в GitLab.
set -eu

GITLAB_API="${TORRCAST_GITLAB_API:-https://gitlab.anysda.space/api/v4}"
GITLAB_WEB="${TORRCAST_GITLAB_WEB:-https://gitlab.anysda.space}"
GITLAB_REPO="${TORRCAST_GITLAB_REPO:-$GITLAB_WEB/anysda/torrcast.git}"
PROJECT_ID="${TORRCAST_PROJECT_ID:-10}"
PROJECT_PATH="${TORRCAST_PROJECT_PATH:-anysda/torrcast}"

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
    git clone --quiet "$GITLAB_REPO" "$dst" || die "не клонируется $GITLAB_REPO"
    (
        cd "$dst"
        git rev-parse -q --verify "refs/tags/$t" >/dev/null 2>&1 \
            || die "тега $t нет в $GITLAB_REPO"
        git merge-base --is-ancestor "refs/tags/$t" origin/master \
            || die "тег $t не лежит на master"
        git checkout --quiet "$t"
    )
}

# --- 3. версия из тега в три места -------------------------------------------
substitute_version() {  # $1 - каталог клона, $2 - версия без v
    src="$1" ver="$2"
    # Версия в дереве - любая: она уже менялась и будет меняться. Литерал прежней
    # версии здесь означал бы, что первый же выпуск делает скрипт неработающим молча.
    any_ver='[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*'
    sed -i "s/^__version__ = \"$any_ver\"\$/__version__ = \"$ver\"/" \
        "$src/torrcast/domain/version.py"
    sed -i "s/^version = \"$any_ver\"\$/version = \"$ver\"/" "$src/pyproject.toml"
    sed -i "s/^VERSION='$any_ver'\$/VERSION='$ver'/" "$src/install.sh"

    grep -q "^__version__ = \"$ver\"\$" "$src/torrcast/domain/version.py" \
        || die "версия не встала в torrcast/domain/version.py"
    grep -q "^version = \"$ver\"\$" "$src/pyproject.toml" \
        || die "версия не встала в pyproject.toml"
    grep -q "^VERSION='$ver'\$" "$src/install.sh" \
        || die "версия не встала в install.sh"
}

# --- 4. тарбол белым списком + sha256 ----------------------------------------
# Едут: torrcast/, tgbot/ (их ставит hatchling, see pyproject packages), install.sh,
# install (bootstrap), pyproject.toml, все четыре README, LICENSE и пять файлов из scripts/,
# которых install.sh реально зовёт по REPO_DIR (sni-shim.py и определения индексеров).
# tests/, scripts/test-gate и прочая разработческая обвязка НЕ едут.
build_tarball() {  # $1 - рабочий каталог (внутри - src/ клон), $2 - версия без v
    work="$1" ver="$2" src="$1/src" pkg="$1/pkg"
    mkdir "$pkg" "$pkg/scripts"
    cp -a "$src/torrcast" "$src/tgbot" "$pkg/"
    cp "$src/install.sh" "$src/install" "$src/pyproject.toml" "$src/LICENSE" "$pkg/"
    cp "$src/README.md" "$src/README-jp.md" "$src/README-es.md" "$src/README-ru.md" "$pkg/"
    cp "$src/scripts/sni-shim.py" "$src/scripts/anilibria.yml" "$src/scripts/jacred.yml" \
       "$src/scripts/anilibria-indexer.py" "$src/scripts/jacred-indexer.py" "$pkg/scripts/"
    find "$pkg" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    find "$pkg" -name '*.pyc' -delete

    ( cd "$pkg" && tar -czf "$work/torrcast-$ver.tar.gz" -- * )
    ( cd "$work" && sha256sum "torrcast-$ver.tar.gz" > "torrcast-$ver.tar.gz.sha256" )
}

# --- 5. заливка в generic-реестр ---------------------------------------------
upload_package() {  # $1 - рабочий каталог, $2 - версия без v, $3 - заголовок токена
    work="$1" ver="$2" auth="$3"
    base="$GITLAB_API/projects/$PROJECT_ID/packages/generic/torrcast/$ver"
    curl -fsSL -H "$auth" --upload-file "$work/torrcast-$ver.tar.gz" \
         "$base/torrcast-$ver.tar.gz" || die "не залился тарбол"
    curl -fsSL -H "$auth" --upload-file "$work/torrcast-$ver.tar.gz.sha256" \
         "$base/torrcast-$ver.tar.gz.sha256" || die "не залился sha256"
}

# --- 6. Release на теге + сверка permalink/latest снаружи --------------------
release_body() {  # $1 - тег, $2 - url install, $3 - url тарбола; описание - из $notes
    need python3
    TC_TAG="$1" TC_INSTALL="$2" TC_TARBALL="$3" TC_NOTES="$notes" python3 -c '
import json
import os

body = {
    "tag_name": os.environ["TC_TAG"],
    "assets": {
        "links": [
            {"name": "install", "url": os.environ["TC_INSTALL"], "filepath": "/install"},
            {"name": "tarball", "url": os.environ["TC_TARBALL"]},
        ]
    },
}
notes = os.environ["TC_NOTES"]
if notes:
    with open(notes, encoding="utf-8") as fh:
        body["description"] = fh.read()
print(json.dumps(body, ensure_ascii=False))
'
}

publish_release() {  # $1 - тег, $2 - версия без v, $3 - заголовок токена
    t="$1" ver="$2" auth="$3"
    tarball_url="$GITLAB_API/projects/$PROJECT_ID/packages/generic/torrcast/$ver/torrcast-$ver.tar.gz"
    install_url="$GITLAB_WEB/$PROJECT_PATH/-/raw/$t/install"
    curl -fsSL -X POST -H "$auth" -H 'Content-Type: application/json' \
        --data "$(release_body "$t" "$install_url" "$tarball_url")" \
        "$GITLAB_API/projects/$PROJECT_ID/releases" >/dev/null || die "релиз не завёлся"

    got="$(curl -fsSL "$GITLAB_API/projects/$PROJECT_ID/releases/permalink/latest" \
           | sed -n 's/.*"tag_name" *: *"\([^"]*\)".*/\1/p')"
    [ "$got" = "$t" ] || die "после публикации permalink/latest отдал «$got», а не «$t»"
}

main() {
    need git
    need curl
    need tar
    need sha256sum

    check_tag_format "$tag"
    info "[1] тег $tag - semver, проверяю предка на master"

    work="$(mktemp -d)"
    cleanup() { [ "$dry_run" -eq 1 ] || rm -rf "$work"; }
    trap cleanup EXIT

    info "[2] клонирую $GITLAB_REPO по тегу $tag"
    clone_at_tag "$work/src" "$tag"

    ver="${tag#v}"
    info "[3] подставляю версию $ver в три места"
    substitute_version "$work/src" "$ver"

    info "[4] собираю tarball + sha256"
    build_tarball "$work" "$ver"

    if [ "$dry_run" -eq 1 ]; then
        info "--dry-run: шаги 5-6 не выполняю, только печатаю намерение"
        info "  [5] залил бы torrcast-$ver.tar.gz(.sha256) в $GITLAB_API/projects/$PROJECT_ID/packages/generic/torrcast/$ver/"
        info "  [6] завёл бы Release на $tag (asset install -> /install, asset tarball), сверил бы permalink/latest = $ver"
        info "тарбол и sha256 оставлены на диске: $work - прибери сам после проверки"
        return 0
    fi

    auth=""
    [ -n "${CI_JOB_TOKEN:-}" ] && auth="JOB-TOKEN: $CI_JOB_TOKEN"
    [ -z "$auth" ] && [ -n "${GITLAB_TOKEN:-}" ] && auth="PRIVATE-TOKEN: $GITLAB_TOKEN"
    [ -n "$auth" ] || die "нужен токен: переменная GITLAB_TOKEN (в пайплайне - CI_JOB_TOKEN)"

    info "[5] заливаю тарбол и sha256 в generic-реестр"
    upload_package "$work" "$ver" "$auth"

    info "[6] завожу Release на $tag и сверяю permalink/latest"
    publish_release "$tag" "$ver" "$auth"

    info "готово: $tag опубликован"
}

main "$@"
