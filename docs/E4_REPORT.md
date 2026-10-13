# E-4 Report — Channel Rack step-grid (draw / read / clear)

**Epic:** E-4 из `prompts/flstudio-mcp-upgrade/01_IMPLEMENTATION_PROMPTS.md`
**Branch:** `epic/E-4` — `cc89b9a` (implementation), `2c3b7d5` (safety-contract + docs), review fixes (this report)
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
  pagination; the MCP tool merges pages and stops before the merged
  lists exceed `_LIST_BUDGET = 600` compact-JSON bytes, returning
  `next_start` so the agent paginates the rest (E-4 review blocker (д)
  — an unbounded `count=None` merge measured 929 B with no resume point).
- **Batch is ONE RPC** (`channel_set_grid_bits`, max 64 pairs), not
  `safe_write_group`: one SysEx, one undo entry, no E-1 pacing needed.
  Recorded deviation from the epic sketch — deliberate. Live-verified at
  the full 64-pair cap (~0.6 KB payload lands, `applied=64`).
- **Rollback**: new snapshot kind `channel_grid:N` = the whole bit grid
  **plus per-step velocities** (same page walk); restore rewrites the
  touched bits through the batch command — ON bits at their snapshotted
  velocity, OFF bits as 0. (Review blocker (б): the first version stored
  bits only and restored ON hits with value=1 — silent. Live proof of
  the fix: `set(48,90) → clear → rollback` → bit48 back at velocity 90.)
  Velocities that are unreadable in the snapshot (`None`/`-1`/error
  string on an ON bit) fall back to **115**, FL's observed default for
  pattern-authored hits.
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
| `get_grid(0)` baseline | 808 Kick bits `1011…` at 0,2,3 |
| dry-run `set_grid_bits` 4-on-the-floor | `planned`, grid unchanged |
| real batch `[[0,100],[4,100],[8,100],[12,100]]` | `echo.applied=4`, bits at 0,4,8,12 on (old 2,3 kept) |
| `rollback_last_change` | grid = baseline |
| isolated velocity probe 60..63 | raw 0..127 round-trip exact |
| probe rollback | bits back to 0 |
| `set_grid_bit(step=64)` | raises `write rejected by FL: step 64 out of range 0..63`; grid untouched |
| single bit + `echo.velocity_readback` | `80` = written value |
| `clear_grid(0..3)` + rollback | zeroed, then restored |
| `channel=-1` | pydantic `ge=1` validation error |
| **review fix (б)**: empty ch2, `set(48,90) → clear → rollback` | bit48 back at **velocity 90** (was silently 1) |
| **review fix (б)**: `clear` over real 808 hits + rollback | bits and velocities (`40` we set, originals) all back |
| **review fix (д)**: full read, `count=None` | 586 B / 48 steps, `next_start=48`; union of pages covers **256/256** in 6 pages |
| **risk (батч)**: full 64-pair batch | `applied=64`, velocities round-trip `[1,3,5,7,…]`, rollback clears all |

Bonus live fact: the user's `Pattern 1` had grown to 64 beats (16 bars)
between sessions — `steps_total` correctly followed to **256** (the
no-hardcode derivation doing its job; pagination covered the whole grid).

## DoD (спека E-4)

- [x] Рабочие тулы (4) — live-прогон выше
- [x] Живой сценарий + rollback — ALL PASS
- [x] ruff — 689 (бейзлайн 691 − два I001, починенных заодно)
- [x] README (77 tools + composition bullet), SKILL (drum-row без «Phase 1»),
  `00_OVERVIEW_AND_CONTRACTS.md` (77/52)
- [x] ROADMAP — эпики там не трекаются (по аналогии с E-2/E-3)

## Known limits / follow-ups

- Per-step `pRelease`/`pFinePitch`/`pPan` are not exposed (only on/off + velocity).
- Unreadable snapshot velocities on ON bits fall back to 115 on restore
  (conscious default, not a silent 1).
- `get_grid` window is 16 steps/RPC by design; the merged reply is
  budget-capped (600 B) — resume via `next_start`.
- Pre-fix lossy rollbacks had already stamped velocity 1 onto the 808
  Kick's hits; repaired live to the FL default 115 after the fix landed.
