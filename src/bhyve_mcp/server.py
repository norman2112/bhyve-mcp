"""FastMCP server for Orbit B-Hyve irrigation control."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import get_session

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

mcp = FastMCP("bhyve-mcp")


def _to_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


# --- Read tools ---


@mcp.tool()
async def list_devices() -> str:
    """List all B-Hyve devices (controllers, hubs, hose timers, flood sensors) on the account.

    Returns device id, name, type, status, firmware, station count, battery, and connectivity.
    Use device IDs from this response with all other tools.
    """
    result = await get_session().list_devices()
    return _to_json(result)


@mcp.tool()
async def get_device_status(device_id: str) -> str:
    """Get current status of a specific device including watering state and rain delays.

    Args:
        device_id: Device ID from list_devices.
    """
    result = await get_session().get_device_status(device_id)
    return _to_json(result)


@mcp.tool()
async def get_zone_details(device_id: str) -> str:
    """Get detailed info for all zones on a device.

    Args:
        device_id: Device ID from list_devices.
    """
    result = await get_session().get_zone_details(device_id)
    return _to_json(result)


@mcp.tool()
async def get_programs(device_id: str) -> str:
    """List watering programs configured for a device.

    Args:
        device_id: Device ID from list_devices.
    """
    result = await get_session().get_programs(device_id)
    return _to_json(result)


@mcp.tool()
async def get_watering_history(
    device_id: str, page: int = 1, per_page: int = 10
) -> str:
    """Get recent watering history for a device.

    Args:
        device_id: Device ID from list_devices.
        page: Page number (default 1).
        per_page: Results per page (default 10).
    """
    result = await get_session().get_watering_history(device_id, page, per_page)
    return _to_json(result)


# --- Write tools ---


@mcp.tool()
async def start_watering(
    device_id: str,
    zone: int,
    minutes: int,
    allow_extended_runtime: bool = False,
) -> str:
    """Start watering a specific zone for a given duration.

    Safety: durations over 30 minutes require allow_extended_runtime=true.

    Args:
        device_id: Device ID from list_devices.
        zone: Zone/station number (1-indexed).
        minutes: Duration in minutes (1-120).
        allow_extended_runtime: Set true to allow watering longer than 30 minutes.
    """
    result = await get_session().start_watering(
        device_id, zone, minutes, allow_extended_runtime
    )
    return _to_json(result)


@mcp.tool()
async def stop_watering(device_id: str) -> str:
    """Stop all active watering on a device.

    Args:
        device_id: Device ID from list_devices.
    """
    result = await get_session().stop_watering(device_id)
    return _to_json(result)


@mcp.tool()
async def enable_rain_delay(device_id: str, hours: int) -> str:
    """Enable rain delay (pauses all scheduled watering).

    Args:
        device_id: Device ID from list_devices.
        hours: Hours to delay (1-168, max 7 days).
    """
    result = await get_session().enable_rain_delay(device_id, hours)
    return _to_json(result)


@mcp.tool()
async def disable_rain_delay(device_id: str) -> str:
    """Cancel an active rain delay.

    Args:
        device_id: Device ID from list_devices.
    """
    result = await get_session().disable_rain_delay(device_id)
    return _to_json(result)


@mcp.tool()
async def set_device_mode(device_id: str, mode: str) -> str:
    """Set device operating mode.

    Args:
        device_id: Device ID from list_devices.
        mode: Operating mode — "auto" or "off".
    """
    result = await get_session().set_device_mode(device_id, mode)
    return _to_json(result)


@mcp.tool()
async def update_program(
    device_id: str,
    program_id: str,
    start_times: list[str] | None = None,
    frequency: dict | None = None,
    budget: int | None = None,
) -> str:
    """Update an existing watering program's configuration.

    Programs must be created in the B-Hyve app first. Only modifies existing programs.

    Args:
        device_id: Device ID from list_devices.
        program_id: Program ID from get_programs.
        start_times: Watering start times in HH:MM format.
        frequency: Frequency config with type (days|interval), days [0-6], interval int.
        budget: Watering budget percentage (0-200, 100 = default).
    """
    result = await get_session().update_program(
        device_id, program_id, start_times, frequency, budget
    )
    return _to_json(result)


@mcp.tool()
async def toggle_smart_watering(device_id: str, zone: int, enabled: bool) -> str:
    """Enable or disable Smart Watering for a zone (device-wide water_sense_mode).

    Args:
        device_id: Device ID from list_devices.
        zone: Zone/station number.
        enabled: True to enable, false to disable.
    """
    result = await get_session().toggle_smart_watering(device_id, zone, enabled)
    return _to_json(result)


# --- Resources ---


@mcp.resource("bhyve://devices")
async def devices_resource() -> str:
    """Current snapshot of all devices and their status."""
    result = await get_session().list_devices()
    return _to_json(result)


@mcp.resource("bhyve://device/{device_id}/zones")
async def device_zones_resource(device_id: str) -> str:
    """Zone configuration for a specific device."""
    result = await get_session().get_zone_details(device_id)
    return _to_json(result)


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
