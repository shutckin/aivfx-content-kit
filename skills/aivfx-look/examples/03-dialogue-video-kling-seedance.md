# Видео с репликой, Seedance и Kling

Пресет `aivfx-dark-roast`, режим `dialogue`: в кадре говорят, поэтому
добавляются оба видео-блока, движение камеры и строка про живую игру и
синхрон реплик. Если в кадре молчат, бери `--mode video`: строки про реплики
не будет, и модель не станет придумывать говорящие головы.

## Было

```
Camera: medium close-up, slow push-in. A barista in a faded denim apron leans on the counter of a tiny coffee shop and tells a regular: "Same as yesterday, but I made it stronger." The regular laughs and nods. Late afternoon light through the open door, 16:9, cinematic 8k
```

## Seedance: команда

Из папки скилла:

```
python3 scripts/build_prompt.py --preset aivfx-dark-roast --model seedance --mode dialogue --aspect 9:16 "Camera: medium close-up, slow push-in. A barista in a faded denim apron leans on the counter of a tiny coffee shop and tells a regular: \"Same as yesterday, but I made it stronger.\" The regular laughs and nods. Late afternoon light through the open door, 16:9, cinematic 8k"
```

Предупреждения скрипта (stderr):

```
Внимание: убрал из текста сцены соотношение сторон: 16:9. Передавай его параметром модели (--aspect).
Внимание: убрал слова, которые ломают лук: 8k
```

## Seedance: стало

```
Camera: medium close-up, slow push-in. A barista in a faded denim apron leans on the counter of a tiny coffee shop and tells a regular: "Same as yesterday, but I made it stronger." The regular laughs and nods. Late afternoon light through the open door, cinematic.

Shot on Arricam LT with Cooke S4/i primes, 35mm Kodak Vision3 500T, T2.8, shallow depth of field, halation on highlights, fine organic grain, lifted milky blacks, low contrast, no sharpening, no HDR. Dark Roast grade: terracotta-warm skin as the hero tone, honey-oak wood and amber tungsten pools, matte charcoal blacks, cool blue-grey window light, chromatic blue shadows. Handheld with micro-drift, never locked off. Naturalistic performance, real dialogue sync, no music.

Параметр модели: aspect_ratio=9:16
```

В тексте было `16:9`, а ролик нужен вертикальный: такая путаница и есть
причина, почему соотношение сторон живёт только в параметре.

## Kling: та же сцена

Команда та же, только `--model kling`. Для Kling и Veo лук идёт блоком
`Style:`:

```
Camera: medium close-up, slow push-in. A barista in a faded denim apron leans on the counter of a tiny coffee shop and tells a regular: "Same as yesterday, but I made it stronger." The regular laughs and nods. Late afternoon light through the open door, cinematic.
Style: Shot on Arricam LT with Cooke S4/i primes, 35mm Kodak Vision3 500T, T2.8, shallow depth of field, halation on highlights, fine organic grain, lifted milky blacks, low contrast, no sharpening, no HDR. Dark Roast grade: terracotta-warm skin as the hero tone, honey-oak wood and amber tungsten pools, matte charcoal blacks, cool blue-grey window light, chromatic blue shadows. Handheld with micro-drift, never locked off. Naturalistic performance, real dialogue sync, no music.

Параметр модели: aspect_ratio=9:16
```

Проверка:

```
python3 scripts/build_prompt.py ... 2>/dev/null | python3 scripts/check_prompt.py --preset aivfx-dark-roast --mode dialogue
Чисто: лук aivfx-dark-roast на месте, режим dialogue.
```
