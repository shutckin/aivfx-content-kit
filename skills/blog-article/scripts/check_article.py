#!/usr/bin/env python3
"""Проверка markdown-статьи перед публикацией.

Запуск: python3 check_article.py статья.md [--min-words 700] [--min-h2 4]
                                           [--max-words 3000] [--h1-in-body]

Проверяет то, что глазами проверять устаёшь: фронтматтер, длину
description, раздел частых вопросов и знак «?» у каждого вопроса,
число разделов, длинные тире, пустые ссылки, H1 в теле и объём.
Код выхода 1, если есть хотя бы одна ОШИБКА.
"""
import argparse
import re
import sys

# Тире задаём кодами, а не символами. Если когда-нибудь пройдёт чистка
# тире по всему репозиторию, символы внутри регулярки превратятся в
# дефисы, и проверка начнёт валить любой текст за обычный дефис.
DASHES = re.compile('[\u2014\u2013]')

FAQ_HEAD = re.compile(r'(частые вопросы|вопросы и ответы|\bfaq\b|frequently asked)', re.I)
SHORT_HEAD = re.compile(r'^(коротко|кратко|главное|in short|tl;?dr)\b', re.I)

EMPTY_LINKS = [
    (re.compile(r'\[[^\]]*\]\(\s*\)'), 'ссылка без адреса'),
    (re.compile(r'(?<!!)\[\s*\]\([^)]+\)'), 'ссылка без текста'),
    (re.compile(r'\[[^\]]+\]\(\s*#\s*\)'), 'ссылка-заглушка «#»'),
    (re.compile(r'href\s*=\s*["\']\s*#?\s*["\']', re.I), 'пустой href'),
]
MD_LINK = re.compile(r'(?<!!)\[[^\]]+\]\(([^)\s]+)[^)]*\)')


def parse_args():
    p = argparse.ArgumentParser(description='Проверка markdown-статьи')
    p.add_argument('file')
    p.add_argument('--min-words', type=int, default=700)
    p.add_argument('--max-words', type=int, default=3000)
    p.add_argument('--min-h2', type=int, default=4)
    p.add_argument('--h1-in-body', action='store_true',
                   help='шаблон не выводит title как H1, в теле разрешён один H1')
    return p.parse_args()


def split_frontmatter(text):
    """Возвращает (поля, тело, номер первой строки тела)."""
    lines = text.split('\n')
    if not lines or lines[0].strip() != '---':
        return None, text, 1
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            fields = {}
            for raw in lines[1:i]:
                m = re.match(r'^([A-Za-z_][\w-]*)\s*:\s*(.*)$', raw)
                if m:
                    fields[m.group(1).lower()] = m.group(2).strip().strip('"\'')
            return fields, '\n'.join(lines[i + 1:]), i + 2
    return None, text, 1


def headings(body, first_line):
    """Заголовки вне блоков кода: список (уровень, текст, номер строки)."""
    out, in_code = [], False
    for n, line in enumerate(body.split('\n'), start=first_line):
        if line.lstrip().startswith('```'):
            in_code = not in_code
            continue
        m = None if in_code else re.match(r'^(#{1,6})\s+(.+?)\s*#*\s*$', line)
        if m:
            out.append((len(m.group(1)), m.group(2).strip(), n))
    return out


def plain_words(body):
    body = re.sub(r'```.*?```', ' ', body, flags=re.S)
    body = re.sub(r'<[^>]+>', ' ', body)
    body = re.sub(r'\]\([^)]*\)', ']', body)
    return [w for w in re.findall(r'[\wЀ-ӿ][\wЀ-ӿ.-]*', body) if not w.isdigit()]


def check_faq(heads, errors, warns):
    start = next((i for i, h in enumerate(heads) if h[0] == 2 and FAQ_HEAD.search(h[1])), None)
    if start is None:
        errors.append('нет раздела «Частые вопросы» (H2)')
        return 0
    questions = []
    for lvl, txt, n in heads[start + 1:]:
        if lvl <= 2:
            break
        if lvl == 3:
            questions.append((txt, n))
    # Разметка вопросов строится только по заголовкам со знаком вопроса.
    # Без него блок в статье есть, а расширенного сниппета нет - молча.
    for txt, n in questions:
        if not txt.rstrip().endswith('?'):
            errors.append(f'строка {n}: вопрос без «?» - «{txt[:60]}»')
    if len(questions) < 3:
        warns.append(f'в частых вопросах всего {len(questions)} вопросов H3, лучше 3 и больше')
    return len(questions)


def check_h1(heads, title, allow_one, errors):
    h1 = [h for h in heads if h[0] == 1]
    if not allow_one and h1:
        errors.append(f'строка {h1[0][2]}: H1 в теле, шаблон уже выводит title как H1 '
                      '(если нет, запускай с --h1-in-body)')
    elif allow_one and len(h1) > 1:
        errors.append(f'H1 в теле {len(h1)} раз, нужен один (строки {", ".join(str(h[2]) for h in h1)})')
    # Повтор H1 ниже по тексту: раздел назван так же, как вся статья.
    norm = lambda s: re.sub(r'\W+', ' ', s or '').strip().lower()
    main_titles = {norm(title)} | {norm(h[1]) for h in h1}
    main_titles.discard('')
    for lvl, txt, n in heads:
        if lvl > 1 and norm(txt) in main_titles:
            errors.append(f'строка {n}: заголовок раздела повторяет H1 - «{txt[:60]}»')


def check_lines(body, first_line, errors):
    in_code = False
    for n, line in enumerate(body.split('\n'), start=first_line):
        if line.lstrip().startswith('```'):
            in_code = not in_code
        for m in DASHES.finditer(line):
            frag = line[max(0, m.start() - 30):m.end() + 30].strip()
            errors.append(f'строка {n}: длинное тире - «{frag}»')
        if in_code:
            continue
        for rx, label in EMPTY_LINKS:
            for m in rx.finditer(line):
                errors.append(f'строка {n}: {label} - «{m.group(0)[:60]}»')


def main():
    a = parse_args()
    try:
        with open(a.file, encoding='utf-8') as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f'ПРОВАЛ: не смог прочитать файл как UTF-8 - {e}')
        sys.exit(1)

    errors, warns = [], []
    fm, body, first = split_frontmatter(text)
    if fm is None:
        errors.append('нет фронтматтера между строками --- в начале файла')
        fm = {}
    title, desc = fm.get('title', ''), fm.get('description', '')
    if not title:
        errors.append('нет title во фронтматтере')
    elif len(title) > 80:
        warns.append(f'title {len(title)} символов, в выдаче обрежется (ориентир до 80)')
    if not desc:
        errors.append('нет description во фронтматтере')
    elif len(desc) > 160:
        errors.append(f'description {len(desc)} символов, максимум 160')
    if not (fm.get('updated') or fm.get('datemodified') or fm.get('date_modified')):
        warns.append('нет даты обновления (updated) во фронтматтере')
    if not fm.get('author'):
        warns.append('нет автора (author) во фронтматтере')

    heads = headings(body, first)
    h2 = [h for h in heads if h[0] == 2]
    if len(h2) < a.min_h2:
        errors.append(f'разделов H2 всего {len(h2)}, минимум {a.min_h2}')
    if not any(SHORT_HEAD.search(h[1]) for h in h2[:2]) and not re.search(
            r'^\s*\**(коротко|кратко)\b', body[:2000], re.I | re.M):
        warns.append('нет блока «Коротко» в начале статьи')
    faq_count = check_faq(heads, errors, warns)
    check_h1(heads, title, a.h1_in_body, errors)
    check_lines(body, first, errors)

    internal = {u for u in MD_LINK.findall(body) if u.startswith('/')}
    if len(internal) < 3:
        warns.append(f'внутренних ссылок {len(internal)}, лучше 3 и больше')

    words = len(plain_words(body))
    if words < a.min_words:
        errors.append(f'слов {words}, минимум {a.min_words}')
    elif words > a.max_words:
        warns.append(f'слов {words}, больше {a.max_words}: проверь, нет ли воды')

    print(f'\n{a.file}  «{title}»')
    print(f'  слов: {words}, H2: {len(h2)}, вопросов: {faq_count}, '
          f'внутренних ссылок: {len(internal)}, description: {len(desc)}')
    for w in warns:
        print('  ЗАМЕЧАНИЕ: ' + w)
    for e in errors:
        print('  ОШИБКА: ' + e)
    print('  ИТОГ: ' + ('ПРОВАЛ' if errors else 'чисто') + '\n')
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
