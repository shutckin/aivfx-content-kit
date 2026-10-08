#!/usr/bin/env python3
"""Проверка бренд-файла моушен-графики.

Запуск:
  python3 check_brand.py brand.json
  python3 check_brand.py brand.json другой-бренд.json

Проверяет: обязательные поля, цвета в hex, контраст текста к фону не ниже
4.5:1, запрет моноширинных и пиксельных шрифтов, размеры текста для телефона,
длительности движения и сцен в разумных пределах, безопасные зоны внутри кадра.
Ключи, которые начинаются с «_», считаются комментариями и пропускаются.
Код выхода 1 при ошибках, 0 если чисто (предупреждения код не меняют).
"""
import json
import pathlib
import re
import sys

REQUIRED = {
    'name': str,
    'colors': dict,
    'fonts': dict,
    'type_scale': dict,
    'motion': dict,
    'timing': dict,
    'layout': dict,
}
REQUIRED_COLORS = ('bg', 'ink', 'mute', 'accent')
REQUIRED_FONTS = ('display', 'body')
REQUIRED_ROLES = ('hook', 'name', 'chapter', 'number', 'endcard')
HEX = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')

# Пары «текст на фоне», которые должны держать 4.5:1. Берутся, если оба цвета есть.
TEXT_PAIRS = [
    ('ink', 'bg'), ('ink', 'surface'), ('mute', 'bg'),
    ('mute', 'surface'), ('on_accent', 'accent'),
]
MIN_CONTRAST = 4.5
ACCENT_MIN = 3.0  # акцент на фоне: линии и крупные слова, мягче, чем текст

# Моноширинные и пиксельные («терминальные») шрифты запрещены.
BANNED_FONT = re.compile(
    r'(?i)\bmono\b|monospace|\bcode\b|courier|consola|menlo|monaco|'
    r'iosevka|\bhack\b|cascadia|inconsolata|press start|vt323|silkscreen|'
    r'pixel|\bterminal\b|ocr-?a|ocr-?b|space mono|ibm plex mono'
)

# Разумные пределы, секунды. Вне их движение дёргается или тянется.
MOTION_LIMITS = {
    'enter_sec': (0.15, 1.2),
    'exit_sec': (0.1, 0.8),
    'stagger_sec': (0.0, 0.4),
    'word_stagger_sec': (0.1, 0.7),
}
TIMING_LIMITS = {
    'sec_per_word': (0.2, 0.6),
    'min_hold_sec': (0.8, 4.0),
}
SCENE_LIMITS = {
    'hook': (1.0, 3.5),
    'name': (2.5, 8.0),
    'chapter': (1.5, 6.0),
    'number': (2.0, 6.0),
    'endcard': (3.0, 10.0),
}
MIN_TEXT_PX = 28  # на кадре с короткой стороной 1080
FRAMES = {'16:9': (1920, 1080), '9:16': (1080, 1920)}


def clean(obj):
    """Убирает ключи-комментарии, начинающиеся с «_»."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items() if not str(k).startswith('_')}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj


def luminance(hex_color):
    """Относительная яркость по WCAG."""
    h = hex_color.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    chans = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        chans.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = chans
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_colors(colors, errors, warnings):
    for key in REQUIRED_COLORS:
        if key not in colors:
            errors.append(f'colors: нет цвета «{key}»')
    valid = {}
    for key, val in colors.items():
        if not isinstance(val, str) or not HEX.match(val):
            errors.append(f'colors.{key}: «{val}» не hex. Пиши #RRGGBB, '
                          'прозрачность задавай в layout.plate_opacity')
        else:
            valid[key] = val
    if len(valid) > 6:
        warnings.append(f'colors: {len(valid)} цветов. Больше пяти активных '
                        'обычно значит, что цвета украшают, а не объясняют')
    for fg, bg in TEXT_PAIRS:
        if fg in valid and bg in valid:
            ratio = contrast(valid[fg], valid[bg])
            if ratio < MIN_CONTRAST:
                errors.append(f'контраст {fg} на {bg}: {ratio:.2f}:1, '
                              f'нужно не ниже {MIN_CONTRAST}:1')
    if 'accent' in valid and 'bg' in valid:
        ratio = contrast(valid['accent'], valid['bg'])
        if ratio < ACCENT_MIN:
            warnings.append(f'акцент на фоне: {ratio:.2f}:1. Линию увидят, '
                            'а слово акцентом на телефоне потеряется')


def check_fonts(fonts, errors):
    for role in REQUIRED_FONTS:
        if role not in fonts:
            errors.append(f'fonts: нет роли «{role}»')
    for role, spec in fonts.items():
        if not isinstance(spec, dict) or not spec.get('family'):
            errors.append(f'fonts.{role}: нужен объект с полем family')
            continue
        text = ' '.join(str(spec.get(k, '')) for k in ('family', 'fallback', 'file'))
        m = BANNED_FONT.search(text)
        if m:
            errors.append(f'fonts.{role}: «{spec["family"]}» похож на моноширинный '
                          f'или пиксельный шрифт ({m.group(0)}). Нужен санс или '
                          'сериф, цифры через tnum')
        if not spec.get('file'):
            errors.append(f'fonts.{role}: нет file. Шрифт из интернета может не '
                          'догрузиться во время рендера, подключай локальный файл')


def check_range(section, data, limits, errors, required=True):
    for key, (lo, hi) in limits.items():
        if key not in data:
            if required:
                errors.append(f'{section}: нет поля «{key}»')
            continue
        val = data[key]
        if not is_number(val):
            errors.append(f'{section}.{key}: нужно число, а не «{val}»')
        elif not lo <= val <= hi:
            errors.append(f'{section}.{key}: {val} вне разумного {lo}-{hi}')


def check_type(scale, errors):
    for key, val in scale.items():
        if key in ('line_height', 'max_chars_per_line'):
            continue
        if not is_number(val):
            errors.append(f'type_scale.{key}: нужно число пикселей')
        elif val < MIN_TEXT_PX:
            errors.append(f'type_scale.{key}: {val} px. На телефоне меньше '
                          f'{MIN_TEXT_PX} px при кадре 1080 не читается')
    chars = scale.get('max_chars_per_line')
    if is_number(chars) and chars > 42:
        errors.append(f'type_scale.max_chars_per_line: {chars}. Длинную строку '
                      'на телефоне не успевают прочитать, держи до 42')


def check_timing(timing, errors):
    check_range('timing', timing, TIMING_LIMITS, errors)
    fps = timing.get('fps')
    if fps not in (24, 25, 30, 50, 60):
        errors.append(f'timing.fps: «{fps}». Ставь частоту кадров ролика: '
                      '24, 25, 30, 50 или 60')
    scenes = timing.get('scene_sec')
    if not isinstance(scenes, dict):
        errors.append('timing: нет scene_sec с длительностями ролей')
        return
    for role in REQUIRED_ROLES:
        if role not in scenes:
            errors.append(f'timing.scene_sec: нет роли «{role}»')
    check_range('timing.scene_sec', scenes, SCENE_LIMITS, errors, required=False)


def check_safe(layout, errors):
    safe = layout.get('safe')
    if not isinstance(safe, dict):
        errors.append('layout: нет safe с безопасными зонами')
        return
    for ratio, (w, h) in FRAMES.items():
        zone = safe.get(ratio)
        if not isinstance(zone, dict):
            errors.append(f'layout.safe: нет зоны для {ratio}')
            continue
        sides = {k: zone.get(k) for k in ('top', 'bottom', 'left', 'right')}
        if not all(is_number(v) and v >= 0 for v in sides.values()):
            errors.append(f'layout.safe.{ratio}: нужны числа top, bottom, left, right')
            continue
        if sides['left'] + sides['right'] > w * 0.4 or sides['top'] + sides['bottom'] > h * 0.5:
            errors.append(f'layout.safe.{ratio}: отступы съедают больше половины '
                          'кадра, проверь числа')
        if ratio == '9:16' and (sides['top'] < 180 or sides['bottom'] < 300):
            errors.append('layout.safe.9:16: сверху меньше 180 px или снизу меньше '
                          '300 px. Там кнопки и подпись площадки, текст закроют')


def check_brand(data):
    errors, warnings = [], []
    if not isinstance(data, dict):
        return ['файл должен быть объектом JSON'], warnings
    for key, kind in REQUIRED.items():
        if key not in data:
            errors.append(f'нет обязательного поля «{key}»')
        elif not isinstance(data[key], kind):
            errors.append(f'поле «{key}» должно быть {"объектом" if kind is dict else "строкой"}')
    if errors:
        return errors, warnings
    check_colors(data['colors'], errors, warnings)
    check_fonts(data['fonts'], errors)
    check_type(data['type_scale'], errors)
    check_range('motion', data['motion'], MOTION_LIMITS, errors)
    check_timing(data['timing'], errors)
    check_safe(data['layout'], errors)
    return errors, warnings


def main(paths):
    if not paths:
        print('Использование: python3 check_brand.py brand.json [ещё.json]')
        return 1
    failed = False
    for path in paths:
        try:
            raw = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
        except OSError as e:
            print(f'{path}: не могу прочитать файл: {e.strerror}')
            failed = True
            continue
        except json.JSONDecodeError as e:
            print(f'{path}: сломанный JSON, строка {e.lineno}, позиция {e.colno}: {e.msg}')
            failed = True
            continue
        errors, warnings = check_brand(clean(raw))
        for w in warnings:
            print(f'{path}: предупреждение: {w}')
        if errors:
            failed = True
            print(f'{path}: найдено {len(errors)}')
            for e in errors:
                print(f'  - {e}')
        else:
            print(f'{path}: чисто')
    return 1 if failed else 0


if __name__ == '__main__':
    if any(a in ('-h', '--help') for a in sys.argv[1:]):
        print(__doc__ or 'Справка в начале файла.')
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
