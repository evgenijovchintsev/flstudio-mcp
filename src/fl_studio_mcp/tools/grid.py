"""Channel Rack step-grid tools (E-4): deterministic drum drawing.

An alternative to the Piano Roll note bridge for kick/snare/hat: the agent
reads and paints step bits directly (channels.getGridBit / setGridBit).
steps_total comes from the current pattern's length (16th steps), never
hardcoded 16. Writes go through safe_write with a `channel_grid:N` snapshot
(bits + velocities) so set_bit / batch / clear are each ONE rollback step --
the restore rewrites the snapshotted bits at their snapshotted velocities
via the batch command.
"""
from __future__ import annotations

import json
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from .. import protocol, safety
from ..connection import get_bridge

# Agent-facing response budget (E-0 contract §2.2): merged get_grid replies
# stop before exceeding this, returning next_start so the agent paginates.
_LIST_BUDGET = 600
# FL's default step velocity for pattern-authored hits (~115 measured live):
# fallback for ON bits whose velocity is unreadable in the snapshot.
_DEFAULT_VEL = 115


def _restore_bits(channel, steps):
    """Rollback = rewrite snapshotted bits WITH their velocities.

    ON bits go back at the snapshot velocity (unreadable / <=0 falls back
    to FL's default 115 -- restoring with value=1 left hits silent);
    OFF bits are cleared with 0. Pairs ride the batch command, so a
    rollback is still ONE RPC.
    """
    def build(before):
        bits = before.get("grid_bits") or []
        vels = before.get("grid_velocities") or []
        pairs = []
        for s in steps:
            if not (0 <= s < len(bits)):
                continue
            if bits[s]:
                vel = vels[s] if s < len(vels) else None
                if not isinstance(vel, int) or isinstance(vel, bool) or vel <= 0:
                    vel = _DEFAULT_VEL
                pairs.append([s, vel])
            else:
                pairs.append([s, 0])
        return {"command": protocol.CMD_CHANNEL_SET_GRID_BITS,
                "params": {"channel": channel, "bits": pairs}}
    return build


def _envelope_bytes(bits, vels, assigned):
    """Compact-JSON size of the lists the tool returns (budget check)."""
    return len(json.dumps(
        {"grid_bits": bits, "grid_velocities": vels, "grid_assigned": assigned},
        separators=(",", ":")))


def _read_grid(bridge, channel, start, count):
    """Walk the 16-step RPC windows, merging bits/velocities/assigned.

    Stops before the merged lists exceed _LIST_BUDGET and reports
    next_start (start + steps returned) when more steps remain.
    """
    bits, vels, assigned = [], [], []
    cur, total = start, None
    while True:
        page = bridge.call(protocol.CMD_CHANNEL_GET_GRID,
                           {"channel": channel, "start": cur, "count": 16})
        total = page.get("steps_total", total)
        nbits = list(page.get("grid_bits") or [])
        nvels = list(page.get("grid_velocities") or [])
        nassn = list(page.get("grid_assigned") or [])
        if count is not None and len(bits) + len(nbits) > count:
            keep = max(0, count - len(bits))
            nbits, nvels, nassn = nbits[:keep], nvels[:keep], nassn[:keep]
        if (bits and nbits
                and _envelope_bytes(bits + nbits, vels + nvels,
                                    assigned + nassn) > _LIST_BUDGET):
            break                      # keep merged pages; resume via next_start
        bits.extend(nbits)
        vels.extend(nvels)
        assigned.extend(nassn)
        nxt = page.get("next_start")
        if (count is not None and len(bits) >= count) or nxt is None or int(nxt) <= cur:
            break
        cur = int(nxt)
    ns = start + len(bits)
    return {"channel": channel, "steps_total": total, "start": start,
            "next_start": ns if total is not None and ns < total else None,
            "grid_bits": bits, "grid_velocities": vels,
            "grid_assigned": assigned}


def register(mcp: FastMCP) -> None:
    _RO = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True}
    _WR = {"readOnlyHint": False, "destructiveHint": False,
           "idempotentHint": True, "openWorldHint": True}

    @mcp.tool(annotations={"title": "Read Channel Rack step grid", **_RO})
    def fl_channel_get_grid(
        channel: Annotated[int, Field(ge=0, description="Channel Rack index.")] = 0,
        start: Annotated[int, Field(ge=0, description="First step.")] = 0,
        count: Annotated[int | None,
                         Field(gt=0, le=64,
                               description="Max steps; omit for ALL steps "
                                           "from start.")] = None,
    ) -> dict:
        """Step grid of one channel: {channel, steps_total, grid_bits (0/1),
        grid_velocities (pVelocity 0..127 or null), grid_assigned,
        start, next_start}. steps_total = current pattern length in 16th
        steps (never hardcoded 16). Reads walk 16-step RPC windows and stop
        before the reply exceeds the 600-byte budget -- next_start says
        where to resume. One step = one16th note; 4-on-the-floor = steps
        0, 4, 8, 12 in a 16-step (one-bar) window."""
        return _read_grid(get_bridge(), channel,
                          max(0, start), count)

    @mcp.tool(annotations={"title": "Set one step bit (velocity)", **_WR})
    def fl_channel_set_grid_bit(
        channel: Annotated[int, Field(ge=0, description="Channel Rack index.")],
        step: Annotated[int, Field(ge=0, description="Step index (16ths).")],
        value: Annotated[int, Field(ge=0, le=127,
                                    description="0 = off; 1..127 = on with "
                                                "this velocity.")] = 100,
    ) -> dict:
        """Set one Channel Rack step: value 0 clears the bit, 1..127 turns
        it on with that velocity (velocity write is best-effort; the
        response's velocity_readback shows what FL holds). One rollback
        step: restores the previous bit state."""
        return safety.safe_write(
            get_bridge(), tool="channel_set_grid_bit",
            scope=f"channel_grid:{channel}",
            command=protocol.CMD_CHANNEL_SET_GRID_BIT,
            params={"channel": channel, "step": step, "value": value},
            build_restore=_restore_bits(channel, [step]))

    @mcp.tool(annotations={"title": "Batch-set step bits (one undo)", **_WR})
    def fl_channel_set_grid_bits(
        channel: Annotated[int, Field(ge=0, description="Channel Rack index.")],
        bits: Annotated[list[list[int]],
                        Field(description="[step, value] pairs, max 64; "
                              "value 0..127 (0 = off). e.g. "
                              "[[0,100],[4,100],[8,100],[12,100]].")],
    ) -> dict:
        """Draw several steps in ONE rollback step (single batched RPC, no
        pacing needed). Use for patterns like 4-on-the-floor. The response
        reports applied count + any per-step errors."""
        steps = [int(b[0]) for b in bits]
        return safety.safe_write(
            get_bridge(), tool="channel_set_grid_bits",
            scope=f"channel_grid:{channel}",
            command=protocol.CMD_CHANNEL_SET_GRID_BITS,
            params={"channel": channel,
                    "bits": [[int(b[0]), int(b[1])] for b in bits]},
            build_restore=_restore_bits(channel, steps))

    @mcp.tool(annotations={"title": "Clear a step range", **_WR})
    def fl_channel_clear_grid(
        channel: Annotated[int, Field(ge=0, description="Channel Rack index.")],
        start: Annotated[int, Field(ge=0, description="First step.")] = 0,
        count: Annotated[int, Field(gt=0, le=64, description="How many steps.")] = 16,
    ) -> dict:
        """Zero a range of steps (bits off; velocities are left as-is).
        One rollback step: bits that were on come back at their
        snapshotted velocity, off bits stay off."""
        return safety.safe_write(
            get_bridge(), tool="channel_clear_grid",
            scope=f"channel_grid:{channel}",
            command=protocol.CMD_CHANNEL_CLEAR_GRID,
            params={"channel": channel, "start": start, "count": count},
            build_restore=_restore_bits(
                channel, list(range(start, start + count))))
