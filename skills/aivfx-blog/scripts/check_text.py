#!/usr/bin/env python3
"""Поиск примет нейросети в русском тексте.

Запуск: python3 check_text.py <файл или папка> [ещё пути...]
                              [--stoplist путь/к/stoplist.txt]

Ищет длинные тире и формулировки из стоп-листа (по умолчанию
stoplist.txt рядом со скриптом). Печатает файл, строку, раздел,
фрагмент и совет. Код выхода 1, если есть хоть одна находка.
Скрипт находит, решает человек: не правь вслепую по выводу.
"""
import argparse
import os
import re
import sys

# Тире задаём кодами: чистка тире по репозиторию не должна сломать проверку.
DASHES = {'\u2014': 'длинное тире', '\u2013': 'среднее тире'}
DASH_RX = re.compile('[' + ''.join(DASHES) + ']')

TEXT_EXT = {'.md', '.markdown', '.txt', '.html', '.htm', '.json', '.js', '.jsx',
            '.ts', '.tsx', '.mdx', '.yml', '.yaml', '.csv', '.xml'}
SKIP_DIRS = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', '.next', '__pycache__'}
DEFAULT_STOPLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stoplist.txt')


def load_stoplist(path):
    """Читает стоп-лист: список (раздел, регулярка, исходная строка, совет)."""
    rules, section = [], 'стоп-лист'
    with open(path, encoding='utf-8') as f:
        for n, raw in enumerate(f, start=1):
            line = raw.rstrip('\n').strip()
            if not line:
                continue
            if line.startswith('##'):
                section = line.lstrip('#').strip() or section
                continue
            if line.startswith('#'):
                continue
            pattern, _, advice = line.partition(' => ')
            pattern, advice = pattern.strip(), advice.strip()
            try:
                if pattern.startswith('re:'):
                    rx = re.compile(pattern[3:], re.I)
                else:
                    rx = re.compile(r'(?<!\w)' + re.escape(pattern) + r'(?!\w)', re.I)
            except re.error as e:
                print(f'ОШИБКА В СТОП-ЛИСТЕ: {path}, строка {n}: {e}')
                sys.exit(2)
            rules.append((section, rx, pattern, advice))
    return rules


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for name in sorted(files):
                    if os.path.splitext(name)[1].lower() in TEXT_EXT:
                        yield os.path.join(root, name)
        else:
            print(f'ЗАМЕЧАНИЕ: путь не найден - {p}')


def fragment(line, start, end, pad=35):
    left = max(0, start - pad)
    right = min(len(line), end + pad)
    return ('...' if left else '') + line[left:right].strip() + ('...' if right < len(line) else '')


def check_file(path, rules):
    try:
        with open(path, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except UnicodeDecodeError:
        return [(0, 'файл', 'не UTF-8, пропущен (проверь, не битая ли кодировка)', '')]
    except OSError as e:
        return [(0, 'файл', f'не читается: {e}', '')]
    found = []
    for n, line in enumerate(lines, start=1):
        for m in DASH_RX.finditer(line):
            found.append((n, 'Тире', fragment(line, m.start(), m.end()),
                          DASHES[m.group(0)] + ': дефис, точка, двоеточие или запятая'))
        for section, rx, _, advice in rules:
            for m in rx.finditer(line):
                found.append((n, section, fragment(line, m.start(), m.end()), advice))
    return found


def main():
    p = argparse.ArgumentParser(description='Поиск примет нейросети в русском тексте')
    p.add_argument('paths', nargs='+')
    p.add_argument('--stoplist', default=DEFAULT_STOPLIST)
    a = p.parse_args()

    try:
        rules = load_stoplist(a.stoplist)
    except OSError as e:
        print(f'ПРОВАЛ: не смог открыть стоп-лист - {e}')
        sys.exit(2)

    total, files_seen, by_section = 0, 0, {}
    for path in iter_files(a.paths):
        files_seen += 1
        found = check_file(path, rules)
        if not found:
            continue
        print(f'\n{path}')
        for n, section, frag, advice in found:
            where = f'строка {n}' if n else 'файл'
            tail = f'\n      совет: {advice}' if advice else ''
            print(f'  {where} [{section}] «{frag}»{tail}')
            by_section[section] = by_section.get(section, 0) + 1
        total += len(found)

    print(f'\nФайлов проверено: {files_seen}, правил в стоп-листе: {len(rules)}.')
    if total:
        summary = ', '.join(f'{k}: {v}' for k, v in sorted(by_section.items(), key=lambda x: -x[1]))
        print(f'Находок: {total} ({summary}).')
        print('ИТОГ: есть что править\n')
        sys.exit(1)
    print('ИТОГ: по стоп-листу чисто. Это не значит, что текст живой: перечитай вслух.\n')


if __name__ == '__main__':
    main()
