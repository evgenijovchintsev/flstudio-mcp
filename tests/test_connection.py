"""Unit tests for fetch_all_pages (E-1/E-2 pagination contract)."""

from __future__ import annotations

from fl_studio_mcp.connection import fetch_all_pages


def test_single_page(fake_bridge):
    fake_bridge.replies["cmd"] = {"total": 3, "items": [1, 2, 3], "next_start": None}
    out = fetch_all_pages(fake_bridge, "cmd", "items")
    assert out == {"total": 3, "items": [1, 2, 3]}
    assert len(fake_bridge.calls) == 1


def test_multi_page_concat(fake_bridge):
    fake_bridge.replies["cmd"] = [
        {"total": 5, "items": [1, 2], "next_start": 2},
        {"total": 5, "items": [3, 4], "next_start": 4},
        {"total": 5, "items": [5], "next_start": None},
    ]
    out = fetch_all_pages(fake_bridge, "cmd", "items")
    assert out["items"] == [1, 2, 3, 4, 5]
    assert [p["start"] for _c, p in fake_bridge.calls] == [0, 2, 4]


def test_no_forward_progress_stops(fake_bridge):
    # A buggy next_start equal to start must not loop forever.
    fake_bridge.replies["cmd"] = {"total": 2, "items": [1], "next_start": 0}
    out = fetch_all_pages(fake_bridge, "cmd", "items")
    assert out["items"] == [1]
    assert len(fake_bridge.calls) == 1


def test_max_pages_cap():
    # Every page claims more data; the cap must bound the loop.
    class _Infinite:
        def __init__(self):
            self.n = 0
            self.calls = []

        def call(self, command, params=None):
            self.n += 1
            self.calls.append((command, dict(params or {})))
            return {"total": 999, "items": [self.n], "next_start": self.n}

    b = _Infinite()
    out = fetch_all_pages(b, "cmd", "items", max_pages=3)
    assert out["items"] == [1, 2, 3]
    assert len(b.calls) == 3
