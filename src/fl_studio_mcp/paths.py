"""Cross-platform discovery of FL Studio user-data locations.

FL Studio uses the SAME on-disk layout on Windows and macOS:

    <home>/Documents/Image-Line/FL Studio[ NNNN]/
        Settings/Hardware/FLStudioMCP/          # controller script
        Settings/Piano roll scripts/            # note-bridge pyscript
        Presets/Plugin database/Installed/       # scanned plugin shortcuts
        Presets/                                 # channel/mixer/plugin presets

so a single discovery routine serves every platform. Each lookup takes an
explicit env override first (so unusual installs always work), then the
standard path, then any versioned "FL Studio NNNN" folder, newest first.

On Windows the Documents root itself is resolved properly: first from FL's
own registry record (``HKCU\\Software\\Image-Line\\Shared\\Paths``), which
follows a Documents folder redirected to OneDrive or renamed by the OS
language, then the shell's known-folder API, then the naive home path.
macOS just uses ``~/Documents``.

Pure filesystem / registry reads -- no FL, no bridge -- so this is easy to
unit-test.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

# Env overrides (each points directly at the target folder).
ENV_PIANO_ROLL_SCRIPTS = "FLSTUDIO_MCP_PIANO_ROLL_SCRIPTS"
ENV_FL_SETTINGS = "FLSTUDIO_MCP_FL_SETTINGS"


def _fl_shared_data() -> Path | None:
    """FL's 'Shared data' root, e.g. <Documents>/Image-Line (Windows only)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Image-Line\Shared\Paths") as k:
            value, _ = winreg.QueryValueEx(k, "Shared data")
    except OSError:
        return None
    p = Path(value)
    return p if p.is_dir() else None


def _known_documents() -> Path | None:
    """FOLDERID_Documents via SHGetKnownFolderPath (Windows only)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
        fid = GUID(
            0xFDD39AD0, 0x238F, 0x46AF,
            (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
        )
        out = ctypes.c_wchar_p()
        try:
            hr = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(fid), 0, None, ctypes.byref(out))
            value = out.value if hr == 0 else None
        finally:
            # the caller owns the buffer, even when the call fails
            ctypes.windll.ole32.CoTaskMemFree(out)
        if not value:
            return None
        path = Path(value)
        return path if path.is_dir() else None
    except Exception:
        return None


@lru_cache(maxsize=1)
def documents_dir() -> Path:
    """The user's real Documents folder (registry/known-folder aware on
    Windows, ``~/Documents`` elsewhere)."""
    return _known_documents() or Path.home() / "Documents"


@lru_cache(maxsize=1)
def image_line_dir() -> Path:
    """<Documents>/Image-Line, honouring FL's own registry record first."""
    return _fl_shared_data() or documents_dir() / "Image-Line"


def fl_data_roots() -> Iterator[Path]:
    """Yield candidate FL Studio user-data roots, newest version first.

    Handles both the unversioned ``FL Studio`` folder and versioned
    ``FL Studio 2025`` style folders, under the resolved Image-Line dir
    (registry-aware on Windows) and a bare ~/Image-Line fallback.
    """
    for base in (image_line_dir(), Path.home() / "Image-Line"):
        if not base.is_dir():
            continue
        # exact "FL Studio" first, then versioned folders newest-first
        exact = base / "FL Studio"
        if exact.is_dir():
            yield exact
        for fl in sorted(base.glob("FL Studio *"), reverse=True):
            if fl.is_dir():
                yield fl


def find_fl_settings_dir() -> str | None:
    """Locate FL's ``Settings`` folder (env override wins). Returns a str path
    or None if not found."""
    env = os.environ.get(ENV_FL_SETTINGS)
    if env and os.path.isdir(env):
        return env
    for root in fl_data_roots():
        settings = root / "Settings"
        if settings.is_dir():
            return str(settings)
    return None


def find_piano_roll_scripts_dir() -> str:
    """Locate FL's ``Piano roll scripts`` folder.

    Order: env override -> discovered ``Settings/Piano roll scripts`` ->
    the standard path (returned even if absent, so callers can create it and
    fail loudly on write rather than silently pick the wrong place).
    """
    env = os.environ.get(ENV_PIANO_ROLL_SCRIPTS)
    if env:
        return env
    settings = find_fl_settings_dir()
    if settings:
        cand = Path(settings) / "Piano roll scripts"
        if cand.is_dir():
            return str(cand)
    standard = image_line_dir() / "FL Studio" / "Settings" / "Piano roll scripts"
    # If a versioned root exists but the unversioned one doesn't, prefer it.
    if not standard.is_dir():
        for root in fl_data_roots():
            cand = root / "Settings" / "Piano roll scripts"
            return str(cand)
    return str(standard)
