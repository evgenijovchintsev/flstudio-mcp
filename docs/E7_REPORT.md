# E-7 — `fl_piano_get_notes`: BLOCKED (no readable channel exists)

Spec: `prompts/flstudio-mcp-upgrade/01_IMPLEMENTATION_PROMPTS.md` epic E-7.
DoD explicitly allows: "либо туйл с живым сценарием, либо честный `blocked`
с доказательством из E-0". Both design paths are now disproved — this
report is that proof.

## Verdict: BLOCKED

No tool is shipped. `applied` on the note bridge stays honest `"unknown"`
forever until FL exposes a score-read channel (or a future FL build
changes the sandbox facts below — re-probe then).

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

## Path 2 — controller-side note-read API: DEAD (this epic's probe)

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
   (re-run the pattern searches in this report).

## Files changed

- `docs/E7_REPORT.md` (this file)
- `docs/E6_REPORT.md` — follow-up section: E-7 confirmed blocked
- `README.md` — note-bridge limitation no longer defers to E-7
- `skills/flstudio-production/SKILL.md` — note-bridge section: E-7 is
  blocked, not coming; `unknown` is permanent for now
- `prompts/flstudio-mcp-upgrade/00_OVERVIEW_AND_CONTRACTS.md` §2.1 —
  map line updated
