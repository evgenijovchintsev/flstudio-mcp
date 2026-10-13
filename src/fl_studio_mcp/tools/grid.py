"""Channel Rack step-grid tools (E-4): deterministic drum drawing.

An alternative to the Piano Roll note bridge for kick/snare/hat: the agent
reads and paints step bits directly (channels.getGridBit / setGridBit).
steps_total comes from the current pattern's length (16th steps), never
hardcoded 16. Writes go through safe_write with a `channel_grid:N` snapshot
(whole bit grid) so set_bit / batch / clear are each ONE rollback step --
the restore rewrites the snapshotted bits via the batch command.
"""
from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from .. import protocol, safety
from ..connection import get_bridge


def _restore_bits(channel, steps):
    """Rollback = rewrite the snapshotted 0/1 for exactly the touched steps."""
    def build(before):
        bits = before.get("grid_bits") or []
        pairs = [[s, bits[s]] for s in steps if 0 <= s < len(bits)]
        return {"command": protocol.CMD_CHANNEL_SET_GRID_BITS,
                "params": {"channel": channel, "bits": pairs}}
    return build


def _read_grid(bridge, channel, start, count):
    """Walk the 16-step RPC windows, merging bits/velocities/assigned."""
    bits, vels, assigned = [], [], []
    cur, total = start, None
    while True:
        page = bridge.call(protocol.CMD_CHANNEL_GET_GRID,
                           {"channel": channel, "start": cur, "count": 16})
        total = page.get("steps_total", total)
        bits.extend(page.get("grid_bits") or [])
        vels.extend(page.get("grid_velocities") or [])
        assigned.extend(page.get("grid_assigned") or [])
        if count is not None and len(bits) >= count:
            bits[:] = bits[:count]
            vels[:] = vels[:count]
            assigned[:] = assigned[:count]
            break
        nxt = page.get("next_start")
        if nxt is None or int(nxt) <= cur:
            break
        cur = int(nxt)
    return {"channel": channel, "steps_total": total, "start": start,
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
        grid_velocities (pVelocity 0..127 or null), grid_assigned}.
        steps_total = current pattern length in 16th steps (never
        hardcoded 16). One step = one16th note; 4-on-the-floor = steps
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
        One rollback step: restores the bits that were on."""
        return safety.safe_write(
            get_bridge(), tool="channel_clear_grid",
            scope=f"channel_grid:{channel}",
            command=protocol.CMD_CHANNEL_CLEAR_GRID,
            params={"channel": channel, "start": start, "count": count},
            build_restore=_restore_bits(
                channel, list(range(start, start + count))))
