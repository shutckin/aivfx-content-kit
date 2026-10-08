#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сбор поисковых подсказок Google по затравке.

Что делает: берёт затравку (например «suno»), подставляет к ней буквы
алфавита и вопросительные слова, спрашивает публичный эндпойнт подсказок
и печатает уникальные подсказки в CSV. Это список того, что люди реально
набирают, без цифр частотности.

Запуск:
    python3 scripts/suggest.py "suno"
    python3 scripts/suggest.py "kling" --hl en --out kling.csv
    python3 scripts/suggest.py "seedance" --pause 2 --no-alphabet
    python3 scripts/suggest.py "suno" --dry-run   # только план запросов, без сети

Код выхода: 0 - собрано, 1 - ни один запрос не прошёл (сеть, блокировка),
2 - неверные аргументы. Внешних зависимостей нет.
"""

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://suggestqueries.google.com/complete/search"
USER_AGENT = "Mozilla/5.0 (compatible; aivfx-blog-suggest/1.0)"
TIMEOUT_SEC = 10
# После стольких сетевых ошибок подряд считаем, что сети нет, и выходим.
MAX_FAILS_IN_ROW = 3

ALPHABETS = {
    "ru": list("абвгдеёжзийклмнопрстуфхцчшщэюя"),
    "en": list("abcdefghijklmnopqrstuvwxyz"),
}

# Вопросительные слова ставятся ПЕРЕД затравкой: «как suno», «сколько suno».
QUESTIONS = {
    "ru": ["как", "что", "где", "почему", "зачем", "сколько", "можно ли",
           "какой", "когда", "чем", "стоит ли", "нужно ли"],
    "en": ["how", "what", "where", "why", "how much", "can", "is",
           "which", "when", "best", "vs"],
}


def build_prefixes(seed, lang, use_alphabet, use_questions):
    """Список запросов к подсказкам: сама затравка, затравка+буква, вопрос+затравка."""
    prefixes = [seed]
    if use_alphabet:
        prefixes += [f"{seed} {ch}" for ch in ALPHABETS.get(lang, ALPHABETS["en"])]
    if use_questions:
        prefixes += [f"{q} {seed}" for q in QUESTIONS.get(lang, QUESTIONS["en"])]
    return prefixes


def fetch_suggestions(prefix, lang):
    """Один запрос к эндпойнту. Возвращает список подсказок или бросает исключение."""
    params = urllib.parse.urlencode({
        "client": "firefox", "hl": lang, "q": prefix,
        "ie": "utf-8", "oe": "utf-8",
    })
    req = urllib.request.Request(f"{ENDPOINT}?{params}",
                                 headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        raw = resp.read()
    data = json.loads(raw.decode("utf-8", errors="replace"))
    # Ответ вида ["запрос", ["подсказка 1", "подсказка 2", ...], ...]
    if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
        raise ValueError("неожиданный формат ответа")
    return [s for s in data[1] if isinstance(s, str)]


def collect(prefixes, lang, pause):
    """Обходит все запросы с паузой. Возвращает (строки, число успешных, ошибки)."""
    seen = set()
    rows = []
    ok = 0
    errors = []
    fails_in_row = 0
    for i, prefix in enumerate(prefixes):
        if i > 0:
            time.sleep(pause)
        try:
            suggestions = fetch_suggestions(prefix, lang)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"{prefix}: {exc}")
            fails_in_row += 1
            if fails_in_row >= MAX_FAILS_IN_ROW and ok == 0:
                break
            continue
        ok += 1
        fails_in_row = 0
        for s in suggestions:
            key = " ".join(s.lower().split())
            if key and key not in seen:
                seen.add(key)
                rows.append({"подсказка": s.strip(), "затравка": prefix})
    return rows, ok, errors


def write_csv(rows, out_path):
    fields = ["подсказка", "затравка"]
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Уникальные поисковые подсказки Google по затравке, вывод CSV.")
    p.add_argument("seed", help="затравка, например «suno» или «claude code»")
    p.add_argument("--hl", default="ru", choices=sorted(ALPHABETS),
                   help="язык подсказок и алфавита (по умолчанию ru)")
    p.add_argument("--pause", type=float, default=1.0,
                   help="пауза между запросами в секундах (по умолчанию 1.0, меньше 0.5 не ставь)")
    p.add_argument("--out", help="файл CSV; без него печать в консоль")
    p.add_argument("--no-alphabet", action="store_true", help="не обходить алфавит")
    p.add_argument("--no-questions", action="store_true", help="не добавлять вопросительные слова")
    p.add_argument("--dry-run", action="store_true", help="показать план запросов без сети")
    args = p.parse_args(argv)
    args.seed = " ".join(args.seed.split())
    if not args.seed:
        p.error("затравка пустая")
    if args.pause < 0.5:
        p.error("пауза меньше 0.5 секунды: так быстро ловят блокировку")
    return args


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    prefixes = build_prefixes(args.seed, args.hl,
                              not args.no_alphabet, not args.no_questions)

    if args.dry_run:
        print(f"План: {len(prefixes)} запросов, пауза {args.pause} с.", file=sys.stderr)
        for p in prefixes:
            print(p)
        return 0

    est = round(len(prefixes) * args.pause)
    print(f"Запросов: {len(prefixes)}, займёт около {est} с.", file=sys.stderr)
    rows, ok, errors = collect(prefixes, args.hl, args.pause)

    if ok == 0:
        print("Не удалось получить ни одной подсказки. Похоже, нет сети или эндпойнт "
              "недоступен из этой сети (VPN, блокировка, песочница).", file=sys.stderr)
        if errors:
            print(f"Первая ошибка: {errors[0]}", file=sys.stderr)
        return 1

    write_csv(rows, args.out)
    where = f" в файл {args.out}" if args.out else ""
    print(f"Готово: {len(rows)} уникальных подсказок{where}. "
          f"Успешных запросов {ok} из {len(prefixes)}.", file=sys.stderr)
    if errors:
        print(f"Не прошло запросов: {len(errors)} (например: {errors[0]})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
