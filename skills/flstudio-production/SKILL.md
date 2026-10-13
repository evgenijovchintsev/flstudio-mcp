---
name: flstudio-production
description: Use this skill whenever the user wants to control FL Studio from Claude — write or trigger drum patterns, set tempo, change mixer levels, write notes to the Piano Roll, work with Carnatic ragas or kuthu rhythms in FL Studio, or troubleshoot the FLStudioMCP bridge. Trigger on FL Studio, FL, Fruity Loops, FLStudioMCP, "FL-il pannu", music production via Claude. ALWAYS use the fl-studio MCP server tools — never instruct the user to perform the change manually if a tool exists.
---

# FL Studio production skill

This is the orchestration layer. Deep content lives in `references/`.

## Before you act

1. Call `fl_ping` once at the start of every session. If `alive: false`,
   stop and tell the user to open FL Studio and select FLStudioMCP as a
   controller type. Do not retry blindly.
2. Read `references/limits.md` so you don't promise things the FL API can't
   deliver (no plugin loading, no new-pattern creation, etc).
3. If the user is going to write Piano Roll notes, FL Studio must be the
   focused window. Warn them once at the start.

## Tool selection

| User intent | Tools |
|---|---|
| Tempo, play, stop | `fl_set_tempo`, `fl_play`, `fl_stop`, `fl_toggle_play` |
| Where are we in the song | `fl_get_song_position` |
| Drum patterns | `fl_channel_get_grid` (read the bit grid), `fl_channel_set_grid_bit` / `_set_grid_bits` (draw steps, velocity 0..127), `fl_channel_clear_grid` — Channel Rack, NOT the Piano Roll |
| Mixer levels | `fl_mixer_set_volume`, `_set_pan` (Phase 2) |
| Melody in a raga | `fl_preset_write_raga_melody` (Phase 6) which calls Piano Roll under the hood |
| Kuthu beat | `fl_preset_write_kuthu_pattern` (Phase 6) |
| Read a plugin's knobs | `fl_plugin_list`, `fl_plugin_get_params` (names + normalised 0..1 values) |
| Change one knob | `fl_plugin_set_param` — answers `verified` / `attempts`; a `hint` means FL refused the value |
| Change several knobs of one plugin | `fl_plugin_set_params` — one paced burst, ONE undo step; prefer it over repeating the single tool |
| List / pick / rename patterns | `fl_pattern_list` (paginated), `fl_pattern_select`, `fl_pattern_rename` — select/rename are one rollback step each |
| How long is a pattern | `fl_pattern_get_length` — beats (FL's native unit) + derived bars/ticks via the project PPQ |
| Step through a plugin's presets | `fl_plugin_preset(track, slot, op)` — info (read-only) / next / prev; **NO rollback** (FL has no set-preset) — the response warns; navigate back manually |
| Undo the last FL action | `fl_undo` — exact on volume/param writes, but **undo/rollback do not commute** (undo can cancel a rollback) and some API actions (e.g. pattern rename) are not in FL's undo stack; the response warns + shows `last_rollback` — re-read state after every undo |
| Read a color | `fl_get_channel_color`, `fl_get_track_color` — `{int, hex, r, g, b}` |
| Probe the FL scripting API | `fl_api_probe(module, pattern?)` — names of one module, budget-paginated |
| See FL on screen / debug visually | `fl_screenshot` — PNG path to Read back (see «Debugging with screenshots») |

### Note bridge (writing notes into the Piano roll)

Writing notes uses a generated `.pyscript` + FL's "Run last script again"
hotkey — there is no FL API to run a script (`ui.runScript` is absent). Status
meanings to relay to the user:

- **`applied: "unknown"` (always, today)** — E-6 proved there is NO
  programmatic confirmation channel: the pyscript sandbox blocks file I/O
  (no receipt file) and the controller cannot import `flpianoroll` (cannot
  read the score back). Verify notes visually in the Piano roll. `applied:
  true/false` arrives with E-7 (`fl_piano_get_notes`).
- **`triggered: true`** — only means the run-last-script hotkey was sent,
  NOT that notes appeared.
- **needs-manual** — if notes did not appear: the one-time arm is missing.
  Recipe: open the Piano roll → Tools → Scripts → **MCP Apply** (run once
  this FL session; after that `Cmd+Opt+Y` / `Ctrl+Alt+Y` re-runs it). Check
  `focus_ok`/`method` in the trigger result when debugging macOS focus.

### Plugin parameter recipe

Trust `verified`, not the request. Measured on FL 26 with Fruity Parametric
EQ 2: levels and gains take an arbitrary 0..1 value; stepped parameters
(filter types, orders, selectors) snap to their own grid, so an off-grid
request comes back `verified: false` with the snapped value in `after`; some
parameters (band widths) ignore writes entirely. An open plugin window
(pickup mode) did not block script writes in our test. Values are the
normalised 0..1 domain shown by `fl_plugin_get_params` — read the display
string (`3.6dB`, `500Hz`) to know what a value means, and prefer
`fl_plugin_set_params` for 2+ knobs (one undo step).

### Debugging with screenshots

`fl_screenshot()` (macOS `screencapture -x`, no focus stealing) captures the
screen for **agent debugging** — checking a plugin window, the hint bar, or
whether FL is focused — not part of the music workflow. It returns a PNG
path (default `~/.flstudio-mcp/shots/<timestamp>.png`, auto-cleaned after
7 days); Read that path to see the image. `region=[x, y, w, h]` crops in
LOGICAL points (the coordinates pyautogui clicks in), never PNG pixels: on
retina the PNG is 2x the logical screen (measured E-0 Q5: 1710x1107 logical
→ 3420x2214 px), so `logical = px / (png_width / logical_width)` — measure
that ratio per display, don't hardcode 2.0. No Screen Recording permission?
The tool returns `ok: false` with a hint toward System Settings → Privacy &
Security → Screen Recording.

## When something fails

- `FLNotRunning` → bridge is healthy, FL is not. Ask user to open FL.
- `FLTimeout` → controller is loaded but stalled. Ask user to re-select
  FLStudioMCP in MIDI Settings.
- `FLCommandFailed` with `code=client` → bad input. Show the user what was
  wrong and ask for a correction.

## References

- `references/limits.md` — FL API constraints.
- `references/ragas.md` — How the Carnatic raga preset pack is organised.
- `references/kuthu.md` — Kuthu / gaana rhythm vocabulary.

(These references are written as Phase 6 ships.)
