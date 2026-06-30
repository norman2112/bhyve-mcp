"""B-Hyve session management and high-level API wrapper."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from functools import wraps
from typing import Any, Callable, TypeVar

from aiohttp import ClientSession
from dotenv import load_dotenv

from .models import (
    ActionConfirmation,
    DeviceStatus,
    DeviceSummary,
    ErrorResponse,
    ProgramSummary,
    WateringEvent,
    ZoneDetail,
    format_iso_end_time,
)
from .pybhyve import BHyveClient
from .pybhyve.errors import AuthenticationError, BHyveError, RequestError
from .pybhyve.typings import BHyveTimerProgram

load_dotenv()

_LOGGER = logging.getLogger(__name__)

PROGRAM_UPDATE_KEYS = {
    "budget",
    "device_id",
    "enabled",
    "frequency",
    "id",
    "name",
    "program",
    "program_start_date",
    "run_times",
    "start_times",
}

T = TypeVar("T")


def _require_credentials() -> tuple[str, str]:
    email = os.getenv("BHYVE_EMAIL", "").strip()
    password = os.getenv("BHYVE_PASSWORD", "").strip()
    if not email or not password:
        raise ValueError(
            "BHYVE_EMAIL and BHYVE_PASSWORD environment variables are required"
        )
    return email, password


def handle_api_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap API calls with structured error handling."""

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except AuthenticationError as err:
            return ErrorResponse(
                error="Authentication failed. Check BHYVE_EMAIL and BHYVE_PASSWORD.",
                error_type="authentication_error",
            ).model_dump()
        except ValueError as err:
            return ErrorResponse(error=str(err), error_type="validation_error").model_dump()
        except RequestError as err:
            message = str(err)
            error_type = "request_error"
            if "Timeout" in message:
                error_type = "timeout_error"
            return ErrorResponse(error=message, error_type=error_type).model_dump()
        except BHyveError as err:
            return ErrorResponse(error=str(err), error_type="bhyve_error").model_dump()
        except Exception as err:
            _LOGGER.exception("Unexpected error in %s", func.__name__)
            return ErrorResponse(
                error=str(err), error_type="unexpected_error"
            ).model_dump()

    return wrapper


class BhyveSession:
    """Cached authenticated B-Hyve client for the MCP server lifetime."""

    def __init__(self) -> None:
        self._client: BHyveClient | None = None
        self._session: ClientSession | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws_started = False

    async def _noop_ws_callback(self, _data: dict) -> None:
        """Discard websocket events; REST polling is sufficient for MCP."""

    async def _ensure_client(self, *, force_reauth: bool = False) -> BHyveClient:
        email, password = _require_credentials()

        if self._session is None or self._session.closed:
            self._session = ClientSession()
            force_reauth = True

        if self._client is None or force_reauth:
            if self._client is not None:
                await self._client.stop()
            self._client = BHyveClient(email, password, self._session)
            self._ws_started = False

        if force_reauth or self._client._token is None:
            logged_in = await self._client.login()
            if not logged_in:
                raise AuthenticationError("Login failed")

        if not self._ws_started:
            if self._loop is None:
                self._loop = asyncio.get_running_loop()
            self._client.listen(self._loop, self._noop_ws_callback)
            self._ws_started = True
            await asyncio.sleep(0.5)

        return self._client

    async def _with_reauth(self, operation: Callable[[BHyveClient], Any]) -> Any:
        client = await self._ensure_client()
        try:
            return await operation(client)
        except AuthenticationError:
            client = await self._ensure_client(force_reauth=True)
            return await operation(client)

    @staticmethod
    def _summarize_device(device: dict) -> DeviceSummary:
        status = device.get("status") or {}
        battery = device.get("battery")
        battery_level = None
        if isinstance(battery, dict):
            battery_level = battery.get("percent") or battery.get("level")
        elif isinstance(battery, (int, float)):
            battery_level = float(battery)

        zones = device.get("zones") or []
        return DeviceSummary(
            id=device.get("id", ""),
            name=device.get("name") or "Unknown Device",
            type=device.get("type", "unknown"),
            status=status,
            firmware_version=device.get("firmware_version"),
            num_stations=len(zones) or device.get("num_stations"),
            battery_level=battery_level,
            last_connected_at=device.get("last_connected_at")
            or status.get("last_connected_at"),
            is_connected=device.get("is_connected"),
        )

    @handle_api_errors
    async def list_devices(self) -> list[dict]:
        async def op(client: BHyveClient) -> list[dict]:
            devices = await client.devices
            return [self._summarize_device(d).model_dump() for d in devices]

        return await self._with_reauth(op)

    @handle_api_errors
    async def get_device_status(self, device_id: str) -> dict:
        async def op(client: BHyveClient) -> dict:
            device = await client.get_device(device_id, force_update=True)
            if device is None:
                raise ValueError(f"Device not found: {device_id}")

            status = device.get("status") or {}
            watering_raw = status.get("watering_status")
            rain_delay_hours = status.get("rain_delay", 0)
            rain_delay = None
            if rain_delay_hours:
                rain_delay = {
                    "hours": rain_delay_hours,
                    "cause": status.get("rain_delay_cause"),
                    "weather_type": status.get("rain_delay_weather_type"),
                    "started_at": status.get("rain_delay_started_at"),
                }

            result = DeviceStatus(
                device_id=device_id,
                name=device.get("name") or "Unknown Device",
                watering_status=watering_raw,
                next_start_time=status.get("next_start_time"),
                next_start_programs=status.get("next_start_programs"),
                mode=status.get("mode") or status.get("run_mode"),
                rain_delay=rain_delay,
                is_connected=device.get("is_connected"),
            )
            return result.model_dump()

        return await self._with_reauth(op)

    @handle_api_errors
    async def get_zone_details(self, device_id: str) -> list[dict]:
        async def op(client: BHyveClient) -> list[dict]:
            device = await client.get_device(device_id, force_update=True)
            if device is None:
                raise ValueError(f"Device not found: {device_id}")

            status = device.get("status") or {}
            watering = status.get("watering_status") or {}
            current_station = watering.get("current_station")
            programs = await client.timer_programs
            device_programs = [p for p in programs if p.get("device_id") == device_id]

            zones_out: list[dict] = []
            for zone in device.get("zones") or []:
                station = zone.get("station")
                zone_programs = []
                for program in device_programs:
                    run_times = [
                        rt
                        for rt in program.get("run_times", [])
                        if str(rt.get("station")) == str(station)
                    ]
                    if run_times or program.get("is_smart_program"):
                        zone_programs.append(
                            {
                                "id": program.get("id"),
                                "name": program.get("name"),
                                "enabled": program.get("enabled"),
                                "is_smart_program": program.get("is_smart_program"),
                                "run_times": run_times,
                            }
                        )

                soil_moisture = None
                landscape = await client.get_landscape(device_id, str(station))
                if landscape:
                    soil_moisture = landscape.get("current_water_level")

                zones_out.append(
                    ZoneDetail(
                        station=station,
                        name=zone.get("name"),
                        smart_watering_enabled=zone.get("smart_watering_enabled"),
                        sprinkler_type=zone.get("sprinkler_type"),
                        image_url=zone.get("image_url"),
                        is_watering=str(current_station) == str(station),
                        last_watering_timestamp=zone.get("last_watering_timestamp"),
                        next_start_time=status.get("next_start_time"),
                        programs=zone_programs,
                        soil_moisture=soil_moisture,
                    ).model_dump()
                )
            return zones_out

        return await self._with_reauth(op)

    @handle_api_errors
    async def get_programs(self, device_id: str) -> list[dict]:
        async def op(client: BHyveClient) -> list[dict]:
            programs = await client.timer_programs
            result = []
            for program in programs:
                if program.get("device_id") != device_id:
                    continue
                result.append(
                    ProgramSummary(
                        id=program.get("id", ""),
                        name=program.get("name"),
                        enabled=bool(program.get("enabled")),
                        frequency=program.get("frequency"),
                        start_times=program.get("start_times") or [],
                        budget=program.get("budget"),
                        run_times=program.get("run_times") or [],
                        is_smart_program=bool(program.get("is_smart_program")),
                    ).model_dump()
                )
            return result

        return await self._with_reauth(op)

    @handle_api_errors
    async def get_watering_history(
        self, device_id: str, page: int = 1, per_page: int = 10
    ) -> list[dict]:
        async def op(client: BHyveClient) -> list[dict]:
            device = await client.get_device(device_id)
            if device is None:
                raise ValueError(f"Device not found: {device_id}")

            history = await client.get_device_history_page(
                device_id, page=page, per_page=per_page, force_update=True
            )
            events = history if isinstance(history, list) else history.get("items", history)
            if not isinstance(events, list):
                events = [history] if history else []

            results = []
            for event in events:
                if not isinstance(event, dict):
                    continue
                results.append(
                    WateringEvent(
                        timestamp=event.get("started_at") or event.get("timestamp"),
                        zone=event.get("station") or event.get("zone"),
                        duration=event.get("run_time") or event.get("duration"),
                        program=event.get("program_name") or event.get("program"),
                        water_usage=event.get("consumption_gallons")
                        or event.get("water_usage"),
                        raw=event,
                    ).model_dump()
                )
            return results

        return await self._with_reauth(op)

    @handle_api_errors
    async def start_watering(
        self,
        device_id: str,
        zone: int,
        minutes: int,
        allow_extended_runtime: bool = False,
    ) -> dict:
        if minutes < 1 or minutes > 120:
            raise ValueError("minutes must be between 1 and 120")
        if minutes > 30 and not allow_extended_runtime:
            raise ValueError(
                "Duration exceeds 30 minute safety limit. "
                "Set allow_extended_runtime=true to override."
            )

        async def op(client: BHyveClient) -> dict:
            device = await client.get_device(device_id, force_update=True)
            if device is None:
                raise ValueError(f"Device not found: {device_id}")
            if not device.get("is_connected", True):
                raise ValueError(f"Device offline: {device_id}")

            zone_name = str(zone)
            for z in device.get("zones") or []:
                if str(z.get("station")) == str(zone):
                    zone_name = z.get("name") or zone_name
                    break

            now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            await client.send_message(
                {
                    "event": "change_mode",
                    "mode": "manual",
                    "device_id": device_id,
                    "timestamp": now,
                    "stations": [{"station": zone, "run_time": minutes}],
                }
            )
            return ActionConfirmation(
                message=f"Started watering zone {zone_name} for {minutes} minutes",
                details={
                    "device_id": device_id,
                    "zone": zone,
                    "zone_name": zone_name,
                    "minutes": minutes,
                    "expected_end_time": format_iso_end_time(minutes),
                },
            ).model_dump()

        return await self._with_reauth(op)

    @handle_api_errors
    async def stop_watering(self, device_id: str) -> dict:
        async def op(client: BHyveClient) -> dict:
            device = await client.get_device(device_id)
            if device is None:
                raise ValueError(f"Device not found: {device_id}")

            now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            await client.send_message(
                {
                    "event": "change_mode",
                    "mode": "manual",
                    "device_id": device_id,
                    "timestamp": now,
                    "stations": [],
                }
            )
            return ActionConfirmation(
                message="Stop watering command sent",
                details={"device_id": device_id},
            ).model_dump()

        return await self._with_reauth(op)

    @handle_api_errors
    async def enable_rain_delay(self, device_id: str, hours: int) -> dict:
        if hours < 1 or hours > 168:
            raise ValueError("hours must be between 1 and 168")

        async def op(client: BHyveClient) -> dict:
            device = await client.get_device(device_id)
            if device is None:
                raise ValueError(f"Device not found: {device_id}")

            await client.set_rain_delay(device_id, hours)
            return ActionConfirmation(
                message=f"Rain delay enabled for {hours} hours",
                details={
                    "device_id": device_id,
                    "hours": hours,
                    "expected_end_time": format_iso_end_time(hours * 60),
                },
            ).model_dump()

        return await self._with_reauth(op)

    @handle_api_errors
    async def disable_rain_delay(self, device_id: str) -> dict:
        async def op(client: BHyveClient) -> dict:
            device = await client.get_device(device_id)
            if device is None:
                raise ValueError(f"Device not found: {device_id}")

            await client.set_rain_delay(device_id, 0)
            return ActionConfirmation(
                message="Rain delay disabled",
                details={"device_id": device_id},
            ).model_dump()

        return await self._with_reauth(op)

    @handle_api_errors
    async def set_device_mode(self, device_id: str, mode: str) -> dict:
        if mode not in ("auto", "off"):
            raise ValueError('mode must be "auto" or "off"')

        async def op(client: BHyveClient) -> dict:
            device = await client.get_device(device_id, force_update=True)
            if device is None:
                raise ValueError(f"Device not found: {device_id}")

            await client.send_message(
                {
                    "event": "change_mode",
                    "device_id": device_id,
                    "mode": mode,
                }
            )
            return ActionConfirmation(
                message=f"Device mode set to {mode}",
                details={"device_id": device_id, "mode": mode},
            ).model_dump()

        return await self._with_reauth(op)

    @handle_api_errors
    async def update_program(
        self,
        device_id: str,
        program_id: str,
        start_times: list[str] | None = None,
        frequency: dict | None = None,
        budget: int | None = None,
    ) -> dict:
        if start_times is None and frequency is None and budget is None:
            raise ValueError(
                "At least one of start_times, frequency, or budget must be provided"
            )
        if budget is not None and (budget < 0 or budget > 200):
            raise ValueError("budget must be between 0 and 200")

        async def op(client: BHyveClient) -> dict:
            programs = await client.timer_programs
            program = next((p for p in programs if p.get("id") == program_id), None)
            if program is None:
                raise ValueError(f"Program not found: {program_id}")
            if program.get("device_id") != device_id:
                raise ValueError(
                    f"Program {program_id} does not belong to device {device_id}"
                )
            if program.get("is_smart_program"):
                raise ValueError("Cannot update smart programs via API")

            update_payload = BHyveTimerProgram(
                {k: v for k, v in program.items() if k in PROGRAM_UPDATE_KEYS}
            )
            if start_times is not None:
                update_payload["start_times"] = start_times
            if frequency is not None:
                update_payload["frequency"] = frequency
            if budget is not None:
                update_payload["budget"] = budget

            await client.update_program(program_id, update_payload)
            return ActionConfirmation(
                message="Program updated",
                details={
                    "device_id": device_id,
                    "program_id": program_id,
                    "start_times": update_payload.get("start_times"),
                    "frequency": update_payload.get("frequency"),
                    "budget": update_payload.get("budget"),
                },
            ).model_dump()

        return await self._with_reauth(op)

    @handle_api_errors
    async def toggle_smart_watering(
        self, device_id: str, zone: int, enabled: bool
    ) -> dict:
        async def op(client: BHyveClient) -> dict:
            device = await client.get_device(device_id, force_update=True)
            if device is None:
                raise ValueError(f"Device not found: {device_id}")

            zone_exists = any(
                str(z.get("station")) == str(zone) for z in device.get("zones") or []
            )
            if not zone_exists:
                raise ValueError(f"Zone not found: {zone}")

            await client.update_device(
                {
                    "id": device_id,
                    "type": device.get("type"),
                    "mac_address": device.get("mac_address"),
                    "water_sense_mode": "auto" if enabled else "off",
                }
            )
            state = "enabled" if enabled else "disabled"
            return ActionConfirmation(
                message=f"Smart watering {state} for zone {zone}",
                details={
                    "device_id": device_id,
                    "zone": zone,
                    "enabled": enabled,
                    "note": "Smart watering is device-wide (water_sense_mode)",
                },
            ).model_dump()

        return await self._with_reauth(op)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.stop()
        if self._session is not None and not self._session.closed:
            await self._session.close()


_session = BhyveSession()


def get_session() -> BhyveSession:
    return _session
