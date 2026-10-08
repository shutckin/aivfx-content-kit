#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка раскадровки в виде таблицы markdown.

Что проверяет:
  - сумму длительностей против целевого хронометража (--target, допуск --tolerance);
  - пустые ячейки (прочерк "-" считается заполненной: «закадра нет намеренно»);
  - кадры дольше порога (--max, по умолчанию 7 секунд);
  - источник из списка: съёмка, генерация, архив, сток, моушен, скриншот;
  - что таймкод каждого кадра совпадает с концом предыдущего.

Таблица ищется по заголовку: нужна колонка со словом «Длит». Остальные колонки
узнаются по словам «Тайм», «Тип», «Реплик» или «Закадр», «Визуал», «Источник».

Запуск:
    python3 scripts/check_shotlist.py shotlist.md
    python3 scripts/check_shotlist.py shotlist.md --target 30 --max 3
    python3 scripts/check_shotlist.py shotlist.md --target 90 --tolerance 3

Код выхода: 0 - чисто, 1 - есть нарушения, 2 - файл не читается или таблицы нет.
"""

import argparse
import re
import sys
from pathlib import Path

SOURCES = ('съёмка', 'съемка', 'генерация', 'архив', 'сток', 'моушен', 'скриншот')
COLUMNS = {
    'num': ('#', '№'),
    'timecode': ('тайм',),
    'type': ('тип',),
    'line': ('реплик', 'закадр'),
    'visual': ('визуал',),
    'duration': ('длит',),
    'source': ('источник',),
}
TIME_RX = re.compile(r'(\d{1,2}):(\d{2})(?:[.,](\d+))?')


def split_row(line):
    """Строка таблицы в список ячеек без крайних пустых."""
    cells = [c.strip() for c in line.strip().strip('|').split('|')]
    return cells


def is_separator(cells):
    return all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c) and any(cells)


def map_columns(header):
    """Номер колонки для каждого известного поля по словам в заголовке."""
    found = {}
    for idx, name in enumerate(header):
        low = name.lower()
        for key, words in COLUMNS.items():
            if key in found:
                continue
            if key == 'num':
                if low in words:
                    found[key] = idx
            elif any(w in low for w in words):
                found[key] = idx
    return found


def find_table(text):
    """Первая таблица с колонкой длительности: (колонки, строки с номерами)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.lstrip().startswith('|'):
            continue
        header = split_row(line)
        cols = map_columns(header)
        if 'duration' not in cols or i + 1 >= len(lines):
            continue
        if not is_separator(split_row(lines[i + 1])):
            continue
        rows = []
        for n in range(i + 2, len(lines)):
            if not lines[n].lstrip().startswith('|'):
                break
            rows.append((n + 1, split_row(lines[n])))
        return header, cols, rows
    return None


def parse_seconds(text):
    """'3', '2,5 с', '0:04' в секунды. None, если не число."""
    text = text.strip().lower()
    m = TIME_RX.search(text)
    if m:
        frac = float('0.' + m.group(3)) if m.group(3) else 0.0
        return int(m.group(1)) * 60 + int(m.group(2)) + frac
    m = re.search(r'\d+(?:[.,]\d+)?', text)
    if m:
        return float(m.group(0).replace(',', '.'))
    return None


def parse_start(text):
    """Начало кадра из таймкода '0:03-0:05' или '00:03'."""
    m = TIME_RX.search(text)
    if not m:
        return None
    frac = float('0.' + m.group(3)) if m.group(3) else 0.0
    return int(m.group(1)) * 60 + int(m.group(2)) + frac


def fmt(sec):
    return f'{sec:g} с'


def check_rows(header, cols, rows, args):
    problems = []
    total = 0.0
    for line_no, cells in rows:
        cells = cells + [''] * (len(header) - len(cells))
        label = cells[cols['num']] if 'num' in cols and cells[cols['num']] else f'строка {line_no}'
        where = f'кадр {label} (строка {line_no})'
        for idx, name in enumerate(header):
            if not cells[idx]:
                problems.append(f'{where}: пустая ячейка «{name}». Если пусто намеренно, поставь «-»')
        dur = parse_seconds(cells[cols['duration']])
        if dur is None:
            problems.append(f'{where}: длительность не число: «{cells[cols["duration"]]}»')
            continue
        if dur > args.max:
            problems.append(f'{where}: {fmt(dur)}, дольше порога {fmt(args.max)}. Разбей кадр или подними --max')
        if 'timecode' in cols and cells[cols['timecode']]:
            start = parse_start(cells[cols['timecode']])
            if start is None:
                problems.append(f'{where}: таймкод не читается: «{cells[cols["timecode"]]}»')
            elif abs(start - total) > 0.05:
                problems.append(f'{where}: таймкод {fmt(start)}, а по сумме прошлых кадров должен быть {fmt(round(total, 2))}')
        if 'source' in cols and cells[cols['source']]:
            src = cells[cols['source']].lower()
            if not any(s in src for s in SOURCES):
                problems.append(f'{where}: источник «{cells[cols["source"]]}» не из списка: съёмка, генерация, архив, сток, моушен, скриншот')
        total += dur
    return problems, total


def main(argv=None):
    ap = argparse.ArgumentParser(description='Проверка раскадровки в таблице markdown.')
    ap.add_argument('file', help='файл .md с таблицей кадров')
    ap.add_argument('--target', type=float, help='целевой хронометраж, секунды')
    ap.add_argument('--tolerance', type=float, default=1.0, help='допуск к целевому, секунды (по умолчанию 1)')
    ap.add_argument('--max', type=float, default=7.0, help='порог длины одного кадра, секунды (по умолчанию 7)')
    args = ap.parse_args(argv)

    path = Path(args.file)
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        print(f'Не могу прочитать файл {path}: {exc}')
        return 2

    found = find_table(text)
    if not found:
        print('Таблица кадров не найдена: нужна таблица markdown с колонкой «Длит.» и строкой-разделителем под заголовком.')
        return 2
    header, cols, rows = found
    if not rows:
        print('В таблице нет ни одного кадра.')
        return 2

    problems, total = check_rows(header, cols, rows, args)
    if args.target is not None and abs(total - args.target) > args.tolerance:
        diff = total - args.target
        word = 'длиннее' if diff > 0 else 'короче'
        problems.append(f'сумма длительностей {fmt(round(total, 2))}, это на {fmt(round(abs(diff), 2))} {word} цели {fmt(args.target)} (допуск {fmt(args.tolerance)})')

    print(f'Кадров: {len(rows)}, общий хронометраж: {fmt(round(total, 2))}')
    if problems:
        print(f'Найдено нарушений: {len(problems)}')
        for p in problems:
            print(f'  - {p}')
        return 1
    print('Чисто: таблица заполнена, хронометраж и длины кадров в порядке.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
