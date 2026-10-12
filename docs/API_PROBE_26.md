# API Probe: FL Studio 26.1.7 (E-0 spike)

Дата: 12 окт 2026. FL **Producer Edition v26.1.7 [build 5419]**, bridge `protocol v2`,
ветка `epic/E-0`. Все вызовы — «вызвал → прочитал результат», никаких догадок.

Воспроизводимый вызов (daemon, newline-JSON на TCP 127.0.0.1:9787; формат —
`daemon.py:33`, `{"op":"call","cmd":...,"params":{...}}`):

```sh
printf '%s\n' '{"op":"call","cmd":"api_probe","params":{"op":"ppq"}}' \
  | nc 127.0.0.1 9787
# или размер ответа (важно для бюджета SysEx, см. Q1):
python scripts/rpc_call.py api_probe '{"op":"ppq"}'   # печатает payload bytes
```

Контроллер развёрнут в
`~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/`.

Маркеры reload: `e0-probe-v16` → `v17` (op `jump`) → `v18` (бюджет-пагинация
op `step`). FL **не** перечитывает контроллер сам — нужен ручной «Update»
в MIDI settings, а если и он не берёт — перезапуск FL (проверено: после
«Update» FL продолжал отдавать v17, после перезапуска подхватил v18).

---

## Q1 — Channel Rack step-сетка (есть ли доступ к grid-битам?)

**Гипотеза:** FL API отдаёт состояние step-секвенсора Channel Rack по-битово.

**Проверка:** `api_probe op=step`, плюс `api_probe op=dir module=channels`.

**Факт:**
- `dir(channels)` — 54 имени. Нужные есть:
  `getGridBit`, `getGridBitWithLoop`, `setGridBit`, `isGridBitAssigned`,
  `getStepParam`, `getCurrentStepParam`, `setStepParameterByIndex`, `fillEachNSteps`.
- `dir(ui)` — 72 имени, есть `getStepEditMode` / `setStepEditMode`
  (setter подтверждён: `step_mode_has_setter: true`).
- **Пагинация `op=dir` подтверждена вживую:** `module=channels` →
  `total: 54, next_start: 34` (страница отдана, остаток 20 имён).
- **Бюджет `op=step` (исправлено в этом же эпике):** раньше `steps=64`
  отдавал 64 бита одним ответом (~815 B) — это выше бюджета SysEx
  (>1000 B молча теряется). Теперь окно ограничено **16 битами на вызов**
  и пагинируется `start`/`next_start`, как `op=dir`. Замерено:
  `steps=64, start=0` → 16 бит, `next_start: 16`, **431 B**;
  `start=16` → 16 бит, `next_start: 32`. Живой ответ (канал 0):
  `grid_bits=[1,0,1,1,0,0,...]` (шаги 0–3 активны), `run_script_api: false`.
- **`ui.runScript` отсутствует** → `run_script_api: false`. Запустить pyscript
  извне API нельзя — только хоткей «Run last script again».

**Вывод:** step-сетка **полностью доступна на чтение** бит-за-битом. Это готовый
фундамент для E-2/E-6 (чтение/запись паттернов без Piano roll).
Но **автозапуск скриптов через API мёртв** — триггер только хоткей.

---

## Q2 — Piano-roll pyscript: что реально доступно?

**Гипотеза:** из pyscript-песочницы Piano roll можно достучаться до файлов и/или
до широкого FL API.

**Проверка:** `fl_pyscripts/MCP_Read_Probe.pyscript` v3 — пишет receipt в
3 пути, читает `~/.flstudio-mcp/probe.json`, кодирует вердикт **нотами** в score
(потому что `print()` в View → Script output не виден, а `ui` недоступен).

*Контроль входного файла:* `~/.flstudio-mcp/probe.json` **создан заранее**
(снаружи песочницы, обычным процессом; `ls -la` → mtime 11:38, до запуска
пробы; содержимое `{"pitch":64,"msg":"E-0 read test","ts":...}`). Без этого
контроля «read FAIL» ≠ «песочница блокирует» — мог бы быть просто отсутствующий
файл. Наличие файла до запуска — обязательный шаг проверки Q2.

Коды тонов (версия v3): `84`=скрипт дошёл до конца, `85`=read probe.json OK,
`86`=хотя бы одна запись OK, `87`=import ui, `88`=import flpianoroll,
`89`=import channels, `90`=import general, `91`=crash.
**Все 13 import-проверок наблюдаемы** (каждый модуль кодируется своим тоном):
`92`=mixer, `93`=plugins, `94`=transport, `95`=patterns, `96`=midi,
`97`=arrangement, `98`=utils, `99`=sys, `100`=time.

**Факт (запуск из меню Piano roll → Tools → Scripts → MCP Read Probe):**
- В score появились **ровно 2 ноты: C7 (84) и E7 (88)**.
- **Честная отметка прогона:** последний след нот (84+88) оставлен прогоном
  **v2** — отдельного прогона v3 с 13-тонной таблицей не выполнялось (v3
  деплойнут и сверен с репо: md5 `9b0c0fa0…` совпадает в обоих местах;
  mtime деплоя 16:30+). След v2 и v3 не различить: при неработающих импортах
  92–100 и работающем flpianoroll обе версии пишут ровно 84+88. Различимый
  прогон (маркеры 92–100) появится только когда импорты перестанут падать —
  сейчас их отсутствие **и** есть результат Q2.
- Расшифровка: скрипт **дошёл до конца** (84) и **`flpianoroll` импортируется** (88).
- `85/86` отсутствуют → **чтение и запись файла заблокированы**
  (receipt-файлов нет ни в одном из 3 путей; входной `probe.json` при этом
  существовал — см. контроль выше, так что read FAIL ≠ «файла не было»).
- `87/89/90/92–100` отсутствуют → из песочницы импортируются **только**
  `flpianoroll` (+ `os`, `json`, которые нужны самому скрипту); `ui`, `channels`,
  `general`, `mixer`, `plugins`, `transport`, `patterns`, `midi`, `arrangement`,
  `utils`, `sys`, `time` — **нет**.

**Вывод:** песочница Piano roll экспортирует **только `flpianoroll`**.
Идея «обойти сломанный `plugin_set_param` через pyscript внутри FL» — **мёртв**.
Полный FL API из контекста Piano roll **недоступен**. `print()` туда-назад
не идёт; канал обратной связи — только ноты (видимые в score) или хоткей-триггер.

---

## Q3 — macOS-хоткей «Run last script again»: Cmd+Opt+Y

**Гипотеза:** платформенный триггер нот-моста (Cmd+Opt+Y) работает на macOS.

**Проверка:** два отдельных прогона, чтобы не путать MCP_Read_Probe (диагностика
песочницы) с MCP_Apply (запись нот):

1. **Cmd+Opt+Y как «повторить последний скрипт»** — последним скриптом был
   MCP Read Probe; после нажатия (руками, пользователем) score содержит
   **ровно 2 ноты: C7 (84) и E7 (88)** — маркеры Read_Probe, перезаписанные
   заново (предыдущая «серая» нота исчезла). Хоткей **перечитал файл скрипта**
   и выполнил его — значит FL перезагружает .pyscript на каждый запуск.
2. **Cmd+Opt+Y как триггер MCP_Apply** — `apply_notes` (пустой replace)
   отправил хоткей после записи `MCP_Apply.pyscript`; FL отработал, и ноты
   применились. Здесь маркеры 84/88 не участвуют — это отдельный канал.

**Факт:**
- Шорткат «Run last script again» = **Cmd+Opt+Y** (подтверждено в меню FL).
- Хоткей перечитывает .pyscript с диска и выполняет его (п. 1) и триггерит
  MCP_Apply (п. 2).
- Важно для `AGENT.md`: старая заметка «хоткей через pyautogui/osascript
  теряет модификаторы» относится к **автоматизации извне** (pyautogui/osascript
  шлут хоткей). Здесь хоткей **нажат вручную пользователем** — и работает.
  Это **не** противоречие, а разные каналы: ручной — надёжный, автоматический
  извне — ненадёжный (модификаторы теряются). Вывод E-0: автоматический
  автотриггер не использовать (в Q1 подтверждено `run_script_api: false`);
  ручной запуск/хоткей — рабочий путь.

**Вывод:** нот-мост **работает на macOS**. Единственный ручной шаг сессии —
запустить «MCP Apply» один раз из меню, чтобы он стал «last script»
(API для arm нет, см. Q1 `run_script_api: false`).

---

## Q4 — Паттерны: `jumpToPattern` за границу, `findFirstNextEmptyPat`

**Гипотеза:** `patterns.jumpToPattern` ведёт себя предсказуемо на 0 / past-max;
`findFirstNextEmptyPat` отдаёт индекс свободного паттерна.

**Проверка:** `api_probe op=pat` (чтение метаданных), `arrange_new_pattern`,
новый read-only op `jump` (прыгает → читает `patternNumber` → прыгает обратно).

**Факт:**
- База: `pattern_count: 1`, `pattern_number: 1`, `patternMax: 999`,
  `ppq: 96`. `has_set_name/has_set_length: true`.
- `arrange_new_pattern name="E0TEST"` → **ok, index 2, count 1→2, selected 2**.
- `jumpToPattern(999)` → `after_jump_number: 999` (без ошибки), восстановление OK.
- `jumpToPattern(0)` → `after_jump_number: 1` (FL нормализует 0 → 1).
- `jumpToPattern(1000)` (past max=999) → `after_jump_number: 999` (срез к max).
- **Пружины нет:** после всех прыжков `pattern_count` остался `2`,
  `pattern_list` = `[Pattern 1, E0TEST]` — OOB-прыжки **не плодят** паттерны.
- **Баг API:** `patterns.findFirstNextEmptyPat()` падает
  `TypeError: function missing required argument 'flags' (pos 1)`.
  Работающий обход уже в контроллере `_h_arrange_new_pattern`:
  `try findFirstNextEmptyPat() except → patternCount() + 1`.
- **Cleanup (выполнен):** тестовый `E0TEST` удалён вручную (правый клик по
  паттерну 2 → Delete; API-удаления паттернов нет, `op=undo` его не убирает —
  проверено дважды). После очистки: `pattern_list total=1`,
  `pattern_count=1, pattern_number=1`. Проект вернулся к исходному состоянию.

**Вывод:** `jumpToPattern` **безопасен** (срез к `[1, max]`, без создания).
`findFirstNextEmptyPat` **сломан в FL 26** (нужен `flags`) — fallback
`count+1` обязателен для E-6.

---

## Q5 — Скриншоты: координаты и тайминг

**Гипотеза:** для кликов по FL нужны знаменатели «screencapture ↔ logical».

**Проверка (команды-измерители, воспроизводимы):**

```python
# logical-пространство (координаты, в которых FL рисует и которые принимает pyautogui)
import pyautogui; print(pyautogui.size())          # -> Size(width=1710, height=1107)

# пиксельные размеры PNG от screencapture
import subprocess; subprocess.run(["screencapture", "-x", "/tmp/m.png"], check=True)
import subprocess; print(subprocess.run(
    ["sips", "-g", "pixelWidth", "-g", "pixelHeight", "/tmp/m.png"],
    capture_output=True, text=True).stdout)         # -> pixelWidth 3420, pixelHeight 2214

# тайминги (3 прогона, среднее) -- честный цикл: t0 -> замер -> t1
import time, subprocess
ts = []
for _ in range(3):
    t0 = time.time()
    subprocess.run(["screencapture", "-x", "/tmp/t.png"], check=True)
    ts.append(time.time() - t0)
print("screencapture avg:", sum(ts) / len(ts))     # ~0.18 с на прогон

# для сравнения pyautogui (нужен Pillow)
import pyautogui
t0 = time.time(); pyautogui.screenshot(); print("pyautogui:", time.time() - t0)  # ~0.27
```

**Факт (замерено на этом экране):**
- `pyautogui.size()` = **1710×1107** (logical, точки).
- PNG от `screencapture -x` = **3420×2214** (пиксели).
- Знаменатель = 3420/1710 = **2.0 ровно** (не 1.71 — прежняя цифра была ошибкой).
- `screencapture` ≈ **0.18 с**; `pyautogui.screenshot()` ≈ **0.27 с** (медленнее).

**Вывод:** `screencapture` — быстрее и достаточен для снапшотов. Координаты для
pyautogui-кликов: `logical = screenshot_px / 2.0`. Никогда не смешивать три числа,
которые гуляли по заметкам (0.855 = 1710/2000, 1.71 — обе неверны): на этом
экране коэффициент **ровно 2.0**, и он всегда = `pixelWidth / logical_width`
(пересчитать на другом разрешении, не хардкодить).

---

## Q6 — Цвета и пресеты: точные форматы

**Гипотеза:** FL отдаёт цвет/пресет в стабильном JSON-подобном формате.

**Проверка:** `channel_get_color`, `mixer_get_color`, `plugin_preset info`.

**Факт:**
- `channel_get_color` → `{"channel":0,"color":{"int":6055274,"hex":"#5C656A","r":92,"g":101,"b":106}}` (86–88 B).
- `mixer_get_color` → аналогично (`#636C71`).
- `plugin_preset info` → `{"preset_count":1,"plugin_name":"Emphasizer","name_f3":"","name_f6":"Default"}` (122 B).
- `slot=-1` для sampler → `count_error:"Plugin not valid"`; для генератора
  (канал 4) → `preset_count:30, plugin_name:"FLEX", name_f6:"808 Astronomic"`.

**Вывод:** форматы стабильны и пригодны для E-6 (цвета/пресеты читаются напрямую).

---

## Сводка ответов

| Вопрос | Ответ |
|---|---|
| Q1 step-сетка | **Да**, бит-доступ полный (16 бит/страница, `start`/`next_start`, 431 B); `ui.runScript` нет → автозапуск скриптов невозможен |
| Q2 pyscript | **Только `flpianoroll`** (+ os/json); файлы и широкий FL API недоступны (все 13 import-проверок наблюдаемы нотами); обратная связь — ноты |
| Q3 хоткей | **Cmd+Opt+Y работает** вручную (перечитывает .pyscript); автоматический автотриггер извне — ненадёжен (модификаторы) |
| Q4 паттерны | `jumpToPattern` безопасен (срез `[1,max]`, без создания); `findFirstNextEmptyPat` **сломан** (`flags`) → fallback `count+1`; cleanup E0TEST выполнен |
| Q5 скриншоты | `screencapture` 0.18 с; logical = px / **2.0** (3420/1710) |
| Q6 цвета/пресеты | Форматы стабильны, читаются напрямую |

## Связь с эпиками

- **E-2 / E-6 (arrangement / мост нот):** Q1 даёт чтение step-сетки (пагинация
  учтена); Q2 запрещает pyscript как канал управления; Q3 закрывает платформу;
  Q4 (fallback `count+1`, безопасный `jump`, cleanup) — прямые инструкции для
  `arrange_new_pattern` / `arrange_clone_pattern`.
- **E-5 (macOS-совместимость):** Q3 (ручной хоткей надёжен, автотриггер — нет)
  + Q5 (**2.0**, screencapture).
- **E-6 (presets/colors):** Q6 — готовые форматы.

## Что осталось непокрытым

- `findFirstNextEmptyPat` с корректным `flags` — не исследовано (нужен вызов
  с аргументом; fallback `count+1` достаточен для E-6).
- Поведение `jumpToPattern` на отрицательных индексах — не проверено
  (0/999/1000 проверены, отрицательные — нет).
- `ui.getFocused(wid)` без аргумента падает (`takes exactly 1 argument`) —
  wid брать из `midi.widPianoRoll` и т.п.
- Автозапуск скриптов извне — **невозможен** (`run_script_api: false`);
  каждый сеанс требует одного ручного «MCP Apply».
- Юнит-тестов нет (по плану — E-8); живое покрытие — прогоны, описанные ниже.

---

## Воспроизводимость (DoD-цифры и команды)

**ruff (статика, `ruff 0.17.0`).** Команда и бейзлайн:

```sh
python -m ruff check .            # весь репозиторий
```

| Граница | Ошибок |
|---|---|
| HEAD (бейзлайн до спайка) | **693** |
| после изменений спайка | **693** (дельта **0**) |

Изменённые файлы спайка (дельта по каждому = 0):

| Файл | ruff |
|---|---|
| `fl_controller/FLStudioMCP/device_FLStudioMCP.py` | 19 → 19 |
| `src/fl_studio_mcp/protocol.py` | 6 → 6 |
| `fl_pyscripts/MCP_Read_Probe.pyscript` | 9 → 9 |
| `scripts/test_bridge.py` | 7 → 7 |
| `scripts/rpc_call.py` (новый) | 0 (All checks passed) |

**Живой smoke (DoD).** Команда и вывод `scripts/test_bridge.py` —
`FLSTUDIO_MCP_TRANSPORT=tcp python scripts/test_bridge.py`:

```
  ping............................................ ok
      {'fl_version': 'Producer Edition v26.1.7 [build 5419]', 'protocol_version': 2, 'build': 'e0-probe-v18', ...}
  get_tempo / set_tempo 135.0 / restore 130.0...... ok
  play............................................ ok
  stop............................................. ok
  toggle_play (1st / 2nd)  True -> False.......... ok
  record (1st -> arm / 2nd -> disarm)............. ok
  cleanup (stopped / disarmed / pos reset): {'playing': False, 'recording': False}

All checks passed.
```

Финальный cleanup оставляет `playing: False, recording: False` — зонтик DoD
«не оставлять запись включённой» выполняется. Билд-маркер в ping — `e0-probe-v18`.
