#!/usr/bin/env python3
"""Поиск протухших фактов в текстах: старые версии сервисов, сроки акций,
прошлые годы в заголовках.

Запуск: python3 check_freshness.py <папка> <versions.json> [--today 2026-10-07]

Скрипт НЕ знает, что вышло нового: он знает только versions.json. Поэтому
сначала сверь таблицу по официальным страницам и поставь новую дату в
checked_at, потом запускай. Код выхода 1, если есть хоть одна ОШИБКА.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

TEXT_EXT = {'.md', '.markdown', '.mdx', '.txt', '.js', '.jsx', '.ts', '.tsx', '.json', '.html', '.htm'}
SKIP_DIRS = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', '.next', '__pycache__'}

# Слова, с которыми старая версия упомянута как история, а не как актуальная.
HISTORY = re.compile(r'(раньше|ранее|прежн|предыдущ|устаревш|стар(ая|ой|ую|ые)\s+верси|'
                     r'на смену|сменил|заменил|вместо|до выхода|когда-то|была|был\s|'
                     r'previous|formerly|replaced|used to|old version)', re.I)

MONTHS = (r'(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря|'
          r'january|february|march|april|may|june|july|august|september|october|november|december)')
DEADLINES = [
    re.compile(r'\b(до|по|until|till|through)\s+\d{1,2}(-?го)?\s+' + MONTHS, re.I),
    re.compile(r'\b(до|по|until)\s+\d{1,2}\.\d{1,2}(\.\d{2,4})?\b', re.I),
    re.compile(r'\bдо\s+конца\s+(месяца|недели|года|акции|лета|осени|зимы|весны|сезона|дня)\b', re.I),
    re.compile(r'\b(только|лишь)\s+(сегодня|до|в\s+этом\s+месяце|на\s+этой\s+неделе)\b', re.I),
    re.compile(r'\b(успей(те)?|осталось\s+\d+\s+(дн|час)\w*|последний\s+день\s+акци\w*)', re.I),
    re.compile(r'\b(only today|limited time|ends (on|in) \w+|while it lasts|last chance)\b', re.I),
]

YEAR = re.compile(r'(?<!\d)(20\d\d)(?!\d)')
MD_HEAD = re.compile(r'^\s{0,3}#{1,6}\s+(.+)$')
HTML_HEAD = re.compile(r'<(h[1-6]|title)\b[^>]*>(.*?)</\1>', re.I | re.S)
KEY_HEAD = re.compile(r'["\']?(title|seoTitle|metaTitle|heading|h1|h2|h3)["\']?\s*:\s*(["\'`])(.*?)\2')


def ver_tuple(v):
    # «6», «6.0» и «6.0.0» одна и та же версия: дополняем до трёх чисел.
    nums = [int(x) for x in re.findall(r'\d+', str(v))][:3]
    return tuple(nums + [0] * (3 - len(nums)))


def load_table(path, today):
    """Читает versions.json и проверяет, что таблицу сверяли недавно."""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    errors, services = [], []
    checked = data.get('checked_at')
    ttl = int(data.get('ttl_days', 45))
    if not checked:
        errors.append('в versions.json нет checked_at: непонятно, когда таблицу сверяли')
    else:
        age = (today - dt.date.fromisoformat(checked)).days
        if age > ttl:
            errors.append(f'таблицу версий сверяли {age} дней назад ({checked}), дольше {ttl} ей верить нельзя.\n'
                          '      Сверь версии по официальным страницам и поставь новую дату в checked_at.')
    for s in data.get('services', []):
        flags = 0 if s.get('case_sensitive') else re.I
        services.append({
            'name': s['name'],
            'current': str(s['current']),
            'version_rx': re.compile(s['version_regex'], flags),
            'context_rx': re.compile(s.get('context_regex') or re.escape(s['name']), re.I),
            'window': int(s.get('context_window', 200)),
        })
    return services, errors


def iter_files(root, skip):
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for name in sorted(files):
            p = os.path.join(d, name)
            if os.path.splitext(name)[1].lower() in TEXT_EXT and os.path.abspath(p) not in skip:
                yield p


def nearest(positions, at):
    return min((abs(p - at) for p in positions), default=None)


def line_info(text, pos):
    start = text.rfind('\n', 0, pos) + 1
    end = text.find('\n', pos)
    end = len(text) if end == -1 else end
    return text.count('\n', 0, pos) + 1, text[start:end]


def frag(line, pad=160):
    line = re.sub(r'\s+', ' ', line).strip()
    return line if len(line) <= pad else line[:pad] + '...'


def check_versions(text, services, out, seen):
    """Версия считается версией сервиса, только если рядом стоит имя сервиса
    и никакое другое имя сервиса не стоит ближе. Так «V8» одного сервиса не
    путается с «v8» другого."""
    ctx = {s['name']: [m.start() for m in s['context_rx'].finditer(text)] for s in services}
    for s in services:
        own = ctx[s['name']]
        if not own:
            continue
        for m in s['version_rx'].finditer(text):
            d_own = nearest(own, m.start())
            if d_own is None or d_own > s['window']:
                continue
            if any(nearest(ctx[o['name']], m.start()) is not None
                   and nearest(ctx[o['name']], m.start()) < d_own
                   for o in services if o['name'] != s['name']):
                continue
            v = m.group(1)
            n, line = line_info(text, m.start())
            seen.setdefault(s['name'], {}).setdefault(v, set()).add(out['file'])
            if ver_tuple(v) < ver_tuple(s['current']):
                kind = 'warns' if HISTORY.search(line) else 'errors'
                note = ' (похоже на историю, проверь)' if kind == 'warns' else ''
                out[kind].append(f'строка {n}: {s["name"]} {v}, актуальная {s["current"]}{note}\n'
                                 f'      «{frag(line)}»')
            elif ver_tuple(v) > ver_tuple(s['current']):
                out['warns'].append(f'строка {n}: {s["name"]} {v} новее таблицы ({s["current"]}): '
                                    'похоже, таблицу пора обновить')


def check_deadlines(text, out):
    for rx in DEADLINES:
        for m in rx.finditer(text):
            n, line = line_info(text, m.start())
            out['errors'].append(f'строка {n}: срок в тексте «{m.group(0)}» протухнет. '
                                 f'Пиши без даты окончания и сверяй перед выкатом\n      «{frag(line)}»')


def check_head_years(text, year, out):
    heads = []
    for i, line in enumerate(text.split('\n'), start=1):
        m = MD_HEAD.match(line)
        if m:
            heads.append((i, m.group(1)))
    for rx, g in ((HTML_HEAD, 2), (KEY_HEAD, 3)):
        for m in rx.finditer(text):
            heads.append((text.count('\n', 0, m.start()) + 1, m.group(g)))
    for n, h in heads:
        old = [y for y in YEAR.findall(h) if int(y) < year]
        if old and str(year) not in h:
            out['errors'].append(f'строка {n}: в заголовке год {", ".join(old)}, сейчас {year}\n'
                                 f'      «{frag(h)}»')


def main():
    p = argparse.ArgumentParser(description='Поиск протухших фактов')
    p.add_argument('folder')
    p.add_argument('versions')
    p.add_argument('--today', help='дата проверки ГГГГ-ММ-ДД, по умолчанию сегодня')
    a = p.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()

    try:
        services, table_errors = load_table(a.versions, today)
    except (OSError, ValueError, KeyError, re.error) as e:
        print(f'ПРОВАЛ: не смог прочитать {a.versions} - {e}')
        sys.exit(2)
    if not os.path.isdir(a.folder):
        print(f'ПРОВАЛ: папки нет - {a.folder}')
        sys.exit(2)

    reports, seen, files = [], {}, 0
    for path in iter_files(a.folder, {os.path.abspath(a.versions)}):
        files += 1
        try:
            with open(path, encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError:
            reports.append({'file': path, 'errors': [], 'warns': ['не UTF-8, пропущен']})
            continue
        out = {'file': path, 'errors': [], 'warns': []}
        check_versions(text, services, out, seen)
        check_deadlines(text, out)
        check_head_years(text, today.year, out)
        if out['errors'] or out['warns']:
            reports.append(out)

    print(f'\nФайлов: {files}, сервисов в таблице: {len(services)}, дата проверки: {today}.')
    for e in table_errors:
        print('ОШИБКА ТАБЛИЦЫ: ' + e)
    total = len(table_errors)
    for r in reports:
        print(f'\n{r["file"]}')
        for e in r['errors']:
            print('  ОШИБКА: ' + e)
        for w in r['warns']:
            print('  ЗАМЕЧАНИЕ: ' + w)
        total += len(r['errors'])

    # Одна модель под разными версиями в разных текстах: противоречие.
    mixed = {k: v for k, v in seen.items() if len(v) > 1}
    if mixed:
        print('\nРАЗНЫЕ ВЕРСИИ ОДНОГО СЕРВИСА В ТЕКСТАХ:')
        for name, vers in sorted(mixed.items()):
            parts = [f'{v} ({len(fs)} файл.)' for v, fs in sorted(vers.items(), key=lambda x: ver_tuple(x[0]))]
            print(f'  {name}: ' + ', '.join(parts))

    print('\nИТОГ: ' + (f'ошибок {total}' if total else 'протухшего не нашёл') + '\n')
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
