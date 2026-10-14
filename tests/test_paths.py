"""paths.py (PR #10 + #15 combined): FL user-data discovery.

Pure filesystem tests -- tmp_path + monkeypatched home; no FL, no bridge.
Windows-only resolvers (registry / known-folder) degrade to None on macOS
and are covered by the non-win32 branch assertions.
"""
from __future__ import annotations

from pathlib import Path

from fl_studio_mcp import paths


def _mk_fl_tree(base: Path, versioned: bool = False) -> Path:
    name = "FL Studio 2026" if versioned else "FL Studio"
    root = base / name
    (root / "Settings" / "Piano roll scripts").mkdir(parents=True)
    (root / "Settings" / "Hardware").mkdir(parents=True)
    (root / "Presets" / "Plugin database" / "Installed").mkdir(parents=True)
    return root


def test_fl_data_roots_exact_and_versioned(tmp_path, monkeypatch):
    il = tmp_path / "Documents" / "Image-Line"
    _mk_fl_tree(il, versioned=False)
    _mk_fl_tree(il, versioned=True)
    monkeypatch.setattr(paths, "image_line_dir", lambda: il)
    roots = list(paths.fl_data_roots())
    # exact "FL Studio" first, then versioned newest-first
    assert roots[0].name == "FL Studio"
    assert [r.name for r in roots[1:]] == ["FL Studio 2026"]


def test_env_override_wins(tmp_path, monkeypatch):
    fake = tmp_path / "custom-scripts"
    fake.mkdir()
    monkeypatch.setenv(paths.ENV_PIANO_ROLL_SCRIPTS, str(fake))
    assert paths.find_piano_roll_scripts_dir() == str(fake)

    fake_settings = tmp_path / "custom-settings"
    fake_settings.mkdir()
    monkeypatch.setenv(paths.ENV_FL_SETTINGS, str(fake_settings))
    assert paths.find_fl_settings_dir() == str(fake_settings)


def test_piano_roll_scripts_discovered(tmp_path, monkeypatch):
    il = tmp_path / "Documents" / "Image-Line"
    root = _mk_fl_tree(il, versioned=True)  # only versioned
    monkeypatch.setattr(paths, "image_line_dir", lambda: il)
    monkeypatch.delenv(paths.ENV_PIANO_ROLL_SCRIPTS, raising=False)
    monkeypatch.delenv(paths.ENV_FL_SETTINGS, raising=False)
    found = paths.find_piano_roll_scripts_dir()
    assert found == str(root / "Settings" / "Piano roll scripts")


def test_piano_roll_scripts_fallback_when_absent(tmp_path, monkeypatch):
    """No FL tree at all -> standard path is returned so the caller can
    create it and fail loudly on write."""
    empty = tmp_path / "empty-IL"
    empty.mkdir()
    monkeypatch.setattr(paths, "image_line_dir", lambda: empty)
    monkeypatch.delenv(paths.ENV_PIANO_ROLL_SCRIPTS, raising=False)
    monkeypatch.delenv(paths.ENV_FL_SETTINGS, raising=False)
    found = Path(paths.find_piano_roll_scripts_dir())
    assert found.parts[-3:] == ("FL Studio", "Settings", "Piano roll scripts")
    # ends with the standard layout under the (empty) image-line dir
    assert str(found).startswith(str(empty))


def test_windows_resolvers_degrade_off_win32():
    """On non-Windows both Windows-only resolvers return None."""
    import sys
    if sys.platform == "win32":
        return
    assert paths._fl_shared_data() is None
    assert paths._known_documents() is None


def test_documents_dir_is_home_documents_on_mac(tmp_path, monkeypatch):
    import sys
    if sys.platform == "win32":
        return
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    paths.documents_dir.cache_clear()
    paths.image_line_dir.cache_clear()
    try:
        assert paths.documents_dir() == tmp_path / "Documents"
        assert paths.image_line_dir() == tmp_path / "Documents" / "Image-Line"
    finally:
        paths.documents_dir.cache_clear()
        paths.image_line_dir.cache_clear()
