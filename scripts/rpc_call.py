#!/usr/bin/env python3
"""Sized RPC call against the local fl-studio-mcp daemon.

Prints the response plus the exact JSON byte size of the reply payload, so
budget regressions (SysEx drops >1000 B silently) are visible while probing.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("FLSTUDIO_MCP_TRANSPORT", "tcp")
from fl_studio_mcp.connection import get_bridge  # noqa: E402


def main():
    cmd = sys.argv[1]
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    bridge = get_bridge()
    bridge.open()
    resp = bridge.call(cmd, params)
    text = json.dumps(resp, ensure_ascii=False)
    print(text)
    print(f"--- payload bytes: {len(text.encode('utf-8'))} ---", file=sys.stderr)


if __name__ == "__main__":
    main()
