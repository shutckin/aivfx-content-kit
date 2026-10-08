#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка файла превью перед показом владельцу и загрузкой на YouTube.

Что проверяет:
  - размер: 1280x720 для роликов, 1080x1920 для Shorts (флаг --shorts);
  - вес файла: до 2 МБ (лимит YouTube на превью);
  - имя файла: латиница, цифры, дефис, точка и подчёркивание, без пробелов;
  - формат: PNG или JPEG (размер читается из заголовка без сторонних библиотек).

Запуск:
    python3 scripts/check_thumb.py finals/cheap-cam-a-face-v1.jpg
    python3 scripts/check_thumb.py --shorts finals/cheap-cam-short-a-v1.jpg
    python3 scripts/check_thumb.py finals/*.jpg
    python3 scripts/check_thumb.py --make-test test-thumb.png
    python3 scripts/check_thumb.py --make-test test-short.png --shorts

--make-test создаёт серый PNG нужного размера (средствами zlib и struct)
и сразу его проверяет: так можно убедиться, что сам скрипт работает.

Код выхода: 0 - чисто, 1 - есть нарушения, 2 - файл не читается или
неверные аргументы.
"""

import argparse
import re
import struct
import sys
import zlib
from pathlib import Path

VIDEO_SIZE = (1280, 720)
SHORTS_SIZE = (1080, 1920)
MAX_BYTES = 2 * 1024 * 1024
# Разрешённые символы имени: латиница, цифры, дефис, подчёркивание, точка.
NAME_OK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
EXTENSIONS = {'.png', '.jpg', '.jpeg'}
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def read_size(path):
    """Возвращает (формат, ширина, высота) или бросает ValueError."""
    data = path.read_bytes()
    if data[:8] == PNG_SIGNATURE:
        if len(data) < 24 or data[12:16] != b'IHDR':
            raise ValueError('PNG без блока IHDR, файл повреждён')
        w, h = struct.unpack('>II', data[16:24])
        return 'PNG', w, h
    if data[:2] == b'\xff\xd8':
        w, h = _jpeg_size(data)
        return 'JPEG', w, h
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        raise ValueError('WebP: YouTube превью в WebP не принимает, сохрани в JPEG или PNG')
    raise ValueError('не PNG и не JPEG')


def _jpeg_size(data):
    """Ищет маркер SOF и читает из него размеры."""
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01, 0xFF) or 0xD0 <= marker <= 0xD7:
            i += 1 if marker == 0xFF else 2
            continue
        length = struct.unpack('>H', data[i + 2:i + 4])[0]
        if marker in JPEG_SOF:
            h, w = struct.unpack('>HH', data[i + 5:i + 9])
            return w, h
        i += 2 + length
    raise ValueError('JPEG без маркера размеров, файл повреждён')


def check_file(path, expected):
    """Возвращает список нарушений для одного файла."""
    problems = []
    name = path.name
    if ' ' in name:
        problems.append('в имени пробел, замени на дефис')
    elif not NAME_OK.match(name):
        problems.append('в имени не латиница или лишние символы, '
                        'нужны только a-z, 0-9, дефис')
    if path.suffix.lower() not in EXTENSIONS:
        problems.append(f'расширение {path.suffix or "(нет)"}, нужно .jpg или .png')

    size = path.stat().st_size
    if size > MAX_BYTES:
        problems.append(f'вес {size / 1024 / 1024:.2f} МБ, больше 2 МБ: '
                        'сожми JPEG или уменьши качество')

    fmt, w, h = read_size(path)
    if (w, h) != expected:
        problems.append(f'размер {w}x{h}, нужен {expected[0]}x{expected[1]}')
    return fmt, w, h, size, problems


def make_test_png(path, size):
    """Пишет серый PNG заданного размера без сторонних библиотек."""
    w, h = size
    row = b'\x00' + b'\x80' * w  # байт фильтра плюс серые пиксели (оттенки серого)
    raw = row * h

    def chunk(kind, body):
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', crc)

    ihdr = struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0)  # 8 бит, оттенки серого
    png = (PNG_SIGNATURE + chunk(b'IHDR', ihdr)
           + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))
    path.write_bytes(png)


def main():
    parser = argparse.ArgumentParser(description='Проверка файла превью YouTube')
    parser.add_argument('files', nargs='*', help='файлы превью (PNG или JPEG)')
    parser.add_argument('--shorts', action='store_true',
                        help='проверять размер Shorts 1080x1920 вместо 1280x720')
    parser.add_argument('--make-test', metavar='ФАЙЛ',
                        help='создать тестовый PNG нужного размера и проверить его')
    args = parser.parse_args()

    expected = SHORTS_SIZE if args.shorts else VIDEO_SIZE
    files = [Path(f) for f in args.files]
    if args.make_test:
        test_path = Path(args.make_test)
        make_test_png(test_path, expected)
        print(f'Создан тестовый файл {test_path} ({expected[0]}x{expected[1]})')
        files.append(test_path)
    if not files:
        print('Ошибка: не указан ни один файл. Пример: '
              'python3 scripts/check_thumb.py finals/cheap-cam-a-face-v1.jpg')
        return 2

    bad, broken = 0, 0
    for path in files:
        if not path.is_file():
            print(f'НЕ НАЙДЕН  {path}')
            broken += 1
            continue
        try:
            fmt, w, h, size, problems = check_file(path, expected)
        except ValueError as err:
            print(f'НЕ ЧИТАЕТСЯ  {path}: {err}')
            broken += 1
            continue
        info = f'{fmt} {w}x{h}, {size / 1024:.0f} КБ'
        if problems:
            bad += 1
            print(f'НАРУШЕНИЯ  {path} ({info})')
            for p in problems:
                print(f'  - {p}')
        else:
            print(f'ЧИСТО  {path} ({info})')

    print(f'Итого: файлов {len(files)}, с нарушениями {bad}, не прочитано {broken}.')
    print('Напоминание: уменьши превью до ширины около 200 пикселей и посмотри '
          'глазами рядом с чужими, скрипт смысл не проверяет.')
    if broken:
        return 2
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
