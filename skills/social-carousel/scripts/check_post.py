#!/usr/bin/env python3
"""Проверка файла партии постов для Instagram, Threads и Pinterest.

Запуск:
    python3 check_post.py batch.json            # проверка партии перед показом
    python3 check_post.py batch.json --publish  # строже: перед постановкой в очередь

Код выхода 0, если нарушений нет (предупреждения допустимы), 1 при нарушениях
или если файл не читается. Только стандартная библиотека.

Формат файла смотри в examples/batch.example.json.
"""
import json
import re
import sys

THREADS_MAX = 500        # Threads API отказывает при тексте длиннее
IG_CAPTION_MAX = 2200    # лимит подписи Instagram
IG_HASHTAGS_MAX = 30     # лимит хэштегов Instagram
SLIDES_MIN = 2           # карусель из одного кадра это не карусель
SLIDES_API_WARN = 10     # лимит API бывает ниже, чем в приложении
PINS_PER_DAY_WARN = 70   # по наблюдению, проверь у себя
DASHES = (chr(0x2014), chr(0x2013))  # длинное и среднее тире, заданы кодом
HASHTAG_RX = re.compile(r'#[^\s#]+')


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, where, msg):
        self.errors.append(f'{where}: {msg}')

    def warn(self, where, msg):
        self.warnings.append(f'{where}: {msg}')


def walk_strings(obj, path='партия'):
    """Отдаёт все строки файла с путём до них, чтобы найти длинные тире везде."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f'{path}[{i}]')


def text_of(obj, key):
    value = obj.get(key, '') if isinstance(obj, dict) else ''
    return value.strip() if isinstance(value, str) else ''


def check_slides(post, where, rep, seen_images, publish):
    slides = post.get('slides')
    if not isinstance(slides, list) or not slides:
        rep.err(where, 'нет слайдов (поле slides)')
        return []
    if len(slides) < SLIDES_MIN:
        rep.err(where, f'слайдов {len(slides)}, для карусели нужно хотя бы {SLIDES_MIN}')
    if len(slides) > SLIDES_API_WARN:
        rep.warn(where, f'слайдов {len(slides)}: проверь лимит карусели в API площадки')
    layouts = []
    for i, slide in enumerate(slides, 1):
        sw = f'{where}, слайд {i}'
        if not isinstance(slide, dict):
            rep.err(sw, 'слайд должен быть объектом с полями image, alt, layout')
            layouts.append('')
            continue
        image, alt, layout = text_of(slide, 'image'), text_of(slide, 'alt'), text_of(slide, 'layout')
        if not image:
            rep.err(sw, 'нет картинки (поле image)')
        elif image in seen_images:
            rep.err(sw, f'кадр уже использован в {seen_images[image]}: {image}')
        else:
            seen_images[image] = sw
        if image and publish and not image.startswith('https://'):
            rep.err(sw, 'для публикации нужен публичный https-адрес: площадка скачивает кадр по ссылке')
        if not alt:
            rep.err(sw, 'нет альт-текста (поле alt), напиши его по самому кадру')
        if not layout:
            rep.err(sw, 'не указана раскладка (поле layout)')
        layouts.append(layout)
    for i in range(1, len(layouts)):
        if layouts[i] and layouts[i] == layouts[i - 1]:
            rep.err(where, f'слайды {i} и {i + 1} собраны одной раскладкой «{layouts[i]}»')
    return layouts


def check_texts(post, where, rep):
    ig = text_of(post.get('instagram') or {}, 'caption')
    th_obj = post.get('threads') or {}
    th, reply = text_of(th_obj, 'text'), text_of(th_obj, 'reply')
    channels = post.get('channels') or ['instagram', 'threads']
    if 'instagram' in channels:
        if not ig:
            rep.err(where, 'нет подписи Instagram (instagram.caption)')
        if len(ig) > IG_CAPTION_MAX:
            rep.err(where, f'подпись Instagram {len(ig)} знаков, лимит {IG_CAPTION_MAX}')
        tags = len(HASHTAG_RX.findall(ig))
        if tags > IG_HASHTAGS_MAX:
            rep.err(where, f'хэштегов {tags}, лимит Instagram {IG_HASHTAGS_MAX}')
    if 'threads' in channels:
        if not th:
            rep.err(where, 'нет отдельного поста Threads (threads.text)')
        if len(th) > THREADS_MAX:
            rep.err(where, f'пост Threads {len(th)} знаков, лимит {THREADS_MAX}: пост упадёт уже после Instagram')
        if len(reply) > THREADS_MAX:
            rep.err(where, f'ответ в ветке Threads {len(reply)} знаков, лимит {THREADS_MAX}')
        if th and ig and (th == ig or ig.startswith(th)):
            rep.err(where, 'пост Threads повторяет подпись Instagram: нужен свой, короче и разговорнее')


def check_posts(posts, rep, publish):
    seen_images, prev_seq, ids = {}, None, set()
    for n, post in enumerate(posts, 1):
        if not isinstance(post, dict):
            rep.err(f'пост {n}', 'пост должен быть объектом')
            continue
        pid = text_of(post, 'id') or f'№{n}'
        where = f'пост {pid}'
        if pid in ids:
            rep.err(where, 'id повторяется в партии')
        ids.add(pid)
        if not text_of(post, 'date'):
            rep.err(where, 'нет даты публикации (поле date)')
        if not text_of(post, 'question'):
            rep.err(where, 'не указан вопрос, на который отвечает пост (поле question)')
        seq = tuple(check_slides(post, where, rep, seen_images, publish))
        if seq and seq == prev_seq:
            rep.err(where, 'карусель собрана той же последовательностью раскладок, что и предыдущая')
        prev_seq = seq or prev_seq
        check_texts(post, where, rep)


def check_pins(pins, rep, publish):
    if not isinstance(pins, list):
        rep.err('pinterest', 'поле pinterest должно быть списком пинов')
        return
    titles = {}
    for i, pin in enumerate(pins, 1):
        where = f'пин {i}'
        if not isinstance(pin, dict):
            rep.err(where, 'пин должен быть объектом с полями image, title, link')
            continue
        image, title, link = text_of(pin, 'image'), text_of(pin, 'title'), text_of(pin, 'link')
        if not image:
            rep.err(where, 'нет картинки (поле image)')
        elif publish and not image.startswith('https://'):
            rep.err(where, 'для загрузки нужен публичный https-адрес картинки')
        if not title:
            rep.err(where, 'нет названия (поле title)')
        elif title in titles:
            rep.err(where, f'название совпадает с пином {titles[title]}: форма отклоняет одинаковые')
        else:
            titles[title] = i
        if not link:
            rep.warn(where, 'нет ссылки (поле link)')
    if len(pins) > PINS_PER_DAY_WARN:
        rep.warn('pinterest', f'пинов {len(pins)}: по наблюдению после ~{PINS_PER_DAY_WARN} в сутки создание '
                              'молча перестаёт работать, раздели по дням и начни с пробника на 10')


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    publish = '--publish' in argv
    if len(args) != 1:
        print('Укажи файл партии: python3 check_post.py batch.json [--publish]')
        return 1
    try:
        with open(args[0], encoding='utf-8') as f:
            batch = json.load(f)
    except FileNotFoundError:
        print(f'Файл не найден: {args[0]}')
        return 1
    except json.JSONDecodeError as e:
        print(f'Файл не читается как JSON: строка {e.lineno}, позиция {e.colno}: {e.msg}')
        return 1
    if not isinstance(batch, dict):
        print('Файл партии должен быть объектом с полем posts')
        return 1

    rep = Report()
    posts = batch.get('posts')
    if not isinstance(posts, list) or not posts:
        rep.err('партия', 'нет постов (поле posts)')
    else:
        check_posts(posts, rep, publish)
    if 'pinterest' in batch:
        check_pins(batch['pinterest'], rep, publish)
    for path, s in walk_strings(batch):
        if any(d in s for d in DASHES):
            rep.err(path, 'длинное или среднее тире, замени на дефис, двоеточие или точку')
    if publish and batch.get('approved') is not True:
        rep.err('партия', 'нет отметки владельца "approved": true, в очередь ставить рано')

    for w in rep.warnings:
        print('Предупреждение:', w)
    if rep.errors:
        print(f'Найдено нарушений: {len(rep.errors)}')
        print('\n'.join(rep.errors))
        return 1
    count = len(posts) if isinstance(posts, list) else 0
    print(f'Чисто: постов {count}, нарушений нет.')
    return 0


if __name__ == '__main__':
    if any(a in ('-h', '--help') for a in sys.argv[1:]):
        print(__doc__ or 'Справка в начале файла.')
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
