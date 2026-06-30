"""MCP tool tests with mocked B-Hyve client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from bhyve_mcp.client import BhyveSession


@pytest.mark.asyncio
async def test_list_devices(session: BhyveSession) -> None:
    result = await session.list_devices()
    assert isinstance(result, list)
    assert result[0]["id"] == "device-123"
    assert result[0]["name"] == "Front Yard"


@pytest.mark.asyncio
async def test_get_device_status(session: BhyveSession) -> None:
    result = await session.get_device_status("device-123")
    assert result["device_id"] == "device-123"
    assert result["mode"] == "auto"


@pytest.mark.asyncio
async def test_get_zone_details(session: BhyveSession) -> None:
    result = await session.get_zone_details("device-123")
    assert len(result) == 2
    assert result[0]["station"] == 1


@pytest.mark.asyncio
async def test_get_programs(session: BhyveSession) -> None:
    result = await session.get_programs("device-123")
    assert len(result) == 1
    assert result[0]["name"] == "Program A"


@pytest.mark.asyncio
async def test_get_watering_history(session: BhyveSession) -> None:
    result = await session.get_watering_history("device-123")
    assert len(result) == 1
    assert result[0]["zone"] == 1


@pytest.mark.asyncio
async def test_start_watering(session: BhyveSession, mock_bhyve_client: MagicMock) -> None:
    result = await session.start_watering("device-123", zone=1, minutes=10)
    assert result["success"] is True
    mock_bhyve_client.send_message.assert_awaited_once()
    payload = mock_bhyve_client.send_message.await_args.args[0]
    assert payload["event"] == "change_mode"
    assert payload["stations"][0]["station"] == 1


@pytest.mark.asyncio
async def test_start_watering_safety_limit(session: BhyveSession) -> None:
    result = await session.start_watering("device-123", zone=1, minutes=45)
    assert result["success"] is False
    assert "30 minute" in result["error"]


@pytest.mark.asyncio
async def test_stop_watering(session: BhyveSession, mock_bhyve_client: MagicMock) -> None:
    result = await session.stop_watering("device-123")
    assert result["success"] is True
    payload = mock_bhyve_client.send_message.await_args.args[0]
    assert payload["stations"] == []


@pytest.mark.asyncio
async def test_enable_rain_delay(session: BhyveSession, mock_bhyve_client: MagicMock) -> None:
    result = await session.enable_rain_delay("device-123", hours=24)
    assert result["success"] is True
    mock_bhyve_client.set_rain_delay.assert_awaited_with("device-123", 24)


@pytest.mark.asyncio
async def test_disable_rain_delay(session: BhyveSession, mock_bhyve_client: MagicMock) -> None:
    result = await session.disable_rain_delay("device-123")
    assert result["success"] is True
    mock_bhyve_client.set_rain_delay.assert_awaited_with("device-123", 0)


@pytest.mark.asyncio
async def test_set_device_mode(session: BhyveSession, mock_bhyve_client: MagicMock) -> None:
    result = await session.set_device_mode("device-123", "off")
    assert result["success"] is True
    payload = mock_bhyve_client.send_message.await_args.args[0]
    assert payload["mode"] == "off"


@pytest.mark.asyncio
async def test_update_program(session: BhyveSession, mock_bhyve_client: MagicMock) -> None:
    result = await session.update_program(
        "device-123", "prog-1", start_times=["07:00"], budget=80
    )
    assert result["success"] is True
    mock_bhyve_client.update_program.assert_awaited_once()


@pytest.mark.asyncio
async def test_toggle_smart_watering(
    session: BhyveSession, mock_bhyve_client: MagicMock
) -> None:
    result = await session.toggle_smart_watering("device-123", zone=1, enabled=False)
    assert result["success"] is True
    mock_bhyve_client.update_device.assert_awaited_once()


@pytest.mark.asyncio
async def test_device_not_found(session: BhyveSession, mock_bhyve_client: MagicMock) -> None:
    from unittest.mock import AsyncMock

    mock_bhyve_client.get_device = AsyncMock(return_value=None)
    result = await session.get_device_status("missing")
    assert result["success"] is False
    assert "not found" in result["error"]


def test_mcp_tools_registered() -> None:
    from bhyve_mcp.server import mcp

    tools = mcp._tool_manager.list_tools()
    tool_names = {t.name for t in tools}
    expected = {
        "list_devices",
        "get_device_status",
        "get_zone_details",
        "get_programs",
        "get_watering_history",
        "start_watering",
        "stop_watering",
        "enable_rain_delay",
        "disable_rain_delay",
        "set_device_mode",
        "update_program",
        "toggle_smart_watering",
    }
    assert expected.issubset(tool_names)
