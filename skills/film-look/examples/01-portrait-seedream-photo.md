# Портрет в интерьере, Seedream, фото

Пресет `dark-roast` (флагман, с грейдом): в кадре человек и интерьер,
жёстких требований к цвету нет.

## Было

Типичный «нейронный» промпт: соотношение сторон в тексте и слова, которые
просят цифровую резкость.

```
Portrait of a ceramicist in her late fifties sitting at a worn wooden workbench in a small studio apartment, clay dust on her forearms, she looks straight into the lens with a tired half-smile, tall window on the left, shelves of unfired bowls behind her, 4:3, 8k, hyperrealistic, sharp focus, masterpiece
```

Что с ним не так: `4:3` спорит с параметром модели, и кадр обрезается мимо.
`8k`, `hyperrealistic`, `sharp focus`, `masterpiece` дают перешарп и
пластиковую кожу.

## Команда

Из папки скилла:

```
python3 scripts/build_prompt.py --preset dark-roast --model seedream --mode photo --aspect 3:4 "Portrait of a ceramicist in her late fifties sitting at a worn wooden workbench in a small studio apartment, clay dust on her forearms, she looks straight into the lens with a tired half-smile, tall window on the left, shelves of unfired bowls behind her, 4:3, 8k, hyperrealistic, sharp focus, masterpiece"
```

Предупреждения скрипта (stderr):

```
Внимание: убрал из текста сцены соотношение сторон: 4:3. Передавай его параметром модели (--aspect).
Внимание: убрал слова, которые ломают лук: 8k, hyperrealistic, sharp focus, masterpiece
```

## Стало

```
Portrait of a ceramicist in her late fifties sitting at a worn wooden workbench in a small studio apartment, clay dust on her forearms, she looks straight into the lens with a tired half-smile, tall window on the left, shelves of unfired bowls behind her. Shot on Arricam LT with Cooke S4/i primes, 35mm Kodak Vision3 500T, T2.8, shallow depth of field, halation on highlights, fine organic grain, lifted milky blacks, low contrast, no sharpening, no HDR. Dark Roast grade: terracotta-warm skin as the hero tone, honey-oak wood and amber tungsten pools, matte charcoal blacks, cool blue-grey window light, chromatic blue shadows.

Параметр модели: aspect_ratio=3:4
```

Для Seedream лук идёт в конец основного описания тем же абзацем. Строку
«Параметр модели» в промпт не вставляй: это значение для поля или флага
`--aspect_ratio`.
