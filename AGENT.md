# AGENT.md — FL Studio MCP: выводы сессии

Окружение: macOS, FL Studio 2026 v26.1.7 + fl-studio-mcp (исходники: `/Users/jeno/tmp/flstudio-mcp`),
venv: `/Users/jeno/tmp/flstudio-mcp/.venv/bin/python`.
Проект FL: `/Users/jeno/Desktop/New folder`. PID FL: 4225 (не перезапускался 10–11 окт).

## Запись параметров плагинов — КАК РАБОТАЕТ (итог, проверено на Fruity Fast Dist)

### RPC `plugin_set_param` работает, но с нюансами
Формат: `{"op":"call","cmd":"plugin_set_param","params":{"track":N,"slot":S,"param":I,"value":V}}`
(значение нормализовано 0..1). Порядок аргументов в контроллере —
`plugins.setParamValue(val, idx, track, slot)` — корректный.

Нюансы, из-за которых казалось «сломано»:
1. **FL «pickup» mode**: если окно плагина открыто и параметр недавно трогали мышью,
   FL показывает в hint-баре «*param* is waiting for pickup: X% > Y%» и ИГНОРИРУЕТ
   API-записи (все значения отбрасываются, даже ступенчатые). Симптом: set возвращает
   ok, но `v`/`s` всегда прежние.
   - Обход: **сдвинуть ручку мышью** (drag на пару десятков px) — это снимает pickup.
     После этого значение читается API, но API-set может всё ещё не цеплять — тогда
     нужное значение ставить мышью (точность ~1% достаточна).
   - Закрытие окна плагина тоже снимает pickup (проверено: после закрытия окна
     set заработал для Pre amp / Threshold).
2. **Гонка быстрых set**: несколько set подряд без пауз перетираются (FL применяет
   по тику). Делать паузу ~0.3–0.5 с между set и финальным чтением.
3. **Квантизация**: FL может округлить (0.65 → 0.6484, 0.45 → 0.4444) — это норма,
   сверять с допуском ±0.02.
4. Некоторые параметры (например Post gain у Fast Dist) могут вообще не поддаваться
   API-set, пока не сброшен pickup мышью.

### Порядок настройки плагина (рабочий рецепт)
1. `plugin_get_params` (с пагинацией `start`) — прочитать текущие значения.
2. Если подозрение на pickup: закрыть окно плагина ИЛИ заранее свернуть FL к минимуму
   взаимодействия с ручками; не трогать ручки мышью во время сессии записи.
3. `plugin_set_param` по одному параметру с паузой 0.3–0.5 с.
4. Свежим `plugin_get_params` проверить результат (допуск ±0.02).
5. Если параметр не двигается — проверить hint-бар (скриншот) на «waiting for pickup»;
   снять drag-ом мыши по ручке (координаты: скриншот → logical = screenshot * 1710/2000).

### Piano-roll pyscript: ТОЛЬКО flpianoroll
Песочница Piano roll scripts экспортирует исключительно модуль `flpianoroll`.
`import mixer` / `import plugins` / `import channels` / `import ui` / `import transport` —
все падают (проверено флажками-нотами: выполнился только baseline). Полный FL API из
pyscript-контекста Piano roll НЕДОСТУПЕН. Идея «обойти сломанный setParamValue через
pyscript внутри FL» — МЁРТВА.
Дополнительно (E-0, 12 окт): файловое чтение/запись из pyscript **заблокировано**
(receipt-файлы не создаются ни в одном из 3 путей); `print()` в View → Script output
**не виден**. Единственный канал «скрипт отработал» — сами ноты в score.
Подробности: `docs/API_PROBE_26.md` (Q2).

## Критические ограничения FL API (подтверждено)

- Нельзя загружать новые VST/AU-плагины — только контроль существующих.
- Нельзя создавать паттерны с нуля (можно клонировать через arrange_clone_pattern).
- Запись темпа игнорируется, если в FL открыт модальный диалог.
- `plugin_get_params` пагинирован (~7 params/ответ, лимит ~480 байт JSON, `next_start`).
- Команды showEditor в контроллере НЕТ.
- `ui.runScript` отсутствует → автозапуск pyscript из API невозможен.
  Триггер — только хоткей «Run last script again» (macOS: **Cmd+Opt+Y**).
- `patterns.findFirstNextEmptyPat()` в FL 26 **сломан**:
  `TypeError: function missing required argument 'flags'`. Fallback —
  `patterns.patternCount() + 1` (уже в `_h_arrange_new_pattern`).
- `patterns.jumpToPattern` безопасен: 0 → нормализуется в 1, past-max →
  срез к `patternMax` (999), пружин/создания паттернов нет (проверено E-0).

## Что работает

### Запись нот (pyscript-мост)
1. `channel_select` — выбрать канал Channel Rack.
2. RPC `{"op":"apply_notes","notes":[...],"mode":"replace","trigger":true}`.
   Формат ноты: `{pitch (MIDI, 60=C5 в отображении FL), time_bars, length_bars, velocity}`.
3. Мост пишет скрипт в
   `~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/MCP_Apply.pyscript`
   и дёргает хоткей «Run last script again» = **Cmd+Opt+Y**.
4. РАЗ В СЕССИЮ FL: пользователь запускает «MCP Apply» вручную из меню
   Piano roll → шестерёнка (Tools) → Scripts (нет API для arm).

### Прямой RPC
TCP `127.0.0.1:9787`, JSON + `\n`, ответ `{"ok":true,"data":{...}}`.
cmd: `plugin_list`, `plugin_get_params` (пагинация), `plugin_get_param`,
`plugin_set_param` (работает — см. выше), `mixer_list_tracks`, `mixer_get_track`,
`mixer_set_volume/pan/mute/solo/name/color`, `channel_list`, `channel_get`,
`channel_set_*`, `channel_select`, `channel_routing_summary`,
`mixer_get_routing(_all)`, `mixer_set_route`, `mixer_get_peaks`,
`arrange_new_pattern`, `arrange_clone_pattern`, `arrange_add_marker`,
`pattern_list`, `ensure_piano_roll`, `api_probe`, `plugin_preset`.
Записи микшера (volume unit='db', pan, mute, solo, name, color) — работают надёжно.

### Удаление нот из Piano roll
- Правый клик pyautogui по ноте — НЕНАДЁЖЕН (промахи, фокус уходит в другие окна).
- Надёжный способ: MCP_Apply-скрипт, который пересобирает score:
  собрать keep-список (ноты с pitch < порога), `score.clearNotes(True)`,
  обратно `addNote`. Требуется ручной запуск пользователем (см. arm выше).

### Координаты мыши (screencapture ↔ logical)
Разрешение экрана 3420×2214, logical 1710×1107 → знаменатель **1.71**.
`logical = screenshot_px / 1.71`. `screencapture` ~0.16 с (быстрее pyautogui
~0.27 с) — предпочитать для снапшотов. (Старый коэффициент 1710/2000=0.855
НЕ подтверждается.)
FL frontmost проверять osascript-ом перед кликами; иначе клики уходят в другое окно.

Форматы цветов/пресетов (E-0, стабильны):
- цвет канала/трека → `{"int":…,"hex":"#RRGGBB","r":…,"g":…,"b":…}`
- `plugin_preset info` → `{"preset_count":…,"plugin_name":…,"name_f3":…,"name_f6":…}`
- `slot=-1` на sampler → `Plugin not valid`; на генераторе — работает.

Больше фактов API-пробы FL 26.1.7: `docs/API_PROBE_26.md`.

## Состояние музыкального проекта

- Bro-step, **145 BPM** (поднято 11 окт), ОДИН паттерн на 32 такта:
  - 0-7: build, 8-15: drop, 16-23: DnB, 24-31: гибридный финал
- **Вабл-бас (Sytrus, ch5) переписан 11 окт** — рваный gated-wobble:
  билд ускоряется, дроп — гейты/октавные скачки D2-D4, DnB — роллинги+ризы,
  финал — гейты+16-е статтеры (168 нот; apply через pyscript_gen + ручной MCP Apply).
- Измерено при воспроизведении дропа (11 окт): Insert 6 peak ≈ −4.8 dB,
  Master peak ≈ −0.2 dB (почти клип! — при необходимости прибавить headroom).
- Каналы Channel Rack (index → name → mixer):
  - 0 808 Kick → Insert 1
  - 1 808 Clap → Insert 2
  - 2 808 HiHat → Insert 3
  - 3 808 Snare → Insert 4
  - 4 808 Astronomic (мелодия + саб) → Insert 5
  - 5 Sytrus (wobble bass) → Insert 6
- Master: плагинов НЕТ.
- **Insert 6: Fruity Fast Dist, фейдер −3 dB — перенастроен 11 окт (агрессивно)**:
  - Pre amp 0.8516 (90%) — RPC
  - Threshold 0.3333 (40%) — RPC
  - Distortion type **B** — API-set не берёт (ступенчатый); переключено кликом
    по A/B-тумблеру мышью (скриншот → logical: x*0.855)
  - Post gain 0.6875 (~69%) — мышью (pickup-режим блокировал API)
  - Mix level 1.0 (100%)
- Мусорные диагностические ноты (C7/C10/клики) из Piano roll Sytrus УДАЛЕНЫ
  (пересборкой score, keep pitch < 96).

## Прочие заметки

- `fl_ping` первым делом, если что-то ведёт себя странно.
- Мост MIDI может падать при перезапуске терминала — перезапуск демона через
  `launchctl submit -l com.jeno.flstudio-mcp-daemon` (иначе убивается таймаутом шелла);
  после перезапуска порт FLStudioMCP RX может потребовать переключения в FL MIDI Settings.
- Модальный диалог в FL (например, Piano roll - score flipper от Opt+Y) блокирует RPC
  («Operation unsafe at current time») — закрывать (osascript System Events → click button).
- Хоткей Cmd+Opt+Y через pyautogui/osascript теряет модификаторы — не использовать
  для автоматизации; ручной запуск пользователя надёжнее.
- Замена плагина: правый клик по слоту → Delete; добавить можно только вручную.
- Distructor при переносе между дорожками сохраняет параметры.
- Для отладки RPC напрямую: `/Users/jeno/tmp/flstudio-mcp/.venv/bin/python -c ...`
  (полезно, когда MCP-инструмент возвращает обрезанные данные).
