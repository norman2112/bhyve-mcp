"""Pydantic models for B-Hyve MCP tool responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DeviceSummary(BaseModel):
    id: str
    name: str
    type: str
    status: dict[str, Any] = Field(default_factory=dict)
    firmware_version: str | None = None
    num_stations: int | None = None
    battery_level: float | None = None
    last_connected_at: str | None = None
    is_connected: bool | None = None


class WateringStatus(BaseModel):
    current_station: str | int | None = None
    started_watering_station_at: str | None = None
    program: str | None = None
    stations: list[dict[str, Any]] | None = None


class DeviceStatus(BaseModel):
    device_id: str
    name: str
    watering_status: WateringStatus | None = None
    next_start_time: str | None = None
    next_start_programs: list[Any] | None = None
    mode: str | None = None
    rain_delay: dict[str, Any] | None = None
    is_connected: bool | None = None


class ZoneDetail(BaseModel):
    station: str | int
    name: str | None = None
    smart_watering_enabled: bool | None = None
    sprinkler_type: str | None = None
    image_url: str | None = None
    is_watering: bool = False
    last_watering_timestamp: str | None = None
    next_start_time: str | None = None
    programs: list[dict[str, Any]] = Field(default_factory=list)
    soil_moisture: float | None = None


class ProgramSummary(BaseModel):
    id: str
    name: str | None = None
    enabled: bool = False
    frequency: dict[str, Any] | list[Any] | None = None
    start_times: list[str] = Field(default_factory=list)
    budget: int | None = None
    run_times: list[dict[str, Any]] = Field(default_factory=list)
    is_smart_program: bool = False


class WateringEvent(BaseModel):
    timestamp: str | None = None
    zone: str | int | None = None
    duration: float | None = None
    program: str | None = None
    water_usage: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ActionConfirmation(BaseModel):
    success: bool = True
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_type: str


def format_iso_end_time(minutes: int) -> str:
    """Return an ISO timestamp for when watering should end."""
    end = datetime.utcnow().timestamp() + (minutes * 60)
    return datetime.utcfromtimestamp(end).strftime("%Y-%m-%dT%H:%M:%SZ")
