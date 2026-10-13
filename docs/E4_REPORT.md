# E-4 Report — Channel Rack step-grid (draw / read / clear)

**Epic:** E-4 из `prompts/flstudio-mcp-upgrade/01_IMPLEMENTATION_PROMPTS.md`
**Branch:** `epic/E-4` — `cc89b9a` (implementation), + safety-contract fix (this report's live-run findings)
**Live FL:** Producer Edition v26.1.7 [build 5419], controller marker `e4-grid-v1`

## API facts (verified live + official docs)

Docs: <https://www.image-line.com/fl-studio-learning/fl-studio-beta-online-manual/html/midi_scripting.htm>
(`#script_module_channels`, `#stepParams`).

- `channels.getGridBit(index, position)` / `setGridBit(index, position, value)` —
  read/write one step; value 0 = off, non-zero = on.
- `channels.getCurrentStepParam(index, step, pVelocity)` / `setStepParameterByIndex(index, patNum, step, pVelocity, value)` —
  per-step velocity (`pVelocity = 1`).
- **Velocity scale is RAW 0..127** — live round-trip on empty steps 60..63:
  wrote `[90, 100, 110, 120]`, read back exactly `[90, 100, 110, 120]`.
  Pattern-authored hits default to ~115. OFF steps read back `-1` (or a
  stored value on a previously-hit step).
- **No rack-length API exists.** `steps_total` is derived from the current
  pattern: `beats × 4` (16th-note steps), floor 16 — fresh 4-bar pattern →
  64. Never hardcoded to 16 (the old probe's budget).

## Design decisions

- **4 CMD / 4 handlers / 4 tools**, mirror pairs: `channel_get_grid`,
  `channel_set_grid_bit`, `channel_set_grid_bits`, `channel_clear_grid`.
- **Windowed reads**: `get_grid` returns 16 steps per RPC (budget: the
  64-step dump measured ~431 B in `API_PROBE_26.md` Q1) with `next_start`
  pagination; the MCP tool merges pages up to the `_LIST_BUDGET`.
- **Batch is ONE RPC** (`channel_set_grid_bits`, max 64 pairs), not
  `safe_write_group`: one SysEx, one undo entry, no E-1 pacing needed.
  Recorded deviation from the epic sketch — deliberate.
- **Rollback**: new snapshot kind `channel_grid:N` = the whole bit grid;
  restore rewrites the touched bits through the batch command.
  **Velocity is NOT in the snapshot** — rollback restores 0/1 bits only.
  Documented limit; per-step velocities of pre-existing hits survive a
  rollback of a batch that only re-set their bit.
- Writes route through `safe_write` (one changelog entry per tool call).

## Safety-layer findings (cross-cutting, fixed in this epic)

Live run exposed two honesty gaps in `safety.safe_write`:

1. **`{"ok": false}` from a handler was wrapped in `ok: true`** —
   `fl_channel_set_grid_bit(step=64)` "succeeded" with the rejection hidden
   in `after`. Now `safe_write` raises `ValueError("write rejected by FL: …")`
   and logs nothing (the write did not happen). `safe_write_group` stops at
   the first rejection but still logs the changelog (restores cover every
   snapshotted scope, so earlier writes in the group stay rollback-able).
2. **Handler replies were invisible to callers** — safe_write responses now
   carry `echo` (applied counts, `velocity_readback`, ...). Additive field;
   existing tools unaffected.

## Live scenario (ALL PASS)

| Step | Result |
|---|---|
| `get_grid(0)` baseline | `steps_total=64`, 808 Kick bits `1011…` at 0,2,3 |
| dry-run `set_grid_bits` 4-on-the-floor | `planned`, grid unchanged |
| real batch `[[0,100],[4,100],[8,100],[12,100]]` | `echo.applied=4`, bits at 0,4,8,12 on (old 2,3 kept) |
| `rollback_last_change` | grid = baseline |
| isolated velocity probe 60..63 | raw 0..127 round-trip exact |
| probe rollback | bits back to 0 |
| `set_grid_bit(step=64)` | raises `write rejected by FL: step 64 out of range 0..63`; grid untouched |
| single bit + `echo.velocity_readback` | `80` = written value |
| `clear_grid(0..3)` + rollback | zeroed, then restored |
| `channel=-1` | pydantic `ge=1` validation error |

## DoD (спека E-4)

- [x] Рабочие тулы (4) — live-прогон выше
- [x] Живой сценарий + rollback — ALL PASS
- [x] ruff — 689 (бейзлайн 691 − два I001, починенных заодно)
- [x] README (77 tools + composition bullet), SKILL (drum-row без «Phase 1»),
  `00_OVERVIEW_AND_CONTRACTS.md` (77/52)
- [x] ROADMAP — эпики там не трекаются (по аналогии с E-2/E-3)

## Known limits / follow-ups

- Per-step `pRelease`/`pFinePitch`/`pPan` are not exposed (only on/off + velocity).
- Rollback does not restore per-step velocities (bit-only snapshot).
- `get_grid` window is 16 steps/RPC by design; full 64-step dump = 4 merged pages.
