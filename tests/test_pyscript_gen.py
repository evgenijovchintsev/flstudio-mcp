"""Per-note porta rendering (PR #18): 808 glides.

Backward compatibility contract: notes without porta (or porta=False)
render as plain 4-tuples; a truthy porta appends the 5th field.
"""
from __future__ import annotations

import re

from fl_studio_mcp.pyscript_gen import render_apply_script


def _notes(script: str):
    m = re.search(r"^NOTES = (.*)$", script, re.M)
    assert m, "script has no NOTES line"
    return eval(m.group(1))  # noqa: S307 - our own generated literal


def test_plain_notes_are_4_tuples():
    s = render_apply_script(
        [{"pitch": 60, "time_bars": 0, "length_bars": 1, "velocity": 0.8}])
    assert _notes(s) == [(60, 0.0, 1.0, 0.8)]


def test_porta_true_appends_fifth_field():
    s = render_apply_script(
        [{"pitch": 60, "time_bars": 0, "length_bars": 1, "velocity": 0.8,
          "porta": True}])
    assert _notes(s) == [(60, 0.0, 1.0, 0.8, True)]


def test_mixed_list():
    s = render_apply_script([
        {"pitch": 60, "time_bars": 0, "length_bars": 1, "velocity": 0.8},
        {"pitch": 62, "time_bars": 1, "length_bars": 1, "velocity": 0.8,
         "porta": True},
    ])
    assert _notes(s) == [(60, 0.0, 1.0, 0.8), (62, 1.0, 1.0, 0.8, True)]


def test_porta_false_is_dropped():
    s = render_apply_script(
        [{"pitch": 40, "time_bars": 2.5, "length_bars": 0.5, "velocity": 0.5,
          "porta": False}])
    assert _notes(s) == [(40, 2.5, 0.5, 0.5)]


def test_generated_script_uses_len_guard():
    """The pyscript runtime must tolerate both 4- and 5-tuples in one list."""
    s = render_apply_script(
        [{"pitch": 60, "time_bars": 0, "length_bars": 1, "velocity": 0.8,
          "porta": True}])
    assert "if len(item) > 4 and item[4]:" in s
    assert "n.porta = True" in s
