#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка обложки перед показом владельцу и вставкой в статью.

Что проверяет:
  - ширину файла (по умолчанию 1280, как ждёт вёрстка);
  - соотношение сторон (по умолчанию 16:9, допуск 1%);
  - с --prompt: слова из стоп-листа, соотношение сторон в тексте промпта
    (его передают только параметром модели) и наличие пресета лука.

Форматы: PNG, JPEG, WebP. Внешних зависимостей нет.

Запуск:
    python3 scripts/check_cover.py cover-v2.webp
    python3 scripts/check_cover.py cover-v2.webp --width 1280 --ratio 16:9
    python3 scripts/check_cover.py cover-v2.webp --prompt prompt.txt
    python3 scripts/check_cover.py --prompt prompt.txt      # только промпт

Код выхода: 0 - чисто, 1 - есть нарушения, 2 - файл не читается или
неверные аргументы.
"""

import argparse
import re
import struct
import sys
from pathlib import Path

# Стоп-лист: (регулярка, что не так). Русский и английский, промпты пишут
# на обоих. Это сито для частых штампов, а не полный список.
STOP_WORDS = [
    (r'\b(laptop|notebook computer|macbook)\b|ноутбук', 'ноутбук в кадре (стоп-лист 1)'),
    (r'\b(monitor|computer screen|desktop screen)\b|монитор', 'монитор в кадре (стоп-лист 1, 6)'),
    (r'\b(desk lamp|table lamp|warm lamp)\b|настольн\w* ламп', 'тёплая настольная лампа (стоп-лист 2)'),
    (r'\bheadphones?\b|наушник', 'наушники как реквизит (стоп-лист 4)'),
    (r'\b(coffee cup|cup of coffee|mug)\b|чашк', 'чашка, натюрморт (стоп-лист 6)'),
    (r'\b(still life)\b|натюрморт', 'натюрморт (стоп-лист 6)'),
    (r'\b(typing|using the app|scrolling (his|her|a) phone)\b', 'буквальное использование сервиса (стоп-лист 5)'),
    (r'\b(headline|title text|caption text|text overlay)\b|заголовок поверх', 'текст поверх кадра (стоп-лист 8)'),
]
# Ночь плюс тёплый свет в интерьере: проверяем сочетанием.
NIGHT = re.compile(r'\b(night|midnight|late evening)\b|ночь|ночью', re.I)
WARM = re.compile(r'\b(warm|tungsten|amber)\b|тёпл|тепл', re.I)
INTERIOR = re.compile(r'\b(room|interior|office|apartment|bedroom)\b|комнат|интерьер|офис', re.I)
# Соотношение сторон в тексте: 16:9, 4:3, 1:1, 9:16, "aspect ratio".
RATIO_IN_TEXT = re.compile(r'\b\d{1,2}\s*:\s*\d{1,2}\b|aspect ratio', re.I)
# Признак пресета лука: хотя бы одна из ключевых фраз ядра.
LOOK_MARKERS = re.compile(r'no sharpening|fine organic grain|no HDR', re.I)


def read_size(path):
    """Возвращает (ширина, высота) или бросает ValueError."""
    data = path.read_bytes()[:65536]
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        w, h = struct.unpack('>II', data[16:24])
        return w, h
    if data[:2] == b'\xff\xd8':
        return _jpeg_size(path.read_bytes())
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return _webp_size(data)
    raise ValueError('не PNG, не JPEG и не WebP')


def _jpeg_size(data):
    i = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack('>H', data[i + 2:i + 4])[0]
        if marker in sof:
            h, w = struct.unpack('>HH', data[i + 5:i + 9])
            return w, h
        i += 2 + length
    raise ValueError('в JPEG не найден блок с размерами')


def _webp_size(data):
    chunk = data[12:16]
    if chunk == b'VP8X':
        w = int.from_bytes(data[24:27], 'little') + 1
        h = int.from_bytes(data[27:30], 'little') + 1
        return w, h
    if chunk == b'VP8L':
        b = int.from_bytes(data[21:25], 'little')
        return (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
    if chunk == b'VP8 ':
        w, h = struct.unpack('<HH', data[26:30])
        return w & 0x3FFF, h & 0x3FFF
    raise ValueError('неизвестный вариант WebP')


def parse_ratio(text):
    m = re.fullmatch(r'(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)', text.strip())
    if not m or float(m.group(2)) == 0:
        raise argparse.ArgumentTypeError('соотношение пишется как 16:9')
    return float(m.group(1)) / float(m.group(2)), text.strip()


def check_image(path, want_width, ratio):
    problems = []
    w, h = read_size(path)
    print(f'Файл: {path.name}, {w}x{h}')
    if want_width and w != want_width:
        problems.append(f'ширина {w}, вёрстка ждёт {want_width}. Уменьши или пересохрани.')
    want, label = ratio
    real = w / h if h else 0
    if abs(real - want) / want > 0.01:
        hint = ' Похоже на квадрат 1:1: соотношение не передали параметром модели?' if abs(real - 1) < 0.01 else ''
        problems.append(f'пропорции {w}x{h} ({real:.3f}), нужно {label} ({want:.3f}).{hint}')
    return problems


def check_prompt(path):
    problems = []
    text = path.read_text(encoding='utf-8')
    for rx, what in STOP_WORDS:
        m = re.search(rx, text, re.I)
        if m:
            problems.append(f'промпт: {what}: «{m.group(0)}»')
    if NIGHT.search(text) and WARM.search(text) and INTERIOR.search(text):
        problems.append('промпт: ночь + тёплый свет + интерьер, даёт коричневое мыло (стоп-лист 3)')
    m = RATIO_IN_TEXT.search(text)
    if m:
        problems.append(f'промпт: соотношение сторон в тексте «{m.group(0)}». Убери, передай параметром модели.')
    if not LOOK_MARKERS.search(text):
        problems.append('промпт: нет пресета лука в конце (no sharpening, fine organic grain, no HDR)')
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description='Проверка обложки статьи')
    ap.add_argument('image', nargs='?', help='файл обложки (PNG, JPEG, WebP)')
    ap.add_argument('--width', type=int, default=1280, help='ширина под вёрстку, 0 чтобы не проверять')
    ap.add_argument('--ratio', type=parse_ratio, default=parse_ratio('16:9'), help='соотношение сторон, например 16:9')
    ap.add_argument('--prompt', help='текстовый файл с промптом')
    args = ap.parse_args(argv)
    if not args.image and not args.prompt:
        ap.error('нужен файл обложки или --prompt')

    problems = []
    try:
        if args.image:
            problems += check_image(Path(args.image), args.width, args.ratio)
        if args.prompt:
            problems += check_prompt(Path(args.prompt))
    except (OSError, ValueError, struct.error) as e:
        print(f'Не могу прочитать файл: {e}', file=sys.stderr)
        return 2

    if problems:
        print(f'Найдено нарушений: {len(problems)}')
        for p in problems:
            print(f'  - {p}')
        return 1
    print('Чисто. Дальше глазами: зум на логотипы, руки, лица, смысл кадра.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
