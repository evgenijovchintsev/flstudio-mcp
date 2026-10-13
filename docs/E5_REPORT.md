# E-5 Report — Wrapper holes: presets, color reads, undo, api_probe

**Epic:** E-5 из `prompts/flstudio-mcp-upgrade/01_IMPLEMENTATION_PROMPTS.md`
**Branch:** `epic/E-5`
**Live FL:** Producer Edition v26.1.7 [build 5419], controller marker `e5-wrappers-v1`

## Live facts (measured, FL 26.1.7)

- **FL 26 has NO `setPreset` and NO preset index** — confirmed live via the
  new `fl_api_probe("plugins")`: the module exposes `getPresetCount`,
  `nextPreset`, `prevPreset` and name reads, nothing else preset-related.
  A by-name restore is impossible.
- **`nextPreset`/`prevPreset` are best-effort**: live, steps get swallowed
  on Fruity Parametric EQ 2 (track 1, slot 0, 13 presets) —
  `next` moved `3 bands → 20Hz + 18kHz cut`, a mirrored rollback did NOT
  bring the preset back. Same-RPC name readback also lags the navigation
  (the E-1 fader pattern).
- **`name_f6` needed `midi.GPN_GetCurrentPreset`** — the handler used to
  call `getName(flag=6, paramIndex=0)`, i.e. always the name of preset
  **#0**, which made every plugin look like it never changed presets.
  Fixed in the controller (falls back to 0 if the constant is missing).
  `name_f3` (flag 3, pidx 0) came back `''` on every probe — rely on
  `name_f6` only.
- **`fl_undo` is exact** — live: volume 0.7812 → set 0.9 → `fl_undo` →
  **0.7812**. It writes nothing to the changelog (by design).
- Color reads return `{int, hex, r, g, b}` for both channel and track;
  set-red → read-back → rollback round-trip on channel 3 works.
- Probe filter worst-case measured: `fl_api_probe("ui", "e")` used to ship
  675 B (names trimmed to 600, wrapper added ~75) — now the FULL envelope
  is measured, so filtered replies stay ≤600 B. No-filter pages were
  already in budget (midi worst=600, channels=600, plugins=257).

## Decisions

### Preset navigation: OUTSIDE the safety layer (review blocker (а))

The epic sketch offered mirror-next/prev as a best-effort restore. Live
testing proved that insufficient: navigation itself is flaky, so a
"rollback" could silently do nothing (the review reproduced exactly that).
Chosen design, matching the `fl_undo` precedent:

- `op=info` is a plain read (no changelog).
- `op=next/prev` are direct controller calls — **no snapshot, no changelog,
  no rollback claim**. Every response carries `rollback: "none"` and a
  `warning` string stating why (no setPreset/getPresetIndex; nav is
  best-effort). The tool also issues a **fresh-tick info re-read**
  (`current`) because the same-RPC name lags.
- The dead `plugin_preset:TRACK:SLOT` snapshot kind was removed from
  `safety.py` in the same change (E-2 convention: no dead declarations).

### `fl_undo`: outside the safety layer (spec option 2)

Nothing readable describes what an undo jump will undo, so a snapshot is
impossible; a changelog entry without a restore would pollute the rollback
stack (the next `fl_rollback_last_change` would error instead of undoing
the previous REAL write). Undo therefore joins `fl_play`/`fl_stop` as a
direct command. **Trap (documented in README/SKILL):** after `fl_undo`,
`fl_rollback_last_change` rolls back the write *before* the undo.

### `fl_api_probe` filter budget

With `pattern`, all pages are walked (`_MAX_PAGES=50`), matches filtered,
and the reply trimmed against `_LIST_BUDGET` measured on the **full
envelope** `{module, pattern, total, start, match_count, names, truncated}`
— the E-0 §2.2 contract (review blocker (в)). Without `pattern`: single
page passthrough (handler already budgets).

## Live scenario (post-review fixes)

| Step | Result |
|---|---|
| `fl_plugin_preset(1, 0, info)` | EQ2: `preset_count=13`, `name_f6` = current preset |
| `fl_plugin_preset(1, 0, next)` | `ok`, `rollback: "none"` + warning present; `current` re-read included |
| `fl_rollback_last_change` after nav | **not applicable** — no changelog entry (by design) |
| `fl_get_channel_color(3)` / set red / rollback | hex round-trips |
| `fl_get_track_color(1)` | `{int, hex, r, g, b}` |
| `fl_api_probe("ui", "e")` | full envelope ≤ 600 B, `match_count`/`truncated` honest |
| `fl_api_probe("plugins")` | names listed (new module in controller) |
| `fl_undo` after a volume write | previous value restored exactly |

## DoD

- [x] 5 tools work live (`fl_plugin_preset`, `fl_get_channel_color`,
      `fl_get_track_color`, `fl_api_probe`, `fl_undo`)
- [x] every write either has a correct scope/snapshot or an explicitly
      documented exception (preset nav + undo, both with response-level
      warnings)
- [x] `ruff check .` — 689 (delta 0)
- [x] README (82 tools + bullets + undo trap), SKILL (tool table),
      `00` §2.1 (82/53, four holes closed) — ROADMAP does not track
      epics (E-2/E-3/E-4 convention), map lives in `00` + reports

## QA E-5 findings (folded in)

QA verdict: PASS with remarks. Post-QA fixes in this report's follow-up
commit:

- **B1 — `fl_undo` does not undo `pattern_rename`** (undid=true, name
  unchanged): FL's `setPatternName` is not in FL's undo stack. Undo
  coverage varies by action type (volume/param writes undo; several API
  actions do not). Documented in the `fl_undo` docstring, response
  warning, README and SKILL — nothing readable can pre-check coverage.
- **B2 — undo × rollback do not commute**: an undo jump can cancel a
  rollback (QA reproduced a color coming back after undo). `fl_undo`'s
  response now carries the explicit non-commutativity warning plus
  `last_rollback` {tool, scope, age_s} — the newest changelog entry,
  which the undo may just have cancelled — and the docs demand a fresh
  state read after every undo.
- **B3 — preset step swallow**: matches the shipped warning; no change.
- **B4 — `RGBToColor` quantization** (`#00FF00` → `#14FF14`): noted in
  both `fl_set_*_color` docstrings — read back with the get tools.
- **B5 — session client stale tool list**: needs an opencode restart
  (server process already on `e5-wrappers-v1`); user action.

## Known limits / follow-ups

- Preset navigation cannot be rolled back via the API (FL limitation);
  the agent must navigate back manually or the user in the preset browser.
- `name_f3` is empty on tested plugins; only `name_f6` is trustworthy.
- `fl_undo` is irreversible and outside the changelog — the NEXT
  `fl_rollback_last_change` targets the write *before* the undo.
- The reviewer's live session left the EQ2 preset on track 1 / slot 0 at
  `30Hz/40Hz + 18kHz cut` — restore it by hand in the preset browser (the
  API honestly cannot).
