"""Shared pytest fixtures."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from bhyve_mcp.client import BhyveSession


@pytest.fixture
def mock_device() -> dict[str, Any]:
    return {
        "id": "device-123",
        "name": "Front Yard",
        "type": "sprinkler_timer",
        "firmware_version": "1.2.3",
        "is_connected": True,
        "mac_address": "aabbccddeeff",
        "water_sense_mode": "auto",
        "zones": [
            {
                "station": 1,
                "name": "Zone 1",
                "smart_watering_enabled": True,
                "sprinkler_type": "spray",
            },
            {
                "station": 2,
                "name": "Zone 2",
                "smart_watering_enabled": False,
            },
        ],
        "status": {
            "mode": "auto",
            "next_start_time": "2026-06-28T06:00:00.000Z",
            "next_start_programs": ["A"],
            "rain_delay": 0,
            "watering_status": None,
        },
    }


@pytest.fixture
def mock_program() -> dict[str, Any]:
    return {
        "id": "prog-1",
        "device_id": "device-123",
        "name": "Program A",
        "enabled": True,
        "frequency": {"type": "days", "days": [1, 3, 5]},
        "start_times": ["06:00"],
        "budget": 100,
        "run_times": [{"station": 1, "run_time": 10}],
        "is_smart_program": False,
    }


@pytest.fixture
def mock_bhyve_client(mock_device: dict, mock_program: dict) -> MagicMock:
    client = MagicMock()

    async def _devices():
        return [mock_device]

    async def _timer_programs():
        return [mock_program]

    type(client).devices = property(lambda self: _devices())
    type(client).timer_programs = property(lambda self: _timer_programs())

    client.get_device = AsyncMock(return_value=mock_device)
    client.get_landscape = AsyncMock(return_value=None)
    client.get_device_history_page = AsyncMock(
        return_value=[
            {
                "started_at": "2026-06-27T06:00:00.000Z",
                "station": 1,
                "run_time": 10,
                "program_name": "Program A",
                "consumption_gallons": 12.5,
            }
        ]
    )
    client.send_message = AsyncMock()
    client.set_rain_delay = AsyncMock()
    client.update_program = AsyncMock()
    client.update_device = AsyncMock()
    client.login = AsyncMock(return_value=True)
    client.listen = MagicMock()
    client.stop = AsyncMock()
    client._token = "test-token"
    return client


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch, mock_bhyve_client: MagicMock) -> BhyveSession:
    monkeypatch.setenv("BHYVE_EMAIL", "test@example.com")
    monkeypatch.setenv("BHYVE_PASSWORD", "secret")

    bhyve_session = BhyveSession()

    async def fake_ensure(*, force_reauth: bool = False) -> MagicMock:
        return mock_bhyve_client

    monkeypatch.setattr(bhyve_session, "_ensure_client", fake_ensure)
    return bhyve_session
