#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Отчёт по журналу кликов переходника /go/<партнёр>?from=<страница>.<место>.

Журнал пишет nginx по формату goclick из scripts/go-redirect.nginx.conf:
  2026-10-01T10:15:00+03:00 to=/go/example from=plastikovye-kartinki.facts country=RU ref="..." ua="..."

Что делает:
  - отсеивает ботов, сканеры и превью мессенджеров по строке браузера;
  - склеивает повторы: тот же браузер, та же метка и тот же партнёр в
    течение 60 секунд считаются одним кликом (IP не пишется, поэтому это
    нижняя граница, а не точное число людей);
  - считает клики по партнёрам, страницам, местам на странице и странам.

Запуск:
    python3 scripts/clicks_report.py clicks.log
    python3 scripts/clicks_report.py clicks.log --days 7
    python3 scripts/clicks_report.py clicks.log --window 0     # без склейки

Код выхода: 0 - чисто, 1 - есть клики без метки from, с кривой меткой или
нераспознанные строки (значит, ссылка на сайте стоит мимо схемы или
сломан формат журнала), 2 - файл не читается или неверные аргументы.
"""

import argparse
import collections
import datetime
import re
import sys
from pathlib import Path

LINE = re.compile(
    r'^(?P<time>\S+) to=(?P<to>\S+) from=(?P<src>\S*) country=(?P<country>\S*) '
    r'ref="(?P<ref>[^"]*)" ua="(?P<ua>[^"]*)"\s*$'
)
# Метка: <страница>.<место>, латиница, цифры, дефис.
GOOD_FROM = re.compile(r'^[a-z0-9][a-z0-9-]*\.[a-z0-9-]+$')
# Боты, сканеры, превью ссылок в мессенджерах и соцсетях, HTTP-библиотеки.
# Слово telegram целиком не режем: встроенный браузер Telegram на Android
# пишет его в строку браузера, а это живой человек. Превью Telegram
# приходит как TelegramBot и отсеивается по слову bot.
# Яндекс целиком тоже не режем: мобильное приложение Яндекса (YandexSearch)
# и Яндекс Браузер это люди. Роботы Яндекса ловятся по bot/robot
# (YandexBot, YandexMobileBot) и по названиям служебных роботов ниже.
BOTS = re.compile(
    r'bot|robot|crawl|spider|slurp|preview|scan|monitor|headless|phantom|lighthouse'
    r'|curl|wget|python|httpx|aiohttp|go-http|okhttp|axios|node-fetch|java/|libwww|php'
    r'|facebookexternalhit|whatsapp|vkshare|skype|discord'
    r'|yandex(?:metrika|images|direct|media|favicons|webmaster|pagechecker|video|imageresizer|turbo)',
    re.I,
)
EMPTY = {'', '-'}


def parse_args(argv):
    ap = argparse.ArgumentParser(description='Отчёт по журналу кликов /go/')
    ap.add_argument('log', help='файл журнала кликов')
    ap.add_argument('--days', type=int, default=0, help='только последние N дней (0 - всё)')
    ap.add_argument('--window', type=int, default=60, help='склейка повторов, секунд (0 - выключить)')
    ap.add_argument('--last', type=int, default=10, help='сколько последних кликов показать')
    args = ap.parse_args(argv)
    if args.days < 0 or args.window < 0 or args.last < 0:
        ap.error('числа должны быть не меньше нуля')
    return args


def read_rows(path, since):
    """Разбирает журнал. Возвращает (клики, боты, нераспознанные строки)."""
    rows, bots, broken = [], 0, []
    with path.open(encoding='utf-8', errors='replace') as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            m = LINE.match(line)
            if not m:
                broken.append(n)
                continue
            try:
                when = datetime.datetime.fromisoformat(m['time'])
            except ValueError:
                broken.append(n)
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=datetime.timezone.utc)
            if since and when < since:
                continue
            ua = m['ua']
            if ua in EMPTY or BOTS.search(ua):
                bots += 1
                continue
            partner = m['to'].split('?')[0].removeprefix('/go/').strip('/') or '(пусто)'
            src = '' if m['src'] in EMPTY else m['src'][:80]
            country = '?' if m['country'] in EMPTY else m['country'][:3]
            rows.append({'when': when, 'partner': partner, 'src': src, 'country': country, 'ua': ua})
    return rows, bots, broken


def merge_repeats(rows, window):
    """Склеивает повторы одного браузера с той же меткой за window секунд."""
    if not window:
        return rows, 0
    last_seen, kept, merged = {}, [], 0
    for r in sorted(rows, key=lambda r: r['when']):
        key = (r['partner'], r['src'], r['country'], r['ua'])
        prev = last_seen.get(key)
        last_seen[key] = r['when']
        if prev and (r['when'] - prev).total_seconds() <= window:
            merged += 1
            continue
        kept.append(r)
    return kept, merged


def print_counter(title, counter):
    print(title)
    for name, n in counter.most_common():
        print(f'  {n:>5}  {name}')
    print()


def report(rows, bots, merged, broken, days):
    period = f'за {days} дн.' if days else 'за всё время в журнале'
    print(f'Кликов людей {period}: {len(rows)}')
    print(f'Отсеяно ботов и превью: {bots}, склеено повторов: {merged}')
    print()
    if rows:
        print_counter('По партнёрам:', collections.Counter(r['partner'] for r in rows))
        print_counter('По страницам и местам:', collections.Counter(r['src'] or '(без метки)' for r in rows))
        places = collections.Counter(r['src'].split('.')[-1] for r in rows if GOOD_FROM.match(r['src']))
        if places:
            print_counter('По месту на странице:', places)
        print('По странам: ' + ', '.join(f'{c} {n}' for c, n in collections.Counter(r['country'] for r in rows).most_common()))
        print()

    unlabeled = [r for r in rows if not r['src']]
    crooked = sorted({r['src'] for r in rows if r['src'] and not GOOD_FROM.match(r['src'])})
    problems = []
    if unlabeled:
        problems.append(f'кликов без метки from: {len(unlabeled)}. Найди на сайте ссылки на /go/ без ?from=')
    if crooked:
        problems.append('кривые метки (нужно страница.место): ' + ', '.join(crooked[:10]))
    if broken:
        problems.append(f'нераспознанных строк: {len(broken)} (строки {", ".join(map(str, broken[:10]))}). Формат журнала не совпадает с goclick?')
    return problems


def main(argv=None):
    args = parse_args(argv)
    path = Path(args.log)
    since = None
    if args.days:
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.days)
    try:
        rows, bots, broken = read_rows(path, since)
    except OSError as e:
        print(f'Не могу прочитать журнал: {e}', file=sys.stderr)
        return 2

    rows, merged = merge_repeats(rows, args.window)
    problems = report(rows, bots, merged, broken, args.days)

    if rows and args.last:
        print(f'Последние {min(args.last, len(rows))}:')
        for r in rows[-args.last:]:
            print(f"  {r['when']:%d.%m %H:%M}  {r['country']:<3} {r['partner']:<16} {r['src'] or '(без метки)'}")
        print()

    if problems:
        print(f'Нарушений: {len(problems)}')
        for p in problems:
            print(f'  - {p}')
        return 1
    print('Разметка ссылок в порядке.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
