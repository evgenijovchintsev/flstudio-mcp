# AGENTS.md

Guidance for AI agents (and humans) working on this repository. The full
design history lives in `docs/`; this file is the short orientation.

## What this is

An MCP server that lets an AI assistant drive FL Studio (mixer, plugins,
piano roll, routing, project) through ~82 `fl_*` tools. FL Studio's
scripting API is the substrate — read `README.md` **Limitations** first;
many "bugs" are API constraints we document instead of work around.

## Architecture (layers)

```
MCP client (Claude, etc.)
  └─ src/fl_studio_mcp/tools/*.py     # fl_* tools, each register(mcp)
       ├─ safety.py                   # snapshot → changelog → rollback
       ├─ protocol.py                 # CMD_* constants, PROTOCOL_VERSION
       └─ connection.py               # get_bridge() → FLBridge | TCPBridge
            └─ daemon.py              # JSON-RPC server (fl-studio-mcp-daemon)
                 └─ MIDI SysEx → fl_controller/FLStudioMCP/device_FLStudioMCP.py
                      └─ _HANDLERS: cmd → FL API (mixer/channels/plugins/ui/…)
```

Note writing is a separate path: `pyscript_gen.py` bakes notes into
`MCP_Apply.pyscript`, `pyscript_trigger.py` fires "Run last script again".
Application cannot be confirmed (`applied: "unknown"` — E-6/E-7).

## Hard contracts

- **Protocol sync**: every `CMD_*` in `protocol.py` has exactly one entry in
  the controller's `_HANDLERS` dict, added in the same commit. Additive
  commands keep `PROTOCOL_VERSION`; changing an existing command's
  semantics bumps it in both files.
- **SysEx budget**: one response ≤ ~600 bytes JSON. Unbounded lists must
  paginate with `start`/`next_start`; the server side walks pages via
  `connection.fetch_all_pages`.
- **Every write** goes through `safety.safe_write` or `safety.safe_write_group`
  (snapshot → `~/.flstudio-mcp/changelog.jsonl` → readback → rollback via
  `fl_rollback_last_change`). A new kind of state means a new scope in
  `safety.take_snapshot()` in the same change. `fl_set_dry_run(True)` must
  work for every new write tool.
- Tools live in `src/fl_studio_mcp/tools/`, named `fl_*`, with `register(mcp)`
  at the bottom and a docstring covering args + return shape.

## Checks (run before every commit)

```
ruff check .                     # lint (config in pyproject.toml)
pytest -q                        # unit tests (fake bridge; no FL needed)
python scripts/test_bridge.py    # protocol sanity (no FL needed)
```

Live checks (need FL Studio + controller loaded):
`FLSTUDIO_MCP_TRANSPORT=tcp python scripts/test_<name>.py` — start every
live session with `fl_ping`; if `build` ≠ the controller's marker, the user
must reload it (MIDI Settings → FLStudioMCP → Update). Transport: with
`FLSTUDIO_MCP_TRANSPORT=tcp` tools go through the daemon (port 9787);
without it the server opens MIDI SysEx directly. In-process calls:
`build_server()` + `await m.call_tool(name, args)`.

## Live testing rules

- After editing the controller: copy it to
  `Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/`, verify
  md5 matches, bump the `build` marker, ask the user to reload FL.
- Live write tests must restore state (rollback or explicit rewrite).
  Keep one known-good project state to return to.

## Where things are

- `src/fl_studio_mcp/safety.py` — rollback layer (read this before any write tool)
- `fl_controller/FLStudioMCP/device_FLStudioMCP.py` — FL-side handlers
- `docs/API_PROBE_26.md` — measured FL 26.1.7 API facts (sandbox, modules)
- `docs/E*_REPORT.md` — per-epic decisions and QA findings
- `evals/evals.json` — request → expected-tool scenarios
- `skills/flstudio-production/SKILL.md` — end-user agent skill
