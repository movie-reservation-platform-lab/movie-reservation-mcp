from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import httpx
from fastmcp import Client


async def main() -> None:
    assert os.getuid() == 10001
    assert shutil.which("uv") is None
    assert shutil.which("uvx") is None
    assert shutil.which("curl") is None
    assert not Path("/app/src").exists()

    async with httpx.AsyncClient(timeout=2) as health_client:
        response = await health_client.get("http://127.0.0.1:8091/health")
        response.raise_for_status()
        assert response.json()["status"] == "ok"

    async with Client("http://127.0.0.1:8091/mcp", timeout=10) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools} == {
            "reservation_get_catalog",
            "reservation_request_seats",
            "reservation_get_request_status",
            "reservation_health",
        }
        result = await client.call_tool("reservation_health", {})
        assert not result.is_error
        assert result.data["ok"] is True
        assert result.data["health"]["status"] == "ok"

    print("Production health, MCP negotiation/tool call, UID and image contents passed.")


if __name__ == "__main__":
    asyncio.run(main())
