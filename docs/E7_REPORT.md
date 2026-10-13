# E-7 — `fl_piano_get_notes`: BLOCKED (no readable channel exists)

Spec: `prompts/flstudio-mcp-upgrade/01_IMPLEMENTATION_PROMPTS.md` epic E-7.
DoD explicitly allows: "либо туйл с живым сценарием, либо честный `blocked`
с доказательством из E-0". Both design paths are now disproved — this
report is that proof.

## Verdict: BLOCKED

No tool is shipped. `applied` on the note bridge stays honest `"unknown"`
forever until FL exposes a score-read channel (or a future FL build
changes the sandbox facts below — re-probe then).

## E-7b re-probe (13 Oct 2026): every remaining egress channel also DEAD

After E-7's initial verdict, two documentation leads suggested untested
channels. Both were probed live (`MCP_Read_Probe` v4, FL 26.1.7 build
5419, deployed md5 `617d7d6c…`, marker tones 84–107; verdict read from
the score via screenshot since no API can read it back — itself the
point of this epic):

1. **Global `Utils` (log / ProgressMsg / ShowMessage)** — FL's own
   `Piano roll script reference.txt` (shipped in the FL 2026 app bundle)
   documents a sandbox-injected global `Utils` with `log()` ("writes to
   the FL Studio debug log tab"), `ProgressMsg()`, and `ShowMessage()`.
   If present, `ProgressMsg` → hint panel → controller `ui.getHintMsg()`
   (already readable via `api_probe op=step`) would have been a
   bidirectional egress with zero controller changes.
   **Result: the global does not exist in the sandbox** — probe tone 101
   (presence), 102 (log), 103 (ProgressMsg) all absent; the hint panel
   stayed empty; `mdfind` for the probe token found nothing but the
   script sources. The reference documents the piano-roll IDE's own
   script host, not the MIDI-controller-style sandbox FL actually runs
   `.pyscript` files in.
2. **Shell / network escapes** — `os.system`, `os.popen`, `os.open`+write,
   `socket` (TCP to the local MCP daemon on 127.0.0.1:9787),
   `subprocess`, `ctypes`. E-0 had only tested the builtin `open()`.
   **Result: all dead** — tones 98–100 (imports) and 104–106
   (os.system/os.popen/os.open) absent; no `/tmp/flmcp_e7b_*` files
   appeared; tone 107 (socket↔daemon round-trip) absent. `os` itself
   imports (path helpers work) but every capability beyond `os.path` is
   blocked.

One delta vs E-0 v3: `midi` is now importable in the sandbox (tone 96).
It exposes only constants — not an egress channel, noted for completeness.

Full matrix (v4 run, 13 Oct 2026): 11 egress channels tested, 0 alive.
The only inbound-outbound pair that works is `flpianoroll` inside the
sandbox, and it cannot cross the sandbox boundary.

## Path 1 — file receipt from the pyscript sandbox: DEAD (E-0 Q2)

The Piano-roll `.pyscript` sandbox (FL 26.1.7, probe run v3, 12 Oct 2026
17:41, `docs/API_PROBE_26.md` Q2):

- only `flpianoroll` (+ `os`/`json`) importable out of 13 probed modules;
- `ui`, `channels`, `general` do NOT import;
- **file read AND write both blocked** — a control `probe.json` was
  created beforehand (mtime verified before the run), yet the script's
  read-failure tone (85) and write-failure tones (86) never appeared;
  no receipt file showed up in any of the 3 attempted paths;
- `print()` does not reach us; the only feedback channel is notes
  written back into the score — invisible without eyes/screenshot.

So the spec's `MCP_Read.pyscript` → `piano_notes.json` design has no
file to land in. (Spec item 3's conflict note is moot: there is no
receipt to share a poll helper with.)

## Path 2 — controller-side note-read API: DEAD (this epic's probe + official docs)

E-7 spec item 2 requires a probe of the CONTROLLER context (full FL API,
not the sandbox). Probed live via `fl_api_probe` (build
`e6-flpianoroll-probe`, FL 26.1.7):

- `flpianoroll` from the controller: `module not available` (E-6 fact,
  re-confirmed);
- pattern searches across ALL 11 probed modules for `note`/`Note`/
  `score`/`Score`/`piano`/`Piano` return only constants, setters and
  event injectors — e.g. `midi.MIDI_NOTEON`, `channels.midiNoteOn`,
  `patterns.setLoopStarterRootNote`, `general.dumpScoreLog` (writes an
  FL log we cannot read back via API);
- full `dir(patterns)` (31 names) and `dir(general)` (30 names) dumped:
  no `getNote*`, no score reader of any kind.

FL's scripting API simply does not expose Piano-roll score contents to
controller scripts. Reading the score is possible ONLY inside the
sandbox via `flpianoroll` — and that sandbox cannot send anything back.

**Official confirmation** (found during E-7b docs research): the
Image-Line-maintained type stubs
([IL-Group/FL-Studio-API-Stubs](https://github.com/IL-Group/FL-Studio-API-Stubs),
`piano_roll_scripting/flpianoroll`) state verbatim: *"Note that this
module is not accessible in MIDI Controller Scripts, it can only be
used in scripts that run in FL Studio's piano roll."* Image-Line's own
docs agree with our live probe — Path 2 is not a gap we failed to
find; it does not exist by design.

## Consequences (documented, not invented)

- Note writes keep returning `applied: "unknown"` (E-6 contract) — this
  epic does not upgrade it. README/SKILL wording updated: E-7 did not
  close the loop; verification stays visual.
- No screenshot-reading "verification" was built (spec forbids
  «на глаз», and E-3's screenshot tools are for clicks/coords, not note
  pitch decoding).

## What would unblock E-7

Any ONE of, on a future FL build:
1. sandbox file I/O allowed (re-run E-0 Q2 control-file probe);
2. `flpianoroll` importable from controller context (re-run
   `fl_api_probe("flpianoroll")`);
3. a score-read function appearing in `dir(patterns)`/`dir(midi)`/etc.
   (re-run the pattern searches in this report);
4. any of the E-7b channels coming alive — global `Utils` in the
   sandbox, `os.system`/`socket`/`subprocess` unblocked, or a new
   export API (re-run `MCP_Read_Probe` v4; deployed md5 `617d7d6c…`,
   source `fl_pyscripts/MCP_Read_Probe.pyscript`).

## Files changed

- `docs/E7_REPORT.md` (this file; E-7b section added 13 Oct)
- `fl_pyscripts/MCP_Read_Probe.pyscript` — v4 egress-matrix probe
  (deployed to `~/Documents/Image-Line/FL Studio/Settings/Piano roll
  scripts/`, md5 `617d7d6c…`)
- `docs/E6_REPORT.md` — follow-up section: E-7 confirmed blocked
- `README.md` — note-bridge limitation no longer defers to E-7
- `skills/flstudio-production/SKILL.md` — note-bridge section: E-7 is
  blocked, not coming; `unknown` is permanent for now
- `prompts/flstudio-mcp-upgrade/00_OVERVIEW_AND_CONTRACTS.md` §2.1 —
  map line updated
