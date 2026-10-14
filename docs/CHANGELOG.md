# Changelog

## v1.1.0 -- E-0..E-8 tool surface + upstream PR port (14 Oct 2026)

The first big surface release since the SysEx rewrite: nine epics (E-0..E-8)
landed on `dev`, then the useful parts of nine upstream PRs from
`rosasynthesiz/flstudio-mcp` were ported and live-verified.

### Epics E-0..E-8

- **Note bridge** (`fl_write_piano_roll_notes` / `_raga_melody` /
  `_raga_chords`): bakes notes into `MCP_Apply.pyscript` and fires
  "Run last script again". Application stays honest `applied: "unknown"`
  (E-6) because FL exposes no score-read channel.
- **E-1/E-2**: pattern list / select / rename / get_length.
- **E-3**: `fl_screenshot` (agent debugging) into `~/.flstudio-mcp/shots/`.
- **E-4**: Channel Rack step-grid read / draw / clear, incl.
  `fl_channel_set_grid_bits`.
- **E-5**: plugin preset info / next / prev + `fl_api_probe` (module
  name listing).
- **E-7 / E-7b**: **BLOCKED, documented** -- all 11 egress channels out of
  the Piano-roll `.pyscript` sandbox are dead on FL 26.1.7 (file I/O,
  `flpianoroll` from controller, score-read APIs, global `Utils`,
  shell/`socket`/`subprocess`). Re-confirmed on build 5419. See
  `docs/E7_REPORT.md` for the full matrix and what would unblock it.

### Ported upstream PRs (live-verified on macOS / FL 26.1.7 build 5419)

- **#17** retarget Piano roll on channel select.
- **#18** optional per-note portamento (808 glides).
- **#16** Ctrl+Alt+Y by virtual-key code (Windows path no longer needs
  pyautogui).
- **#10 + #15** cross-platform FL user-data discovery (`paths.py`, Windows
  registry + SHGetKnownFolderPath, env overrides).
- **#11** opt-in virtual CoreMIDI / ALSA ports (self-created, no
  IAC/loopMIDI setup needed).
- **#12** (decomposed subset) playlist track control + arrangement read,
  deep VST/AU param control (`fl_plugin_overview` / `_calibrate_param` /
  `_set_param_value` / `_intent`), per-OS capability introspection, and an
  honest plugin-load limitation explainer.

Skipped upstream #13 (stale Windows docs). Tool count is now ~96.

## v0.2.0 -- MIDI SysEx transport

**Breaking change**: the transport between the MCP server and the FL
controller script switched from a file-based JSON queue to MIDI SysEx.
Protocol version bumped 1 -> 2. v0.1 clients and v0.2 controllers (or vice
versa) refuse to talk.

### Why

FL Studio's controller-script Python sandbox blocks every form of file
write. Confirmed on FL 24+ with MIDI scripting version 40 / embedded Python
3.12.1:

- `open("...", "w").write("...")` ->
  `SystemError: <class '_io.FileIO'> returned NULL without setting an exception`
- `os.open(..., O_WRONLY|O_CREAT|O_TRUNC)` ->
  `TypeError: bad argument type for built-in operation`
- `os.makedirs(...)` ->
  `mkdir returned NULL without setting an exception`

A normal OS process writing to the same directory succeeds, so it is the
controller-script sandbox specifically, not OS permissions. Piano Roll
`.pyscript`s run in a separate sandbox (only `flpianoroll` + `os`/`json`);
as of FL 26.1.7 (E-0 Q2 probe, 12 Oct 2026) **file I/O there is blocked
too** — the earlier note that this sandbox allowed file I/O is disproved.
Scripts there also only execute on explicit user trigger (`ui.runScript`
is absent) — they're not suitable for the heartbeat / always-on loop the
server depends on.

So all transport moved to MIDI SysEx, which is allowed in controller
scripts via `device.midiOutSysex` (out) and `OnMidiMsg` (in).

### What changed

- `src/fl_studio_mcp/protocol.py`: new SysEx wire format, manufacturer ID
  `0x7D`, magic `"MCP"`, base64-JSON payload. Default port names
  `FLStudioMCP RX` (server -> FL) and `FLStudioMCP TX` (FL -> server).
- `src/fl_studio_mcp/connection.py`: rewritten on `mido` + `python-rtmidi`.
  Background callback dispatches incoming SysEx, blocks the caller on a
  `threading.Event` keyed by request id. Heartbeat detected via incoming
  `DIR_HEARTBEAT` messages from FL.
- `fl_controller/FLStudioMCP/device_FLStudioMCP.py`: rewritten with
  `OnMidiMsg` dispatch and `device.midiOutSysex` response, plus a 500 ms
  heartbeat in `OnIdle`. No more file I/O.
- `pyproject.toml`: added `mido>=1.3.2` and `python-rtmidi>=1.5.8`.
- `server.py`: new `--list-ports` flag for debugging port mismatches.
- `fl_ping`: reports `port_to_fl` and `port_from_fl` instead of a bridge
  root.

### What did NOT change

- The 10 Phase 0 tool names and signatures
  (`fl_ping`, `fl_get_tempo`, `fl_set_tempo`, `fl_play`, `fl_stop`,
  `fl_toggle_play`, `fl_record`, `fl_get_play_state`,
  `fl_get_song_position`, `fl_set_song_position`).
- The command-name catalogue (`CMD_PING`, `CMD_GET_TEMPO`, etc).
- The tool-side error model (`FLNotRunning`, `FLTimeout`,
  `FLCommandFailed`). A new `FLPortMissing` was added for the MIDI-port
  setup failure mode.

### Setup deltas vs v0.1

You now need two virtual MIDI ports created up front:

- Windows: install loopMIDI, create `FLStudioMCP RX` and `FLStudioMCP TX`.
- macOS: add two ports of those names under IAC Driver in Audio MIDI Setup.

Then in FL: Options -> MIDI Settings, enable both ports, set their Port
numbers to the same value (the controller script uses the matching number
to route its responses to the correct output).

## v0.1.0 -- File-queue bridge (withdrawn)

Initial release. Withdrawn because the file-queue design did not work on
FL builds that sandbox controller-script file I/O (which appears to be
every recent FL build, not an edge case).
