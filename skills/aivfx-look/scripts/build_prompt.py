#!/usr/bin/env python3
"""Сборка промпта: сцена плюс лук под правила конкретной модели.

Запуск:
  python3 build_prompt.py --preset aivfx-dark-roast --model seedream --mode photo "сцена"
  python3 build_prompt.py --preset neutral-product --model nano-banana --mode photo --no-grade --file scene.txt
  python3 build_prompt.py --preset aivfx-dark-roast --model midjourney --mode photo --aspect 16:9 "сцена"
  python3 build_prompt.py --list

Готовый промпт идёт в stdout, предупреждения в stderr. Соотношение сторон
никогда не попадает в текст промпта: для Midjourney оно уходит в --ar, для
остальных печатается отдельной строкой «Параметр модели: aspect_ratio=...».
"""
import argparse
import pathlib
import re
import sys

from look_common import (MODES, die, find_aspects, find_banned, list_presets,
                         load_preset, strip_aspects, strip_banned, tidy)

# Куда вставлять лук. tail: в конец той же строки; paragraph: отдельным
# абзацем в конце; style: блоком "Style:"; mj: перед параметрами --.
MODELS = {
    'seedream': ('tail', 'photo'),
    'nano-banana': ('paragraph', 'photo'),
    'gpt-image': ('style', 'photo'),
    'midjourney': ('mj', 'photo'),
    'seedance': ('paragraph', 'video'),
    'kling': ('style', 'video'),
    'veo': ('style', 'video'),
    'higgsfield': ('tail', 'any'),
    'other': ('paragraph', 'any'),
}
ALIASES = {'nanobanana': 'nano-banana', 'nano_banana': 'nano-banana', 'banana': 'nano-banana',
           'gpt-image-2': 'gpt-image', 'gptimage': 'gpt-image', 'gpt': 'gpt-image',
           'mj': 'midjourney', 'veo3': 'veo', 'any': 'other'}


def warn(msg):
    print(f'Внимание: {msg}', file=sys.stderr)


def print_list():
    for p in list_presets():
        d = load_preset(str(p))
        grade = 'с грейдом' if d['grade'].strip() else 'без грейда'
        print(f"{d['name']:<20} {d['title']} ({grade})")
        print(f"{'':<20} брать: {'; '.join(d['use_when'])}")
        print(f"{'':<20} не брать: {'; '.join(d['avoid_when'])}")
    print(f"\nМодели: {', '.join(MODELS)}")


def look_text(preset, mode, no_grade):
    parts = [preset['core'].strip()]
    if preset['grade'].strip() and not no_grade:
        parts.append(preset['grade'].strip())
    if mode in ('video', 'dialogue'):
        parts.append(preset['video_motion'].strip())
    if mode == 'dialogue':
        parts.append(preset['video_dialogue'].strip())
    return ' '.join(p for p in parts if p)


def clean_scene(scene, preset):
    """Вырезает соотношение сторон и слова-ломатели, о каждом предупреждает."""
    aspects = find_aspects(scene)
    if aspects:
        warn('убрал из текста сцены соотношение сторон: ' + ', '.join(aspects)
             + '. Передавай его параметром модели (--aspect).')
        scene = strip_aspects(scene)
    banned = find_banned(scene, preset['banned_words'])
    if banned:
        warn('убрал слова, которые ломают лук: ' + ', '.join(banned))
        scene = strip_banned(scene, preset['banned_words'])
    return tidy(scene)


def end_sentence(text):
    return text if text.endswith(('.', '!', '?')) else text + '.'


def assemble(scene, look, place, aspect):
    if place == 'mj':
        # Свои параметры (--stylize 200 и т.п.) оставляем после лука.
        m = re.search(r'\s--\w', ' ' + scene)
        body, params = (scene, '')
        if m:
            cut = m.start()
            body, params = scene[:cut].strip(), scene[cut:].strip()
        body = ' '.join(body.split())
        out = f'{end_sentence(body)} {look}'
        if aspect:
            out += f' --ar {aspect}'
        return out + (f' {params}' if params else '')
    if place == 'tail':
        return f'{end_sentence(scene)} {look}'
    if place == 'style':
        return f'{end_sentence(scene)}\nStyle: {look}'
    return f'{end_sentence(scene)}\n\n{look}'


def main():
    ap = argparse.ArgumentParser(description='Склеивает сцену и лук под модель.')
    ap.add_argument('scene', nargs='?', help='текст сцены (или --file)')
    ap.add_argument('--file', help='файл с текстом сцены')
    ap.add_argument('--preset', default='aivfx-dark-roast', help='имя пресета или путь к json')
    ap.add_argument('--model', default='other', help=', '.join(MODELS))
    ap.add_argument('--mode', default='photo', choices=MODES)
    ap.add_argument('--no-grade', action='store_true', help='без грейда пресета')
    ap.add_argument('--aspect', help='соотношение сторон, например 16:9')
    ap.add_argument('--list', action='store_true', help='показать пресеты')
    a = ap.parse_args()

    if a.list:
        print_list(); return
    model = ALIASES.get(a.model.lower(), a.model.lower())
    if model not in MODELS:
        die(f'модель «{a.model}» не знаю. Есть: {", ".join(MODELS)}. '
            'Для любой другой бери --model other.')
    if a.file:
        try:
            scene = pathlib.Path(a.file).read_text(encoding='utf-8')
        except OSError as e:
            die(f'не могу прочитать файл сцены {a.file}: {e.strerror}')
    elif a.scene:
        scene = a.scene
    else:
        die('нет текста сцены: передай его в кавычках или через --file')
    if a.aspect and not re.fullmatch(r'\d{1,2}:\d{1,2}', a.aspect.strip()):
        die(f'--aspect «{a.aspect}» не похож на соотношение сторон, нужно вроде 16:9')

    preset = load_preset(a.preset)
    place, kind = MODELS[model]
    if kind == 'photo' and a.mode != 'photo':
        warn(f'{model} делает картинки, а режим {a.mode}: видео-блок всё равно добавлен.')
    if kind == 'video' and a.mode == 'photo':
        warn(f'{model} делает видео, а режим photo: видео-блок не добавлен.')

    scene = clean_scene(scene.strip(), preset)
    if not scene:
        die('после чистки от сцены ничего не осталось')
    look = look_text(preset, a.mode, a.no_grade)
    aspect = a.aspect.strip() if a.aspect else None
    print(assemble(scene, look, place, aspect))
    if aspect and place != 'mj':
        print(f'\nПараметр модели: aspect_ratio={aspect}')
    elif not aspect:
        warn('соотношение сторон не задано: передай его параметром модели, '
             'иначе i2i часто отдаёт квадрат 1:1.')


if __name__ == '__main__':
    main()
