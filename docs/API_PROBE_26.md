# API Probe: FL Studio 26.1.7 (E-0 spike)

Дата: 12 окт 2026. FL **Producer Edition v26.1.7 [build 5419]**, bridge `protocol v2`,
ветка `epic/E-0`. Все вызовы — «вызвал → прочитал результат», никаких догадок.

Транспорт: `FLSTUDIO_MCP_TRANSPORT=tcp`. Тонкий RPC-хелпер из спайка:
`rpc.py api_probe '{"op":"..."}'`. Контроллер развёрнут в
`~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/`.

Маркеры reload: `e0-probe-v16` → `e0-probe-v17` (добавлен op `jump`).
FL **не** перечитывает контроллер сам — нужен ручной «Update» в MIDI settings.

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
- Живое чтение канала 0 (`grid_bits`): `[1,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0]`
  (до очистки диагностических нот). `grid_assigned` — все `true`.
- После очистки нот: `grid_bits` канала 0 — все `[0,...]`.
- **`ui.runScript` отсутствует** → `run_script_api: false`. Запустить pyscript
  извне API нельзя — только хоткей «Run last script again».

**Вывод:** step-сетка **полностью доступна на чтение** бит-за-битом. Это готовый
фундамент для E-2/E-6 (чтение/запись паттернов без Piano roll).
Но **автозапуск скриптов через API мёртв** — триггер только хоткей.

---

## Q2 — Piano-roll pyscript: что реально доступно?

**Гипотеза:** из pyscript-песочницы Piano roll можно достучаться до файлов и/или
до широкого FL API.

**Проверка:** `fl_pyscripts/MCP_Read_Probe.pyscript` v2 — пишет receipt в
3 пути, читает `~/.flstudio-mcp/probe.json`, кодирует вердикт **нотами** в score
(потому что `print()` в View → Script output не виден, а `ui` недоступен).

Коды тонов (версия v2): `84`=скрипт дошёл до конца, `85`=read probe.json OK,
`86`=хотя бы одна запись OK, `87`=import ui, `88`=import flpianoroll,
`89`=import channels, `90`=import general, `91`=crash.

**Факт (запуск из меню Piano roll → Tools → Scripts → MCP Read Probe):**
- В score появились **ровно 2 ноты: C7 (84) и E7 (88)**.
- Расшифровка: скрипт **дошёл до конца** (84) и **`flpianoroll` импортируется** (88).
- `85/86/87/89/90` отсутствуют →
  - **чтение файла заблокировано** (receipt-файлов нет ни в одном из 3 путей),
  - **запись файла заблокирована**,
  - `ui`, `channels`, `general` **не импортируются** из песочницы Piano roll.

**Вывод:** песочница Piano roll экспортирует **только `flpianoroll`**.
Идея «обойти сломанный `plugin_set_param` через pyscript внутри FL» — **мёртв**.
Полный FL API из контекста Piano roll **недоступен**. `print()` туда-назад
не идёт; канал обратной связи — только ноты (видимые в score) или хоткей-триггер.

---

## Q3 — macOS-хоткей «Run last script again»: Cmd+Opt+Y

**Гипотеза:** платформенный триггер нот-моста (Cmd+Opt+Y) работает на macOS.

**Проверка:** сценарий MCP_Apply → клик «Run last script again» в меню →
затем нажатие **Cmd+Opt+Y**.

**Факт:**
- Шорткат «Run last script again» = **Cmd+Opt+Y** (подтверждено в меню FL).
- После Cmd+Opt+Y score содержит **ровно 2 ноты** (C7, E7) — скрипт
  перезапустился, `clearNotes` отработал (предыдущая «серая» нота исчезла).

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

**Вывод:** `jumpToPattern` **безопасен** (срез к `[1, max]`, без создания).
`findFirstNextEmptyPat` **сломан в FL 26** (нужен `flags`) — fallback
`count+1` обязателен для E-6.

---

## Q5 — Скриншоты: координаты и тайминг

**Гипотеза:** для кликов по FL нужны знаменатели «screencapture ↔ logical».

**Проверка:** `screencapture` + замер таймингов.

**Факт:**
- `screencapture` ~**0.16 с**; `pyautogui.screenshot()` ~**0.27 с**
  (медленнее — **screencapture предпочтительнее** для снапшотов).
- Разрешение экрана **3420×2214**; logical-пространство **1710×1107**
  → знаменатель ≈ **1.71** (не 2.0, как в части старых заметок).
- Для кликов: `logical = screenshot_px / 1.71`.

**Вывод:** `screencapture` — быстрее и достаточен. Координаты для pyautogui-кликов
делить на **1.71**. (Замечание к `AGENT.md`: коэффициент 1710/2000=0.855 из
старых заметок **не подтверждается** — актуален 1.71.)

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
| Q1 step-сетка | **Да**, бит-доступ полный; но `ui.runScript` нет → автозапуск скриптов невозможен |
| Q2 pyscript | **Только `flpianoroll`**; файлы и широкий FL API недоступны; обратная связь — ноты |
| Q3 хоткей | **Cmd+Opt+Y работает** на macOS; ручной arm MCP Apply — один раз за сессию |
| Q4 паттерны | `jumpToPattern` безопасен (срез `[1,max]`, без создания); `findFirstNextEmptyPat` **сломан** (`flags`) → fallback `count+1` |
| Q5 скриншоты | `screencapture` 0.16 с; logical = px / **1.71** |
| Q6 цвета/пресеты | Форматы стабильны, читаются напрямую |

## Связь с эпиками

- **E-2 / E-6 (arrangement / мост нот):** Q1 даёт чтение step-сетки;
  Q2 запрещает pyscript как канал управления; Q3 закрывает платформу;
  Q4 (fallback `count+1`, безопасный `jump`) — прямые инструкции для
  `arrange_new_pattern` / `arrange_clone_pattern`.
- **E-5 (macOS-совместимость):** Q3 (хоткей) + Q5 (1.71, screencapture).
- **E-6 (presets/colors):** Q6 — готовые форматы.

## Что осталось непокрытым

- `findFirstNextEmptyPat` с корректным `flags` — не исследовано (нужен вызов
  с аргументом; fallback `count+1` достаточен для E-6).
- Поведение `jumpToPattern` на отрицательных индексах — не проверено.
- `ui.getFocused(wid)` без аргумента падает (`takes exactly 1 argument`) —
  wid брать из `midi.widPianoRoll` и т.п.
- Автозапуск скриптов извне — **невозможен** (`run_script_api: false`);
  каждый сеанс требует одного ручного «MCP Apply».
