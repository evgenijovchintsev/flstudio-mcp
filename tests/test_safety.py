"""Unit tests for the safety layer: dry-run, changelog, rollback, scopes."""

from __future__ import annotations

import pytest

from fl_studio_mcp import protocol, safety


def test_dry_run_plans_without_touching_bridge(fake_bridge, changelog):
    safety.set_dry_run(True)
    try:
        res = safety.safe_write(
            fake_bridge, tool="t", scope="mixer_track:1",
            command=protocol.CMD_MIXER_SET_VOLUME,
            params={"track": 1, "value": 0.5},
            build_restore=lambda before: {"command": protocol.CMD_MIXER_SET_VOLUME,
                                          "params": {"track": 1, "value": before["vol_norm"]}},
        )
    finally:
        safety.set_dry_run(False)
    assert res["ok"] and res["dry_run"] is True
    assert res["planned"]["command"] == protocol.CMD_MIXER_SET_VOLUME
    assert fake_bridge.calls == []            # nothing executed
    assert changelog.recent() == []           # nothing logged


def test_safe_write_logs_one_entry_with_before_after(fake_bridge, changelog):
    fake_bridge.replies[protocol.CMD_MIXER_GET_TRACK] = {"index": 1, "vol_norm": 0.8}
    fake_bridge.replies[protocol.CMD_MIXER_SET_VOLUME] = {"ok": True}
    res = safety.safe_write(
        fake_bridge, tool="set_volume", scope="mixer_track:1",
        command=protocol.CMD_MIXER_SET_VOLUME,
        params={"track": 1, "value": 0.5},
        build_restore=lambda before: {"command": protocol.CMD_MIXER_SET_VOLUME,
                                      "params": {"track": 1, "value": before["vol_norm"]}},
    )
    assert res["ok"] is True
    assert res["before"]["vol_norm"] == 0.8
    entries = changelog.recent()
    assert len(entries) == 1
    e = entries[0]
    assert e["tool"] == "set_volume" and e["scope"] == "mixer_track:1"
    assert e["restore"]["params"]["value"] == 0.8


def test_safe_write_rejected_write_raises_and_logs_nothing(fake_bridge, changelog):
    fake_bridge.replies[protocol.CMD_MIXER_GET_TRACK] = {"index": 1, "vol_norm": 0.8}
    fake_bridge.replies[protocol.CMD_MIXER_SET_VOLUME] = {"ok": False, "error": "bad"}
    with pytest.raises(ValueError, match="rejected"):
        safety.safe_write(
            fake_bridge, tool="set_volume", scope="mixer_track:1",
            command=protocol.CMD_MIXER_SET_VOLUME,
            params={"track": 1, "value": 0.5},
            build_restore=lambda before: {"command": protocol.CMD_MIXER_SET_VOLUME,
                                          "params": {"track": 1}},
        )
    assert changelog.recent() == []


def test_rollback_replays_restore(fake_bridge, changelog):
    fake_bridge.replies[protocol.CMD_MIXER_GET_TRACK] = {"index": 1, "vol_norm": 0.8}
    fake_bridge.replies[protocol.CMD_MIXER_SET_VOLUME] = {"ok": True}
    safety.safe_write(
        fake_bridge, tool="set_volume", scope="mixer_track:1",
        command=protocol.CMD_MIXER_SET_VOLUME,
        params={"track": 1, "value": 0.5},
        build_restore=lambda before: {"command": protocol.CMD_MIXER_SET_VOLUME,
                                      "params": {"track": 1, "value": before["vol_norm"]}},
    )
    out = safety.rollback_last_change(fake_bridge)
    assert out["ok"] is True and out["rolled_back"] == "set_volume"
    # the restore write went through the bridge with the SNAPSHOT value
    restore_calls = [p for c, p in fake_bridge.calls
                     if c == protocol.CMD_MIXER_SET_VOLUME and p.get("value") == 0.8]
    assert restore_calls
    assert changelog.recent() == []           # entry consumed


def test_rollback_empty_changelog(fake_bridge, changelog):
    out = safety.rollback_last_change(fake_bridge)
    assert out["ok"] is False and "empty" in out["error"]


def test_group_is_one_rollback_unit(fake_bridge, changelog):
    fake_bridge.replies[protocol.CMD_PLUGIN_GET_PARAM] = {"i": 0, "name": "Gain", "v": 0.5}
    fake_bridge.replies[protocol.CMD_PLUGIN_SET_PARAM] = {"ok": True}
    writes = [{
        "snap_scope": "plugin_param:1:0:%d" % i,
        "command": protocol.CMD_PLUGIN_SET_PARAM,
        "params": {"track": 1, "slot": 0, "param": i, "value": 0.9},
        "restore": (lambda before, i=i: {"command": protocol.CMD_PLUGIN_SET_PARAM,
                                         "params": {"track": 1, "slot": 0, "param": i,
                                                    "value": before["v"]}}),
    } for i in (3, 5)]
    res = safety.safe_write_group(
        fake_bridge, tool="plugin_set_params", scope="plugin_params:1:0",
        writes=writes, verify_values=None)
    assert res["ok"] is True
    entries = changelog.recent()
    assert len(entries) == 1 and entries[0]["group"] is True
    assert len(entries[0]["restores"]) == 2
    # ONE rollback reverts both params
    out = safety.rollback_last_change(fake_bridge)
    assert out["ok"] is True and len(out["restored"]) == 2


def test_snapshot_scopes_dispatch(fake_bridge, changelog):
    fake_bridge.replies[protocol.CMD_MIXER_GET_TRACK] = {"index": 2}
    fake_bridge.replies[protocol.CMD_CHANNEL_GET] = {"index": 3}
    fake_bridge.replies[protocol.CMD_PLUGIN_GET_PARAM] = {"i": 7}
    fake_bridge.replies[protocol.CMD_MIXER_GET_ROUTING] = {"routes_to": [{"dst": 4}]}
    fake_bridge.replies[protocol.CMD_PATTERN_GET_LENGTH] = {"index": 1, "beats": 16}

    assert safety.take_snapshot(fake_bridge, "mixer_track:2")["index"] == 2
    assert safety.take_snapshot(fake_bridge, "channel:3")["index"] == 3
    assert safety.take_snapshot(fake_bridge, "plugin_param:1:0:7")["i"] == 7
    route = safety.take_snapshot(fake_bridge, "route:1:4")
    assert route == {"src": 1, "dst": 4, "enabled": True}
    assert safety.take_snapshot(fake_bridge, "pattern:1")["beats"] == 16
    with pytest.raises(ValueError, match="unknown snapshot scope"):
        safety.take_snapshot(fake_bridge, "bogus:1")


def test_channel_grid_snapshot_walks_pages(fake_bridge, changelog):
    fake_bridge.replies[protocol.CMD_CHANNEL_GET_GRID] = [
        {"steps_total": 32, "grid_bits": [1, 0] * 8,
         "grid_velocities": [100] * 16, "next_start": 16},
        {"steps_total": 32, "grid_bits": [0, 1] * 8,
         "grid_velocities": [90] * 16, "next_start": None},
    ]
    snap = safety.take_snapshot(fake_bridge, "channel_grid:0")
    assert snap["steps_total"] == 32
    assert len(snap["grid_bits"]) == 32 and len(snap["grid_velocities"]) == 32
    assert snap["grid_velocities"][:2] == [100, 100]
