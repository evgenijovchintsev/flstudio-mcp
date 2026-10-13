"""Piano-roll note authoring -- the generate-script bridge.

FL's pyscript sandbox blocks file I/O (read AND write), so we can't pass note
data via a job file. Instead we GENERATE a .pyscript with the notes baked in
(pyscript_gen), write it into FL's Piano roll scripts folder, then force-focus
FL and fire the platform "Run last script again" shortcut
(Ctrl+Alt+Y on Windows, Cmd+Opt+Y on macOS). FL re-reads the file on that
hotkey, so the fresh notes apply with no manual click.

This runs in a process that can write files + send keystrokes (the daemon, or
a normally-launched MCP server). Under the Store/MSIX Claude Desktop the MCP
server can't, so it delegates here via the daemon's "apply_notes" op.

One-time setup the user must do: run MCP_Apply once from the piano-roll
Scripting menu so it becomes FL's "last script".
"""

from __future__ import annotations

from .pyscript_gen import write_apply_script, write_quantize_script


def apply_notes(notes, mode="replace", trigger=True, quantize=None, snap_ends=False):
    """Write a pyscript into MCP_Apply.pyscript and (optionally) trigger FL.

    Normally writes the given notes. If ``quantize`` (grid in bars) is set, writes
    a script that instead reads the score and snaps existing notes to that grid.

    ``applied`` in the result is the honest note-application status (E-6):
    - ``"unknown"``: the Piano-roll pyscript sandbox blocks file I/O and the
      controller cannot import flpianoroll, so there is NO channel to read
      the score back programmatically (proved in E-0 Q2 + E-6 probe).
      ``triggered: true`` only means the hotkey was sent -- it does NOT mean
      notes appeared. Verify visually (open the Piano roll) or re-read with a
      screenshot tool; ``fl_piano_get_notes`` will close this loop when E-7
      lands.
    ``triggered``/``focused``/``method`` describe the auto-trigger only.

    Returns {ok, ..., script, triggered, focused, focus_ok?, method?, applied, hint?}.
    """
    if quantize is not None:
        path = write_quantize_script(float(quantize), snap_ends)
        result = {"ok": True, "action": "quantize", "grid_bars": float(quantize),
                  "snap_ends": bool(snap_ends), "script": path}
    else:
        path = write_apply_script(notes, mode)
        result = {"ok": True, "count": len(notes), "script": path, "mode": mode}

    if not trigger:
        result["triggered"] = False
        result["applied"] = "unknown"
        result["hint"] = (
            "Script written but NOT triggered. Run 'MCP Apply' once from the "
            "Piano roll Scripting menu (or press the run-last-script "
            "shortcut) to apply the notes."
        )
        return result

    try:
        from .pyscript_trigger import trigger_run_last_script
        trig = trigger_run_last_script()
        shortcut = trig.get("shortcut", "Ctrl+Alt+Y")
        result["triggered"] = bool(trig.get("sent_hotkey", True))
        result["focused"] = trig.get("focused", False)
        if "focus_ok" in trig:
            result["focus_ok"] = trig["focus_ok"]
        if "method" in trig:
            result["method"] = trig["method"]
        if trig.get("error"):
            result["error"] = trig["error"]
        # The trigger can't confirm the script actually ran (E-6: sandbox
        # blocks file receipts; controller cannot import flpianoroll -- both
        # proved). applied stays honest "unknown"; the one manual step that
        # breaks auto-trigger is the one-time arm.
        result["applied"] = "unknown"
        result["setup"] = (
            "Notes were written to the script file and the hotkey was sent, "
            "but there is NO programmatic confirmation channel (proved E-0/E-6): "
            "applied is 'unknown' until you see the notes in the Piano roll. "
            "If notes did not appear: run 'MCP Apply' ONCE from the Piano roll "
            "Scripting menu this FL session (arms 'Run last script again'; "
            "no FL API exists to automate that -- ui.runScript is absent)."
        )
        if not result["triggered"]:
            result["hint"] = (
                "Notes written but auto-trigger is unsupported here. Click "
                f"the FL Piano roll and press {shortcut} to apply."
            )
        elif not result.get("focused"):
            result["hint"] = (
                "Could not focus FL automatically -- click the FL Piano Roll "
                f"and press {shortcut}."
            )
    except Exception as e:
        # Script is written regardless; trigger is best-effort.
        result["triggered"] = False
        result["applied"] = "unknown"
        result["error"] = f"{type(e).__name__}: {e}"
        result["hint"] = (
            f"Notes written but auto-trigger failed ({e}). Click the FL Piano "
            "roll and press the run-last-script shortcut to apply."
        )
    return result
