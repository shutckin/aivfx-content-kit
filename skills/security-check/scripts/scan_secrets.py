#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Поиск строк, похожих на ключи и секреты, в папке своего проекта.

Что ищет:
  - ключи по известным шаблонам: sk-, ghp_ и другие токены GitHub, AKIA (AWS),
    AIza (Google), xox (Slack), токен Telegram-бота, живые ключи Stripe,
    приватные ключи в формате PEM, JWT (так выглядит, например, служебный
    ключ базы, который нельзя отдавать в браузер);
  - в файлах .env: длинные значения у переменных с именами вроде
    SECRET, TOKEN, KEY, PASSWORD;
  - в git (если папка это репозиторий): файлы .env под контролем версий и
    ключи в добавленных строках всей истории коммитов, даже удалённые потом.

Значение никогда не печатается целиком: только первые символы и длина.

Запуск:
    python3 scripts/scan_secrets.py .
    python3 scripts/scan_secrets.py путь/к/проекту --no-git

Строку, где ключ заведомо фальшивый (пример в документации), можно пометить
комментарием "scan-secrets: ignore", и скрипт её пропустит.

Код выхода: 0 - чисто, 1 - есть находки, 2 - папка не найдена или ошибка.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

# Шаблоны ключей. Имя шаблона видит человек в отчёте, поэтому по-русски.
PATTERNS = [
    ("приватный ключ PEM", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("ключ Anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("ключ вида sk- (OpenAI и похожие)", re.compile(r"\bsk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("живой ключ Stripe", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}")),
    ("токен GitHub", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("ключ доступа AWS", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("ключ Google API", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("токен Slack", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}")),
    ("токен Telegram-бота", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("JWT (проверь, не служебный ли это ключ)", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]

# Переменные в .env, где длинное значение почти наверняка секрет.
ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*['\"]?([^'\"\s#]+)")
ENV_SECRET_NAME = re.compile(r"SECRET|TOKEN|KEY|PASSWORD|PASSWD|PRIVATE|CREDENTIAL", re.I)
PLACEHOLDER = re.compile(r"^(?:x+|\*+|<.*>|your[_-].*|changeme|example.*|placeholder.*|\.\.\.)$", re.I)
ENV_MIN_LEN = 16

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
             ".next", ".nuxt", ".vercel", ".turbo", "coverage", ".cache"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".ico", ".pdf",
                 ".mp4", ".mov", ".webm", ".mp3", ".wav", ".zip", ".gz", ".woff",
                 ".woff2", ".ttf", ".otf", ".lock"}
MAX_FILE_BYTES = 2_000_000
IGNORE_MARK = "scan-secrets: ignore"


def mask(value):
    """Показывает первые 4 символа и длину, остальное прячет."""
    head = value[:4]
    return f"{head}{'*' * 8} (длина {len(value)})"


def is_env_file(path):
    name = path.name.lower()
    if name.endswith((".example", ".sample", ".template")):
        return False
    return name == ".env" or name.startswith(".env.") or name.endswith(".env")


def scan_line(line, env_mode):
    """Возвращает список (что нашли, маска) для одной строки."""
    if IGNORE_MARK in line:
        return []
    hits = []
    for title, rx in PATTERNS:
        for m in rx.finditer(line):
            hits.append((title, mask(m.group(0))))
    if env_mode and not hits:
        m = ENV_LINE.match(line)
        if m and ENV_SECRET_NAME.search(m.group(1)):
            value = m.group(2)
            if len(value) >= ENV_MIN_LEN and not PLACEHOLDER.match(value):
                hits.append((f"длинное значение в .env ({m.group(1)})", mask(value)))
    return hits


def iter_files(root):
    for path in sorted(root.rglob("*")):
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        if not path.is_file() or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def scan_folder(root):
    findings = []
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        env_mode = is_env_file(path)
        rel = path.relative_to(root)
        for n, line in enumerate(text.splitlines(), 1):
            for title, masked in scan_line(line, env_mode):
                findings.append(f"{rel}:{n}: {title}: {masked}")
    return findings


def run_git(root, args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git вернул ошибку")
    return result.stdout


def is_git_repo(root):
    try:
        return run_git(root, ["rev-parse", "--is-inside-work-tree"]).strip() == "true"
    except (RuntimeError, FileNotFoundError):
        return False


def scan_git(root):
    findings = []
    for name in run_git(root, ["ls-files"]).splitlines():
        if is_env_file(Path(name)):
            findings.append(f"git: файл {name} под контролем версий (его видно всем, у кого есть репозиторий)")
    # Добавленные строки всей истории: ключ, удалённый позже, всё равно лежит в коммите.
    log = run_git(root, ["log", "--all", "-p", "--no-color", "--format=commit %h"])
    commit, current_file, seen = "?", "?", set()
    for line in log.splitlines():
        if line.startswith("commit "):
            commit = line.split(" ", 1)[1]
        elif line.startswith("+++ "):
            current_file = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and not line.startswith("+++"):
            env_mode = is_env_file(Path(current_file))
            for title, masked in scan_line(line[1:], env_mode):
                key = (current_file, title, masked)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(f"git история, коммит {commit}, {current_file}: {title}: {masked}")
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Поиск похожих на ключи строк в своём проекте.")
    parser.add_argument("folder", help="папка проекта")
    parser.add_argument("--no-git", action="store_true", help="не смотреть историю git")
    args = parser.parse_args(argv)

    root = Path(args.folder).expanduser().resolve()
    if not root.is_dir():
        print(f"Ошибка: папка не найдена: {args.folder}")
        return 2

    findings = scan_folder(root)
    if not args.no_git:
        if is_git_repo(root):
            try:
                findings += scan_git(root)
            except (RuntimeError, FileNotFoundError) as err:
                print(f"Ошибка при чтении истории git: {err}")
                return 2
        else:
            print("Заметка: папка не репозиторий git, историю коммитов не проверял.")

    if findings:
        print(f"Найдено похожих на ключи строк: {len(findings)}")
        print("\n".join(findings))
        print("\nЧто дальше: каждый настоящий ключ из списка считать утёкшим, если он попал")
        print("в git или в код страницы. Порядок действий в SKILL.md, раздел «Если ключ утёк».")
        return 1
    print("Чисто: похожих на ключи строк не найдено.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
