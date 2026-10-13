# E-2 Report — Patterns (select / rename / get_length / list)

**Epic:** E-2 из `prompts/flstudio-mcp-upgrade/01_IMPLEMENTATION_PROMPTS.md`
**Branch:** `epic/E-2` — `0f0bcdb` (implementation), `07995fe` (QA: beats fix), `8fa03d5` (QA: error surfacing)
**Live FL:** Producer Edition v26.1.7 [build 5419], controller marker `e2-patterns-v2`

## Decision: `CMD_PLUGIN_LIST_PARAMS` removed (not aliased)

`protocol.py` declared `CMD_PLUGIN_LIST_PARAMS = "plugin_list_params"` with no
handler in `_HANDLERS` and no MCP tool — a dead declaration (Phase 1B-era).

Options considered:

1. **Implement it** — rejected: `plugin_get_params` already provides the full
   paginated parameter dump (index, name, normalised value) via
   `fl_plugin_get_params`; a second command would duplicate a hot path.
2. **Alias** — rejected: an alias needs a handler anyway; two names for one
   RPC complicate the protocol-sync contract (§2.1) for no client.
3. **Delete the declaration** — taken. Evidence before removal: repo-wide
   `grep -r plugin_list_params` matched only the `protocol.py` declaration,
   `ROADMAP.md` (Phase 5 planning line), and the epic-plan prompts — no code,
   no client. After removal: no code references remain (the remaining match in
   `protocol.py` is the explanatory comment).

`ROADMAP.md` Phase 5 now states the coverage explicitly
(`fl_plugin_get_params` covers the old `fl_plugin_list_params` name).

## Live facts (measured, FL 26.1.7)

- **`patterns.getPatternLength` returns BEATS, not ticks** — official FL MIDI
  scripting docs: *"Returns the length of the pattern at index, in beats."*
  Observed: a fresh pattern = 16 beats = 4.0 bars at `RecPPB/RecPPQ = 4`
  (PPQ 96). Derived in the handler: `length_ticks = beats × RecPPQ`,
  `length_bars = beats / (RecPPB / RecPPQ)` (fallbacks: PPQ 96, 4/4).
- **Out-of-range selection is rejected twice**: pydantic `ge=1` at the tool
  layer, controller range guard (`index ≤ patternCount`) behind the snapshot —
  FL itself silently clamps `jumpToPattern` past the count to `patternMax`
  (999), i.e. a non-existent pattern, so unguarded selection would "succeed"
  on a phantom pattern. No garbage patterns are created by either path.
- **Patterns cannot be deleted via the API.** A test pattern can only be
  renamed to a `TMP_*` marker and removed by hand in FL (documented in
  ROADMAP Phase 3 and the test script output).
- `pattern_list` names are capped at 24 chars in LIST responses (honest
  `trunc: true` flag, budget §2.2); full names are readable via
  `fl_pattern_get_length`.

## Live scenario (DoD)

```
FLSTUDIO_MCP_TRANSPORT=tcp <venv>/python scripts/test_e2_patterns.py
```

**ALL PASS (0 failed)** — list pagination & 1-based contiguity, create,
rename (old name snapshotted), select (previous selection snapshotted),
length (beats/bars/ticks + `beats×ppq==ticks` invariant), rollback-select,
rollback-rename, rejections (select 0/9999/-3, get_length 0).
`scripts/test_bridge.py` — green; `ruff check .` — 692 (baseline, delta 0).

## Contract sync (§2.1 proof)

- `CMD_PATTERN_LIST/SELECT/RENAME/GET_LENGTH` (`protocol.py:114-117`) ↔
  `_HANDLERS` (`device_FLStudioMCP.py:1299-1302`) — 4/4, names literal.
- Repo-wide: 48 `CMD_*` ↔ 48 `_HANDLERS` entries, both directions empty diff.
- 72 MCP tools (`grep -c "@mcp.tool"` == `len(list_tools())`).

## Not covered by tests

- Multi-page `pattern_list` runs were not exercised live (project has <2
  pages); the budget path is `_paginate`, proven in E-0 on other lists.
- Rollback against an index deleted between snapshot and restore is
  unreachable (no delete API), but the error path now surfaces the
  controller's range message.
- Rename with empty/very long names and name conflicts: not exercised.
- Late rollback of a rename over someone else's rename restores the
  snapshotted name (by design, untested live).
