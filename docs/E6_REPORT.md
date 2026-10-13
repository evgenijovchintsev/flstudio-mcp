# E-6 — Note-bridge: honest `applied` + macOS trigger diagnostics

Spec: `prompts/flstudio-mcp-upgrade/01_IMPLEMENTATION_PROMPTS.md` epic E-6.
Depends on E-0 facts Q1 (`ui.runScript` absent), Q2 (pyscript sandbox:
file I/O blocked), Q3 (Cmd+Opt+Y works manually; auto hotkey unreliable).

## Outcome

`applied` is honest, not invented. Receipt file is impossible (E-0 Q2
proved the sandbox blocks read AND write), so the spec's option 2 applies.

**New probe fact (E-6):** the controller context ALSO cannot import
`flpianoroll` (`fl_api_probe("flpianoroll")` → `module not available`,
controller build `e6-flpianoroll-probe`, FL 26.1.7). So there is no
programmatic score-read channel on either side of the bridge today:
- pyscript sandbox: only `flpianoroll` (+ os/json), files blocked;
- controller: full FL API, but no `flpianoroll`, no `ui.runScript`.

Result: every note write reports `applied: "unknown"` with an explicit
`setup` explanation (verify visually; the one-time manual arm; E-7 will
add `fl_piano_get_notes`). `triggered` stays for backward compatibility
and now means only "the hotkey was sent".

## Trigger diagnostics (spec item 3)

`_trigger_macos` adds:
- `focus_ok` — frontmost-app check via System Events right before the
  hotkey (falls back to trusting `activate` if the check itself fails);
- `method` — `"osascript-activate+pyautogui-hotkey"`.

DoD's "5/5 automatic triggers on macOS": the trigger path itself passed
**5/5** live (`triggered=true`, `focus_ok=true`, `applied=unknown`). Note
E-0 Q3's distinction: a hotkey sent programmatically can still lose
modifiers in some contexts; the documented manual fallback (click Piano
roll, press Cmd+Opt+Y, or run MCP Apply from the menu) stays in README,
SKILL and the `hint`/`setup` fields.

## Changed

- `src/fl_studio_mcp/pianoroll.py` — `applied: "unknown"` + `setup`
  text on every path; `focus_ok`/`method` passthrough; docstring lists
  the status meanings.
- `src/fl_studio_mcp/pyscript_trigger.py` — macOS `focus_ok` + `method`.
- `src/fl_studio_mcp/tools/pianoroll.py` — docstring: status meanings.
- `src/fl_studio_mcp/connection.py` — docstrings (direct + daemon).
- `src/fl_studio_mcp/tools/probe.py` — `flpianoroll` module Literal.
- `fl_controller/.../device_FLStudioMCP.py` — guarded `flpianoroll`
  import in api_probe mods (probe result above); marker
  `e6-flpianoroll-probe`, deployed md5 `08c15775…` (FL reload needed
  once; the later md5 change is a comment-only ruff I001 fix).
- `README.md` — limitations rewritten: application cannot be confirmed
  today, verify visually, E-7 closes the loop; setup section notes the
  `applied: "unknown"` contract.
- `skills/flstudio-production/SKILL.md` — new "Note bridge" section:
  applied/needs-manual/unknown statuses + manual-arm recipe.

## Live verification

- `fl_api_probe("flpianoroll")` → `module not available` (controller
  reloaded, `build: e6-flpianoroll-probe` confirmed via fl_ping).
- 5× `fl_write_piano_roll_notes` → 5/5 `triggered=true`,
  `focus_ok=true`, `applied="unknown"` (daemon restarted to pick up
  the new module code).
- `ruff check .` — 689 (baseline; the one new I001 auto-fixed).

## Follow-up

- E-7 (`fl_piano_get_notes`): the controller-side `flpianoroll` import
  is now disproved — the file-based path is blocked too — so E-7 is
  expected to land `blocked` with this quote, or find a channel we
  haven't proved absent yet.
