#!/usr/bin/env python3
"""Проверка готового промпта на лук.

Запуск:
  python3 check_prompt.py prompt.txt --preset aivfx-dark-roast --mode photo
  python3 build_prompt.py ... | python3 check_prompt.py --preset aivfx-dark-roast --mode photo

Ищет: нет ядра пресета целиком, соотношение сторон в тексте, слова-ломатели,
видео-блок в фото, строку реплик без диалога. Строка «Параметр модели: ...»,
которую печатает build_prompt.py, в проверку не идёт.
Код выхода 1 при ошибках, 0 если чисто.
"""
import argparse
import pathlib
import re
import sys

from look_common import MODES, die, find_aspects, find_banned, load_preset, norm


def read_prompt(path):
    if path:
        try:
            return pathlib.Path(path).read_text(encoding='utf-8')
        except OSError as e:
            die(f'не могу прочитать {path}: {e.strerror}')
    if sys.stdin.isatty():
        die('нет промпта: передай файл или подай текст на вход (stdin)')
    return sys.stdin.read()


def without(text, pieces):
    """Вырезает куски лука из текста, чтобы не ловить «no HDR» как ломатель."""
    for p in pieces:
        if p:
            text = text.replace(norm(p), ' ')
    return text


def check(prompt, preset, mode):
    errors, notes = [], []
    lines = [l for l in prompt.splitlines() if not l.strip().startswith('Параметр модели:')]
    text = norm('\n'.join(lines))
    # --ar в конце промпта Midjourney это параметр, а не текст.
    text_no_params = re.sub(r'\s--ar\s*\d{1,2}\s*:\s*\d{1,2}', ' ', text)

    core, grade = preset['core'], preset['grade']
    motion, dialogue = preset['video_motion'], preset['video_dialogue']
    if norm(core) not in text:
        errors.append('нет ядра пресета целиком: вставь core без правок')
    if grade.strip() and norm(grade) not in text:
        notes.append('грейда пресета нет (это нормально для бренд-цветов и точного цвета продукта)')

    aspects = find_aspects(text_no_params)
    if aspects:
        errors.append('соотношение сторон в тексте: ' + ', '.join(aspects)
                      + '. Передавай его параметром модели')

    rest = without(text_no_params, [core, grade, motion, dialogue])
    banned = find_banned(rest, preset['banned_words'])
    if banned:
        errors.append('слова, которые ломают лук: ' + ', '.join(sorted(set(b.lower() for b in banned))))

    has_motion = bool(motion.strip()) and norm(motion) in text
    has_dialogue = bool(dialogue.strip()) and norm(dialogue) in text
    if mode == 'photo' and has_motion:
        errors.append('видео-блок (движение камеры) в промпте для фото: убери его')
    if mode != 'dialogue' and has_dialogue:
        errors.append('строка про реплики без диалога: модель начнёт рисовать говорящие головы')
    if mode in ('video', 'dialogue') and not has_motion:
        notes.append('нет строки движения камеры: оставь так только для штатива, слайдера, дрона')
    if mode == 'dialogue' and not has_dialogue:
        errors.append('в кадре говорят, а строки про реплики и синхрон нет')
    return errors, notes


def main():
    ap = argparse.ArgumentParser(description='Проверяет готовый промпт на лук.')
    ap.add_argument('file', nargs='?', help='файл с промптом (иначе stdin)')
    ap.add_argument('--preset', default='aivfx-dark-roast', help='имя пресета или путь к json')
    ap.add_argument('--mode', default='photo', choices=MODES)
    a = ap.parse_args()

    preset = load_preset(a.preset)
    prompt = read_prompt(a.file)
    if not prompt.strip():
        die('промпт пустой')
    errors, notes = check(prompt, preset, a.mode)
    for n in notes:
        print(f'Заметка: {n}')
    for e in errors:
        print(f'ОШИБКА: {e}')
    if errors:
        print(f'Найдено ошибок: {len(errors)}')
        sys.exit(1)
    print(f'Чисто: лук {preset["name"]} на месте, режим {a.mode}.')


if __name__ == '__main__':
    main()
