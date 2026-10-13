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
  hotkey. Review fix: if the check explicitly shows FL is NOT frontmost
  the hotkey is **refused** (`sent_hotkey: false` + error/hint — a
  Cmd+Opt+Y in a foreign app is worse than none); if the check itself
  throws, `focus_ok` is omitted (unverified) instead of claiming true;
- `method` — `"osascript-activate+pyautogui-hotkey"`.

Review fix (blocker 1): `docs/architecture.md` and `docs/CHANGELOG.md`
(v0.2.0) still claimed the Piano-roll sandbox allows file I/O —
disproved by E-0 Q2 (FL 26.1.7). Both paragraphs now cite the probe so
E-7's design reads the current fact.

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

## QA E-6 findings (PASS with remarks)

QA verdict PASS: S1 write/replace visual PASS, S2 5/5 API PASS, S3 empty
restore visual PASS, S4 trigger=False honest, S5 stale receipt ignored
(planted `apply_receipt.json` with `applied:true` — response stayed
`"unknown"`, no `receipt` field).

- **B1 (critical, fixed)** — focus-check false negative: System Events
  returns the process name `OsxFL` on this machine (CFBundleName is
  still "FL Studio"), so `"FL Studio" in front` refused every hotkey in
  the standalone path. Fix accepts both names; sim: `OsxFL` →
  `focus_ok:true, sent_hotkey:true`, `Safari` → refused. In the daemon
  path System Events itself throws, so the honest check_failed omission
  applies (hotkey sent, `focus_ok` absent) — QA's observed behavior.
- **B2 (minor, by design)** — one manual "MCP Apply" arm per FL session;
  `ui.runScript` is absent, documented in docstrings/setup/SKILL.
- **B3 (minor, documented)** — `ensure_piano_roll` only does
  `ui.showWindow`; it does NOT retarget an already-open Piano roll to
  another channel (stays on 808 Kick after selecting Snare). Not an E-6
  blocker; note-bridge writes go to whatever channel the open Piano roll
  shows.
- **B4 (info)** — `applied` is always `"unknown"` until E-7; contract.

State QA left: Piano roll empty (S3), MCP_Apply.pyscript `NOTES=[]`,
stale receipt deleted, TMP_E6 pattern (index 2) left for manual removal
(no pattern-delete API — E-0 Q4).

## Follow-up

- E-7 (`fl_piano_get_notes`): the controller-side `flpianoroll` import
  is now disproved — the file-based path is blocked too — so E-7 is
  expected to land `blocked` with this quote, or find a channel we
  haven't proved absent yet.
  **(Done — E-7 landed BLOCKED, `docs/E7_REPORT.md`: full-module probe
  found no score-read API anywhere; `applied` stays `"unknown"`.)**
