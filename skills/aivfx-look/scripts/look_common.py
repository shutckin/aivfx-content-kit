"""Общая часть для build_prompt.py и check_prompt.py: пресеты, слова-ломатели,
поиск соотношения сторон. Только стандартная библиотека Python 3.
"""
import json
import pathlib
import re
import sys

PRESETS_DIR = pathlib.Path(__file__).resolve().parent.parent / 'presets'
REQUIRED = ('name', 'title', 'description', 'use_when', 'avoid_when', 'core',
            'grade', 'video_motion', 'video_dialogue', 'banned_words')
MODES = ('photo', 'video', 'dialogue')

# Общий список слов, которые ломают плёночный лук: они просят у модели
# цифровую резкость, HDR и «рекламный» пластик. Пресет может добавить свои.
BANNED_COMMON = [
    '16k', '8k', '4k', 'uhd',
    'ultra detailed', 'ultra-detailed', 'highly detailed', 'extremely detailed',
    'intricate details', 'insane detail', 'hyper detailed', 'hyper-detailed',
    'hyperrealistic', 'hyper-realistic', 'hyper realistic',
    'ultra realistic', 'ultra-realistic', 'photorealistic 8k',
    'sharp focus', 'ultra sharp', 'razor sharp', 'crisp details', 'tack sharp',
    'hdr', 'hdri',
    'masterpiece', 'best quality', 'ultra quality', 'high quality',
    'octane render', 'unreal engine', 'vray', 'v-ray', 'redshift render',
    'trending on artstation', 'award winning photo', 'award-winning photo',
]

# Известные соотношения сторон. (?<![\d:]) и (?![\d:]) не дают поймать время 4:30.
_RATIOS = ('1:1', '4:3', '3:4', '16:9', '9:16', '3:2', '2:3', '21:9', '9:21', '4:5', '5:4', '2:1', '1:2')
_RATIO_RX = '|'.join(r.replace(':', r'\s*:\s*') for r in _RATIOS)
ASPECT_PATTERNS = [
    re.compile(r'--(?:ar|aspect(?:_ratio)?)\s*[= ]?\s*\d{1,2}\s*:\s*\d{1,2}', re.I),
    re.compile(r'\baspect[ _-]?ratio\s*(?:of\s*)?[:=]?\s*\d{1,2}\s*:\s*\d{1,2}', re.I),
    re.compile(r'(?<![\d:])(?:' + _RATIO_RX + r')(?![\d:])'),
]


def die(msg):
    print(f'Ошибка: {msg}', file=sys.stderr)
    sys.exit(2)


def list_presets():
    return sorted(PRESETS_DIR.glob('*.json'))


def load_preset(ref):
    """Принимает имя пресета из папки presets или путь к своему json."""
    path = pathlib.Path(ref)
    if not path.suffix:
        path = PRESETS_DIR / f'{ref}.json'
    if not path.exists():
        names = ', '.join(p.stem for p in list_presets()) or 'нет ни одного'
        die(f'пресет «{ref}» не найден. Есть: {names}. '
            'Можно передать и путь к своему json.')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        die(f'файл {path.name} не читается как json: строка {e.lineno}, '
            f'столбец {e.colno}: {e.msg}')
    if not isinstance(data, dict):
        die(f'в {path.name} должен быть объект {{...}}, а не список или строка')
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        die(f'в {path.name} нет полей: {", ".join(missing)}')
    if not str(data['core']).strip():
        die(f'в {path.name} пустое поле core: без ядра лука нет')
    for k in ('use_when', 'avoid_when', 'banned_words'):
        if not isinstance(data[k], list):
            die(f'в {path.name} поле {k} должно быть списком')
    return data


def norm(text):
    """Схлопывает пробелы и переносы, чтобы сравнивать текст без учёта вёрстки."""
    return re.sub(r'\s+', ' ', text).strip().lower()


def find_aspects(text):
    # Шаблоны идут от длинного к короткому: найденное вырезаем сразу,
    # чтобы «--ar 4:3» не засчитывалось второй раз как голое «4:3».
    found = []
    for rx in ASPECT_PATTERNS:
        found += [m.group(0) for m in rx.finditer(text)]
        text = rx.sub(' ', text)
    return found


def strip_aspects(text):
    for rx in ASPECT_PATTERNS:
        text = rx.sub('', text)
    return text


def banned_regex(word):
    # «HDR» внутри «no HDR» это часть лука, а не ломатель.
    rx = r'(?<![\w-])' + re.escape(word) + r'(?![\w-])'
    if word.lower() in ('hdr', 'hdri'):
        rx = r'(?<!no )' + rx
    return re.compile(rx, re.I)


def find_banned(text, extra):
    hits = []
    for w in BANNED_COMMON + list(extra):
        hits += [m.group(0) for m in banned_regex(w).finditer(text)]
    return hits


def strip_banned(text, extra):
    # Длинные фразы первыми, чтобы «hyper realistic» не порезалось кусками.
    for w in sorted(BANNED_COMMON + list(extra), key=len, reverse=True):
        text = banned_regex(w).sub('', text)
    return text


def tidy(text):
    """Убирает следы вырезания: двойные запятые, пробелы перед точкой."""
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\(\s*\)', '', text)
    text = re.sub(r'\s*,\s*(?:,\s*)+', ', ', text)
    text = re.sub(r'\s+([,.;:])', r'\1', text)
    text = re.sub(r'([,;])\s*\.', '.', text)
    text = re.sub(r'(^|\n)\s*[,;]\s*', r'\1', text)
    text = re.sub(r',\s*$', '', text, flags=re.M)
    return '\n'.join(line.strip() for line in text.splitlines()).strip()
