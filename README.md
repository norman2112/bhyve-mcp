# bhyve-mcp

MCP server for [Orbit B-Hyve](https://orbitbhyve.com/) irrigation systems. Query and control sprinklers from Claude Code, Cursor, or any MCP-compatible client.

## Features

- **Read tools**: list devices, device status, zones, programs, watering history
- **Write tools**: start/stop watering, rain delay, device mode, program updates, smart watering toggle
- **Resources**: `bhyve://devices` and `bhyve://device/{device_id}/zones`
- **Transport**: stdio (local MCP)

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Orbit B-Hyve account

## Setup

1. Clone this repo and install dependencies:

```bash
cd bhyve-mcp
uv sync
```

2. Copy credentials:

```bash
cp .env.example .env
# Edit .env with your BHYVE_EMAIL and BHYVE_PASSWORD
```

## Cursor / Claude Code configuration

Add to `~/.cursor/mcp.json` or your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "bhyve": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/bhyve-mcp",
        "python",
        "-m",
        "bhyve_mcp.server"
      ],
      "env": {
        "BHYVE_EMAIL": "your-email@example.com",
        "BHYVE_PASSWORD": "your-password"
      }
    }
  }
}
```

Replace `/path/to/bhyve-mcp` with the absolute path to this directory.

## Development

```bash
# Run tests
uv run pytest

# Interactive MCP testing
uv run mcp dev src/bhyve_mcp/server.py
```

## Architecture

- **FastMCP** (`mcp` Python SDK) — MCP tool/resource server over stdio
- **Vendored pybhyve** — B-Hyve REST + WebSocket client (from [sebr/bhyve-home-assistant](https://github.com/sebr/bhyve-home-assistant))
- **Session wrapper** — lazy auth, token refresh on 401/403, structured errors

Write operations (start watering, rain delay, etc.) use the B-Hyve WebSocket API. Read operations use REST polling.

## Safety

- `start_watering` defaults to a 30-minute max unless `allow_extended_runtime=true`
- Rain delay capped at 168 hours (7 days)
- Watering duration capped at 120 minutes

## License

MIT
