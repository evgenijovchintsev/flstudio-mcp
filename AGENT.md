# AGENT.md — FL Studio MCP: факты сессии (спайк E-0)

Окружение: macOS, FL Studio 2026 v26.1.7 + fl-studio-mcp.
Репозиторий: `/Users/jeno/git/flstudio-mcp` (ветка `epic/E-0`).
Транспорт: `FLSTUDIO_MCP_TRANSPORT=tcp`.
Интерпретатор: **venv живёт в другом чекауте** —
`/Users/jeno/tmp/flstudio-mcp/.venv/bin/python` (здесь `.venv` нет). Это только
интерпретатор; **файлы всегда брать из этого репо** — запускать с cwd =
`/Users/jeno/git/flstudio-mcp`, иначе выполнится код старого чекаута.
Формат RPC: TCP `127.0.0.1:9787`, newline-JSON `{"op":"call","cmd":…,"params":{…}}`,
ответ `{"ok":true,"data":{…}}`. Хелпер: `scripts/rpc_call.py <cmd> '<json-params>'`
(для `apply_notes` — см. ниже, формат там другой).

Полные воспроизводимые факты FL 26.1.7 — `docs/API_PROBE_26.md` (Q1–Q6).
Эпический план E-0…E-8 + контракты — `prompts/flstudio-mcp-upgrade/`
(`00_OVERVIEW_AND_CONTRACTS.md`, `01_IMPLEMENTATION_PROMPTS.md`).
`ROADMAP.md` — **другой** план (Phase 0–7, эпиков E-* там нет) — не путать.
Этот файл — оперативные заметки сессии; не дублирует вышеуказанные.

---

## Инварианты FL API (подтверждены, стабильны между сессиями)

### Лимиты контроллера (не баги сервера)
- Нельзя загружать новые VST/AU-плагины — только контроль существующих.
- Нельзя создавать паттерны «с нуля» через API; рабочий путь — clone
  (`arrange_clone_pattern`) или `arrange_new_pattern` с fallback `count+1`.
- Запись темпа игнорируется, если в FL открыт модальный диалог.
- Команды `showEditor` в контроллере нет.

### API-поверхность FL 26.1.7 (замеры E-0)
- `plugin_get_params` пагинирован (≈7 params/ответ, лимит ~480 B JSON, `next_start`).
- `ui.runScript` **отсутствует** → автозапуск pyscript из API невозможен.
  Триггер — только хоткей «Run last script again» (macOS: **Cmd+Opt+Y**).
- `patterns.findFirstNextEmptyPat()` **сломан** в FL 26:
  `TypeError: function missing required argument 'flags'`.
  Fallback — `patterns.patternCount() + 1` (уже в `_h_arrange_new_pattern`).
- `patterns.jumpToPattern` безопасен: 0 → 1, past-max → срез к `patternMax` (999),
  пружин/создания паттернов нет (0/999/1000 проверены).
- `patterns` **не удаляются** `api_probe op=undo` (`general.undo`) — проверено ×2.
- `general.undo` (`op=undo`) **не откатывает** запись нот из pyscript — проверено.

### Piano-roll pyscript — песочница: только flpianoroll
Песочница экспортирует **только** `flpianoroll` (+ `os`, `json`, которые нужны
самому скрипту). Заблокировано: файловое чтение и запись (receipt-файлы не
создаются ни в одном из 3 путей). Импорты `ui`, `channels`, `general`, `mixer`,
`plugins`, `transport`, `patterns`, `midi`, `arrangement`, `utils`, `sys`,
`time` — **все падают** (каждый закодирован отдельной нотой, все отсутствовали).
`print()` в View → Script output **не виден**. Единственный канал обратной
связи «скрипт отработал» — сами ноты в score. Идея «обойти сломанный
`plugin_set_param` через pyscript внутри FL» — **мёртвa**.

### Платформа macOS
- Хоткей **Cmd+Opt+Y («Run last script again»)** работает, когда его нажал
  **человек**; FL перечитывает .pyscript с диска на каждый запуск (подтверждено
  на MCP_Read_Probe: каждый запуск перезаписывает свои маркеры заново).
- Автоматизация того же хоткея через pyautogui/osascript **ненадёжна**
  (модификаторы теряются). Не использовать для автоматизации; ручной запуск
  пользователя надёжнее. Автотриггер извне — нет (см. `run_script_api: false`).

### Координаты мыши (screencapture ↔ logical)
Этот экран: logical 1710×1107, PNG от `screencapture -x` 3420×2214 →
**знаменатель ровно 2.0**. `logical = screenshot_px / 2.0`.
Скорость: `screencapture` ≈ 0.18 с (быстрее, предпочитать для снапшотов),
`pyautogui.screenshot()` ≈ 0.27 с.
**Не хардкодить коэффициент** — на другом разрешении он иной; считать как
`pixelWidth / logical_width` (`sips -g pixelWidth …` / `pyautogui.size()`).
Старые числа 1710/2000=0.855 и 1.71 — **оба неверны**, не использовать.

### Форматы цветов/пресетов (стабильны)
- цвет канала/трека → `{"int":…,"hex":"#RRGGBB","r":…,"g":…,"b":…}`
- `plugin_preset info` → `{"preset_count":…,"plugin_name":…,"name_f3":…,"name_f6":…}`
- `slot=-1` на sampler → `Plugin not valid`; на генераторе — работает.

---

## `plugin_set_param` — работает, но с нюансами (Fruity Fast Dist)
Формат: `{"op":"call","cmd":"plugin_set_param","params":{"track":N,"slot":S,"param":I,"value":V}}`
(нормализовано 0..1). Порядок в контроллере `plugins.setParamValue(val, idx, track, slot)` — корректный.
Нюансы, из-за которых казалось «сломано»:
1. **FL «pickup» mode**: окно плагина открыто и параметр недавно трогали мышью →
   hint-бар «*param* is waiting for pickup: X% > Y%», API-set **игнорируется**
   (все значения отбрасываются, даже ступенчатые). Симптом: set возвращает ok,
   но `v`/`s` всегда прежние.
   - Обход: сдвинуть ручку мышью (drag на пару десятков px) **или** закрыть окно
     плагина — после этого API-set цепляется (проверено для Pre amp / Threshold).
2. **Гонка быстрых set**: несколько set подряд без пауз перетираются (FL
   применяет по тику). Пауза ~0.3–0.5 с между set и финальным чтением.
3. **Квантизация**: FL может округлить (0.65 → 0.6484) — норма, сверять с допуском ±0.02.
4. Отдельные параметры (напр. Post gain у Fast Dist) не поддаются API-set, пока
   не сброшен pickup мышью.

**Порядок настройки плагина (рабочий рецепт):** 1) `plugin_get_params`
(пагинация `start`) прочитать текущие; 2) при подозрении на pickup — закрыть окно
плагина, не трогать ручки мышью во время записи; 3) `plugin_set_param` по одному
параметру с паузой 0.3–0.5 с; 4) свежим `plugin_get_params` проверить (±0.02);
5) если параметр не двигается — снять drag-ом мыши по ручке.

---

## Запись нот (pyscript-мост)
1. `channel_select` — выбрать канал Channel Rack.
2. RPC — **верхнеуровневый `op`**, формат:
   `{"op":"apply_notes","notes":[…],"mode":"replace","trigger":true}`
   Формат ноты: `{pitch (MIDI, 60=C5 в FL), time_bars, length_bars, velocity}`.
   Обработчик — `daemon.py:113` (`if op == "apply_notes":`). Это **НЕ** формат
   `{"op":"call","cmd":"apply_notes","params":{…}}` — тот вернёт
   `{"ok":false,"error":"Unknown command: apply_notes"}` (записи нот там нет).
   `scripts/rpc_call.py` оборачивает вызов в `{"op":"call",…}` и потому эту op
   **не умеет** — notes писать только напрямую:
   `printf '%s\n' '{"op":"apply_notes","notes":[…]}' | nc 127.0.0.1 9787`
3. Мост пишет скрипт в
   `~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/MCP_Apply.pyscript`
   и дёргает хоткей Cmd+Opt+Y.
4. **Раз в сеанс FL** пользователь запускает «MCP Apply» вручную из меню
   Piano roll → Tools → Scripts (нет API для arm).
Очистка нот: пустой `mode="replace"` реально чистит score (подтверждено
`grid_bits` все 0).

### Недеструктивная очистка (MCP_Read_Probe v3)
`MCP_Read_Probe.pyscript` **не** делает `score.clearNotes(True)` (это стирает
весь score). Он удаляет **только свои питчи** (84–100): snapshot → переписывание
списка нот только с этими питчами → `addNote` обратно. **Уточнение:** свойства
переписанных (чужих) нот, кроме `number/time/length/velocity`, сбрасываются
(pan/fine/release/color не сохраняются) — переписывание идёт через пересоздание
`Note`. Питчей, которых нет в `MARKER_PITCHES`, переписывание не касается.
Нитерация `for n in score:` **непрямо** подтверждена (deployed v3 отработал без
краша-91), но доказанный паттерн репо — `score.noteCount()` / `score.getNote(i)`
(`pyscript_gen._QUANTIZE_TEMPLATE`); при сбое итерации скрипт уйдёт в ветку 91
и сломает канал обратной связи Q2. Маркеры-маркеры убираются undo (Cmd+Z).

---

## Очистка / гигиена сеанса
- `scripts/test_bridge.py` (DoD-команда) — фактический состав шагов (по скрипту,
  не по догадке): `ping` (билд `e0-probe-v18`), `get_tempo`, `set_tempo +5`,
  восстановление темпа, `play`, `get_play_state (mid-play)`, `stop`; extended:
  `toggle_play` ×2, `get_song_position`, `set_song_position beats=4.0`,
  повторное чтение позиции, `record` ×2 (arm/disarm), cleanup (stop + poll до
  `recording: false` + reset позиции). Вывод процесса — процитирован в
  `docs/API_PROBE_26.md` (DoD-блок).
  - **Учтён баг cleanup**: `record` — тогл, его ответ сообщает **предыдущее**
    состояние, и `get_play_state` может отставать на тик. Раньше cleanup
    оставлял `recording: true`. Исправлено: poll с паузой 0.3 с до
    `recording: false` (до 5 ретраев); оставшийся `recording: true` помечается
    фейлом (all_ok=False). Подтверждено запуском: финальное состояние
    `{'playing': False, 'recording': False}`, «All checks passed».
- Ручной мусор спайка: тестовый паттерн `E0TEST` удаляется вручную
  (правый клик по паттерну → Delete; API-удаления паттернов нет, см. undo выше).
  После очистки `pattern_list total=1`, `pattern_count=1`.

## Стабильность контроллера
- FL **не** перечитывает контроллер сам. «Update» в MIDI settings иногда не
  подхватывает новый файл; toggle порта тоже. **Надёжно** — перезапуск FL
  (проверено: после «Update» FL отдавал старый build, после перезапуска — новый).
- Маркеры билда (в `_h_ping`): `e0-probe-v16` → `v17` (op `jump`) →
  `v18` (бюджет-пагинация op `step`). `fl_ping` первым делом, если что-то
  ведёт себя странно.
- Модальный диалог в FL блокирует RPC («Operation unsafe at current time») —
  закрывать (osascript System Events → click button).

---

## Прочие заметки
- Для отладки RPC напрямую: `python scripts/rpc_call.py <cmd> '<json>'`
  или `printf '%s\n' '{"op":"call","cmd":…,"params":{…}}' | nc 127.0.0.1 9787`.
- Удаление нот правым кликом pyautogui по ноте — **ненадёжно** (промахи, фокус
  уходит в другие окна); надёжнее pyscript-пересборка score (см. недеструктивную
  очистку выше).
- Замена плагина: правый клик по слоту → Delete; добавить можно только вручную.
- Distructor при переносе между дорожками сохраняет параметры.
- `prompts/` в корне репо — untracked, в коммит не тянуть.
