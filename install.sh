#!/usr/bin/env bash
# Установка скиллов AIVFX Content Kit в Claude Code и Codex.
#
# Запуск из корня репозитория:
#   bash install.sh            # в обе среды: ~/.claude/skills и ~/.codex/skills
#   bash install.sh --claude   # только Claude Code
#   bash install.sh --codex    # только Codex
#
# Что делает: копирует каждую папку skills/<имя> в папку скиллов среды.
# Если там уже есть папка с тем же именем, сначала переносит её в
# резервную копию <среда>/skills-backups/<дата-время>/<имя>, потом кладёт
# новую. Чужие скиллы с другими именами не трогает.

set -eu

usage() {
    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
}

want_claude=0
want_codex=0
for arg in "$@"; do
    case "$arg" in
        --claude) want_claude=1 ;;
        --codex) want_codex=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Неизвестный флаг: $arg" >&2; usage >&2; exit 2 ;;
    esac
done
# Без флагов ставим в обе среды.
if [ "$want_claude" -eq 0 ] && [ "$want_codex" -eq 0 ]; then
    want_claude=1
    want_codex=1
fi

if [ -z "${HOME:-}" ]; then
    echo "Переменная HOME пустая, не знаю, куда ставить." >&2
    exit 1
fi

# Папка skills рядом с этим скриптом, откуда бы его ни запустили.
repo_dir=$(cd "$(dirname "$0")" && pwd)
src_dir="$repo_dir/skills"
if [ ! -d "$src_dir" ]; then
    echo "Не нашёл папку со скиллами: $src_dir" >&2
    exit 1
fi

stamp=$(date +%Y%m%d-%H%M%S)

# install_to <название среды> <корень среды, например ~/.claude>
install_to() {
    env_name=$1
    env_root=$2
    dest="$env_root/skills"
    backup_root="$env_root/skills-backups/$stamp"
    installed=0
    backed_up=0

    mkdir -p "$dest"
    echo "$env_name: ставлю в $dest"

    for skill in "$src_dir"/*/; do
        [ -d "$skill" ] || continue
        skill=${skill%/}
        name=$(basename "$skill")
        if [ ! -f "$skill/SKILL.md" ]; then
            echo "  пропускаю $name: нет SKILL.md"
            continue
        fi
        target="$dest/$name"
        # Есть старая папка или ссылка с тем же именем: в резервную копию.
        if [ -e "$target" ] || [ -L "$target" ]; then
            mkdir -p "$backup_root"
            mv "$target" "$backup_root/$name"
            echo "  $name: старая версия перенесена в $backup_root/$name"
            backed_up=$((backed_up + 1))
        fi
        cp -R "$skill" "$target"
        # Кэш Python не нужен в установленной копии.
        find "$target" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
        echo "  $name: установлен"
        installed=$((installed + 1))
    done

    echo "$env_name: установлено $installed, в резервную копию ушло $backed_up."
    echo
}

if [ "$want_claude" -eq 1 ]; then
    install_to "Claude Code" "$HOME/.claude"
fi
if [ "$want_codex" -eq 1 ]; then
    install_to "Codex" "$HOME/.codex"
fi

echo "Готово. Скиллы подхватятся в новой сессии агента."
echo "Проверка: напиши агенту «пришёл бриф на рекламный AI-ролик для кофейни» и посмотри, включился ли ai-video-concept."
