# bhyve-mcp: Orbit B-Hyve MCP Server

## Project Summary

Build an MCP (Model Context Protocol) server that wraps the Orbit B-Hyve irrigation API, enabling Claude Code, Cursor, and any MCP-compatible client to query and control B-Hyve sprinkler systems via natural language.

No existing MCP server for B-Hyve exists. This is a greenfield build.

---

## Architecture

```
Claude Code / Cursor
        │
        │ stdio (JSON-RPC 2.0)
        ▼
  ┌─────────────┐
  │  bhyve-mcp   │  ← FastMCP Python server
  │  (FastMCP)   │
  └──────┬──────┘
         │
         │ aiohttp
         ▼
  ┌──────────────────┐
  │ Orbit B-Hyve API  │  ← REST (HTTPS) + WebSocket
  │ api.orbitbhyve.com │
  └──────────────────┘
```

- **Transport**: stdio (default for Claude Code / Cursor local MCP servers)
- **Framework**: `FastMCP` from the official `mcp` Python SDK (v1.27+)
- **B-Hyve client**: `pybhyve` library (asyncio, aiohttp-based)
- **Auth**: Orbit account email/password via environment variables

---

## Dependencies

```
mcp>=1.27.0
pybhyve
aiohttp
python-dotenv
```

**Python**: 3.10+  
**Package manager**: `uv` (preferred) or `pip`

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BHYVE_EMAIL` | Yes | Orbit B-Hyve account email |
| `BHYVE_PASSWORD` | Yes | Orbit B-Hyve account password |

Load from `.env` file via `python-dotenv`. Never hardcode credentials.

---

## MCP Tools

### Read Tools (No Side Effects)

#### `list_devices`
- **Description**: List all B-Hyve devices (controllers, hubs, hose timers, flood sensors) on the account
- **Parameters**: None
- **Returns**: JSON array of devices with id, name, type, status, firmware_version, num_stations, battery level (if applicable), last_connected_at, wifi/connection status
- **Notes**: This is the entry point — device IDs from this response are used by all other tools

#### `get_device_status`
- **Description**: Get current status of a specific device including watering state, next scheduled run, and any active rain delays
- **Parameters**:
  - `device_id` (string, required): Device ID from `list_devices`
- **Returns**: JSON object with watering_status (null or active zone info), next_start_time, next_start_programs, mode (auto/off), rain_delay info

#### `get_zone_details`
- **Description**: Get detailed info for all zones on a device
- **Parameters**:
  - `device_id` (string, required): Device ID
- **Returns**: JSON array of zones with station number, name, smart_watering_enabled, sprinkler_type, image_url, is_watering, last_watering_timestamp, next_start_time, program details, soil moisture (if available)

#### `get_programs`
- **Description**: List watering programs configured for a device
- **Parameters**:
  - `device_id` (string, required): Device ID
- **Returns**: JSON array of programs with id, name, enabled status, frequency config (days/interval), start_times, budget percentage, zone run times

#### `get_watering_history`
- **Description**: Get recent watering history for a device
- **Parameters**:
  - `device_id` (string, required): Device ID
  - `page` (int, optional, default 1): Page number
  - `per_page` (int, optional, default 10): Results per page
- **Returns**: JSON array of watering events with timestamp, zone, duration, program, water usage (if reported)

### Write Tools (Side Effects — Require Confirmation Pattern)

#### `start_watering`
- **Description**: Start watering a specific zone for a given duration
- **Parameters**:
  - `device_id` (string, required): Device ID
  - `zone` (int, required): Zone/station number (1-indexed)
  - `minutes` (int, required, min 1, max 120): Duration in minutes
- **Returns**: Confirmation with zone name, duration, and expected end time
- **Safety**: Default max 30 minutes. Require explicit override for >30.

#### `stop_watering`
- **Description**: Stop all active watering on a device
- **Parameters**:
  - `device_id` (string, required): Device ID
- **Returns**: Confirmation of stop command

#### `enable_rain_delay`
- **Description**: Enable rain delay (pauses all scheduled watering)
- **Parameters**:
  - `device_id` (string, required): Device ID
  - `hours` (int, required, min 1, max 168): Hours to delay (max 7 days)
- **Returns**: Confirmation with delay end time

#### `disable_rain_delay`
- **Description**: Cancel an active rain delay
- **Parameters**:
  - `device_id` (string, required): Device ID
- **Returns**: Confirmation

#### `set_device_mode`
- **Description**: Set device operating mode
- **Parameters**:
  - `device_id` (string, required): Device ID
  - `mode` (string, required, enum: "auto", "off"): Operating mode
- **Returns**: Confirmation of mode change

#### `update_program`
- **Description**: Update an existing watering program's configuration
- **Parameters**:
  - `device_id` (string, required): Device ID
  - `program_id` (string, required): Program ID from `get_programs`
  - `start_times` (array of strings, optional): Watering start times in HH:MM format
  - `frequency` (object, optional): `{ "type": "days"|"interval", "days": [0-6], "interval": int }`
  - `budget` (int, optional, 0-200): Watering budget percentage (100 = default, 50 = half, 200 = double)
- **Returns**: Updated program config
- **Notes**: Programs must be created in the B-Hyve app first. This tool only modifies existing programs.

#### `toggle_smart_watering`
- **Description**: Enable or disable Smart Watering for a specific zone
- **Parameters**:
  - `device_id` (string, required): Device ID
  - `zone` (int, required): Zone/station number
  - `enabled` (bool, required): true to enable, false to disable
- **Returns**: Confirmation

---

## MCP Resources (Read-Only Context)

#### `bhyve://devices`
- **Description**: Current snapshot of all devices and their status
- **Returns**: Full device list with status (equivalent to `list_devices` output)

#### `bhyve://device/{device_id}/zones`
- **Description**: Zone configuration for a specific device
- **Returns**: Zone details for the given device

---

## Connection Management

### Client Lifecycle
1. On first tool call, initialize `pybhyve.Client` with credentials from env vars
2. Call `client.login()` to authenticate
3. Cache the authenticated client instance for the session
4. Handle token expiration gracefully — re-auth on 401/403

### WebSocket
- **Do NOT use WebSocket for the initial implementation**. REST polling is sufficient for on-demand CLI usage.
- WebSocket adds complexity (persistent connection, reconnection logic) that isn't justified for Claude Code's request/response pattern.
- Future enhancement: optional WebSocket mode for real-time monitoring use cases.

### Error Handling
- Wrap all API calls in try/except
- Return structured error messages, not raw tracebacks
- Specific handling for:
  - Auth failures (bad credentials, expired token)
  - Network timeouts (Orbit servers are occasionally flaky)
  - Device offline (controller not connected)
  - Invalid zone/device IDs
  - Rate limiting (if encountered)

---

## Project Structure

```
bhyve-mcp/
├── pyproject.toml          # Project config, dependencies
├── .env.example            # Template for env vars
├── .gitignore
├── README.md
├── src/
│   └── bhyve_mcp/
│       ├── __init__.py
│       ├── server.py       # FastMCP server definition + tool registrations
│       ├── client.py       # pybhyve client wrapper with session management
│       └── models.py       # Pydantic models for tool responses (optional but nice)
└── tests/
    ├── __init__.py
    ├── test_server.py      # MCP tool tests with mocked bhyve client
    └── conftest.py
```

---

## Claude Code / Cursor Configuration

### Claude Code (`~/.claude/claude_code_config.json` or project `.mcp.json`)
```json
{
  "mcpServers": {
    "bhyve": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/bhyve-mcp", "python", "-m", "bhyve_mcp.server"],
      "env": {
        "BHYVE_EMAIL": "your-email@example.com",
        "BHYVE_PASSWORD": "your-password"
      }
    }
  }
}
```

### Cursor (`~/.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "bhyve": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/bhyve-mcp", "python", "-m", "bhyve_mcp.server"],
      "env": {
        "BHYVE_EMAIL": "your-email@example.com",
        "BHYVE_PASSWORD": "your-password"
      }
    }
  }
}
```

---

## Implementation Notes

### pybhyve API Reference (Reverse-Engineered)

The B-Hyve API is undocumented. Key details from the HA integration and community reverse engineering:

- **Base URL**: `https://api.orbitbhyve.com/v1/`
- **Auth**: POST to login endpoint, returns token for subsequent requests
- **Devices**: GET `/devices` — returns array of all account devices
- **Watering Events**: GET `/watering_events/{device_id}?page=1&per-page=10`
- **Commands are sent via WebSocket** in the HA integration, but REST endpoints exist for most operations
- **pybhyve Client interface**:
  ```python
  from pybhyve import Client
  from aiohttp import ClientSession

  async with ClientSession() as session:
      client = Client(email, password, loop, session, ws_handler)
      await client.login()
      devices = await client.devices  # property, returns list of device dicts
  ```
- **Known device types**: `sprinkler_timer`, `bridge` (WiFi hub), `flood_sensor`
- **Zone commands**: Sent as WebSocket messages in HA integration. If pybhyve doesn't expose zone start/stop directly, you may need to:
  1. Check pybhyve source for undocumented methods
  2. Use the REST API directly (the HA integration's `pybhyve` fork may have more methods than the published pip package)
  3. Reference `sebr/bhyve-home-assistant` for the exact WebSocket message format

### B-Hyve WebSocket Command Format (from HA integration)
```json
{
  "event": "change_mode",
  "mode": "manual",
  "device_id": "...",
  "timestamp": "2026-06-27T12:00:00.000Z",
  "stations": [
    {
      "station": 1,
      "run_time": 10
    }
  ]
}
```

### Key Gotcha: pybhyve Staleness
- `pybhyve` on PyPI was last updated for Python 3.6-3.8 era
- The HA integration (`sebr/bhyve-home-assistant`) bundles its own updated fork of pybhyve internally
- **You may need to vendor or fork pybhyve**, pulling the latest client code from the HA integration's `custom_components/bhyve/pybhyve/` directory
- If pybhyve is too stale, build a minimal REST client directly against `api.orbitbhyve.com` using the HA integration as reference

---

## Testing Strategy

1. **Unit tests**: Mock the pybhyve client, test tool registration and response formatting
2. **Integration tests**: Hit the real Orbit API with a test account (optional, gated behind env var)
3. **MCP Inspector**: Use `mcp dev` CLI to interactively test tools during development
4. **Manual smoke test**: Configure in Claude Code, ask it to list devices and start a zone

---

## Out of Scope (v1)

- Creating new watering programs (must be done in B-Hyve app)
- Flood sensor management beyond status reporting
- Firmware updates
- Multi-account support
- WebSocket persistent connection / real-time event streaming
- OAuth / token refresh (pybhyve handles session internally)
- SSE or Streamable HTTP transport (stdio only for v1)

---

## Future Enhancements (v2+)

- WebSocket mode for real-time zone status during watering
- Weather-aware watering recommendations (integrate weather API)
- Watering schedule optimization suggestions
- NPM package / Docker container for easier distribution
- Publish to MCP server registry
- Home Assistant bridge mode (if someone runs both)

---

## Reference Repos

- **pybhyve** (Python B-Hyve client): https://github.com/sebr/pybhyve
- **bhyve-home-assistant** (HA integration, most complete implementation): https://github.com/sebr/bhyve-home-assistant
- **bhyve-mqtt** (Node.js MQTT bridge): https://github.com/billchurch/bhyve-mqtt
- **orbit-bhyve-remote** (simple Node.js remote): https://github.com/blacksmithlabs/orbit-bhyve-remote
- **MCP Python SDK**: https://github.com/modelcontextprotocol/python-sdk
- **FastMCP docs**: https://modelcontextprotocol.github.io/python-sdk/
