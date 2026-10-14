"""Virtual-port opt-in parsing (PR #11): FLSTUDIO_MCP_VIRTUAL_PORTS env.

Pure env-parsing tests -- no MIDI, no bridge open.
"""
from __future__ import annotations

from fl_studio_mcp import connection


def _fresh(monkeypatch, value, platform="linux"):
    if value is None:
        monkeypatch.delenv("FLSTUDIO_MCP_VIRTUAL_PORTS", raising=False)
    else:
        monkeypatch.setenv("FLSTUDIO_MCP_VIRTUAL_PORTS", value)
    monkeypatch.setattr(connection.sys, "platform", platform)
    return connection._virtual_ports_enabled()


def test_forced_on(monkeypatch):
    for v in ("1", "true", "on", "yes", "TRUE"):
        assert _fresh(monkeypatch, v) is True, v


def test_forced_off(monkeypatch):
    for v in ("0", "false", "off", "no"):
        assert _fresh(monkeypatch, v) is False, v


def test_auto_on_for_macos_linux(monkeypatch):
    assert _fresh(monkeypatch, None, "darwin") is True
    assert _fresh(monkeypatch, "auto", "linux") is True


def test_auto_off_for_windows(monkeypatch):
    """Windows MME cannot create virtual ports -- loopMIDI is still required."""
    assert _fresh(monkeypatch, None, "win32") is False
    assert _fresh(monkeypatch, "auto", "win32") is False
