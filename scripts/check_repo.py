#!/usr/bin/env python3
"""Проверка набора перед публикацией: формат скиллов, длинные тире, личные данные.

Запуск: python3 scripts/check_repo.py  (из корня репозитория). Код 1 при нарушениях.
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DASHES = (chr(0x2014), chr(0x2013))  # длинное и среднее тире, заданы кодом
# Признаки личных данных и секретов. Список намеренно шире, чем нужно:
# лучше лишний раз посмотреть глазами, чем выложить ключ.
PRIVATE = [
    (r'aff_\d{4,}', 'партнёрский ID'),
    (r'\+7[\s(]*\d{3}', 'телефон'),
    (r'(?<![\w.+-])(?!connect@shootkin\.com)[\w.+-]+@(?!example\.)[\w-]+\.[a-z]{2,}', 'почта'),  # деловая почта автора разрешена
    (r'\b(?:\d{1,3}\.){3}\d{1,3}\b', 'IP-адрес'),
    (r'\b[0-9a-f]{32}\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', 'ID (Notion/база)'),
    (r'(?i)\b(sk-[a-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|xox[bp]-)', 'ключ API'),
    (r'(?i)collection://|notion\.so/', 'ссылка на Notion'),
    (r'(?i)/Users/|/private/tmp/', 'локальный путь'),
]
# Свои стоп-слова (названия других проектов, служебные адреса) держи в
# локальном файле scripts/private-patterns.txt: одна регулярка на строку.
# Файл в .gitignore и в репозиторий не попадает.
_local = ROOT / 'scripts' / 'private-patterns.txt'
if _local.exists():
    for _rx in _local.read_text(encoding='utf-8').splitlines():
        if _rx.strip() and not _rx.startswith('#'):
            PRIVATE.append((_rx.strip(), 'своё стоп-слово'))
SKIP_DIRS = {'.git', '__pycache__'}
errors = []

for p in sorted(ROOT.rglob('*')):
    if not p.is_file() or set(p.relative_to(ROOT).parts) & SKIP_DIRS:
        continue
    rel = p.relative_to(ROOT)
    try:
        text = p.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        continue
    for n, line in enumerate(text.splitlines(), 1):
        if any(d in line for d in DASHES):
            errors.append(f'{rel}:{n}: длинное тире')
        if rel in (pathlib.Path('scripts/check_repo.py'), pathlib.Path('scripts/private-patterns.txt')):
            continue
        for rx, what in PRIVATE:
            m = re.search(rx, line)
            if m:
                errors.append(f'{rel}:{n}: {what}: {m.group(0)[:40]}')

for d in sorted((ROOT / 'skills').iterdir()) if (ROOT / 'skills').exists() else []:
    if not d.is_dir():
        continue
    sk = d / 'SKILL.md'
    if not sk.exists():
        errors.append(f'skills/{d.name}: нет SKILL.md'); continue
    head = sk.read_text(encoding='utf-8').split('---')
    if len(head) < 3 or f'name: {d.name}' not in head[1] or 'description:' not in head[1]:
        errors.append(f'skills/{d.name}/SKILL.md: фронтматтер без name: {d.name} или description')

if errors:
    print('Найдено:', len(errors)); print('\n'.join(errors)); sys.exit(1)
print('Чисто: формат скиллов, тире и личные данные в порядке.')
