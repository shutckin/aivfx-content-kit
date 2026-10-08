# Предметка с фирменным цветом, Nano Banana, без грейда

Пресет `neutral-product`: у бутылки утверждённый цвет бренда, тёплый грейд
его бы увёл. У этого пресета грейда нет совсем, ядро то же, что у флагмана,
плюс строка про нейтральный баланс белого. Если берёшь флагман для такой
задачи, добавь `--no-grade`.

## Было

```
A matte terracotta-red (#C8553D) glass bottle of cold-brew coffee standing on a pale limestone block, a few coffee beans scattered at the base, soft daylight from the right, clean off-white background, keep the label text and the bottle colour exactly as in the reference, ultra detailed, HDR, best quality
```

Что с ним не так: `ultra detailed`, `HDR`, `best quality` дают пластиковый
рекламный блеск и пересвеченные блики на стекле. Лука нет, поэтому модель
«улучшает» референс по своему вкусу.

## Команда

Из папки скилла:

```
python3 scripts/build_prompt.py --preset neutral-product --model nano-banana --mode photo --aspect 1:1 "A matte terracotta-red (#C8553D) glass bottle of cold-brew coffee standing on a pale limestone block, a few coffee beans scattered at the base, soft daylight from the right, clean off-white background, keep the label text and the bottle colour exactly as in the reference, ultra detailed, HDR, best quality"
```

Предупреждение скрипта (stderr):

```
Внимание: убрал слова, которые ломают лук: ultra detailed, HDR, best quality
```

## Стало

```
A matte terracotta-red (#C8553D) glass bottle of cold-brew coffee standing on a pale limestone block, a few coffee beans scattered at the base, soft daylight from the right, clean off-white background, keep the label text and the bottle colour exactly as in the reference.

Shot on Arricam LT with Cooke S4/i primes, 35mm Kodak Vision3 500T, T2.8, shallow depth of field, halation on highlights, fine organic grain, lifted milky blacks, low contrast, no sharpening, no HDR. Neutral white balance, true-to-life product colours, no colour cast.

Параметр модели: aspect_ratio=1:1
```

Для Nano Banana лук идёт отдельным абзацем в конце. `no HDR` остался на
месте: это часть лука, скрипт вырезает только «голое» HDR из сцены.

Проверка:

```
python3 scripts/build_prompt.py ... 2>/dev/null | python3 scripts/check_prompt.py --preset neutral-product --mode photo
Чисто: лук neutral-product на месте, режим photo.
```
