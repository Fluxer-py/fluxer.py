"""Reproducible offline cache measurements: python benchmarks/cache.py."""

import asyncio
import gc
import json
import platform
import sys
import time
import tracemalloc
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(
    0, sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1])
)

from fluxer import Bot, Client, Message  # noqa: E402


async def measure():
    """Measure fixed workloads without network access."""
    result = {"python": platform.python_version(), "messages": 1000}
    gc.collect()
    tracemalloc.start()
    client = Client()
    payload = {
        "channel_id": "2",
        "guild_id": "1",
        "content": "hello",
        "author": {"id": "3", "username": "author"},
        "timestamp": "2026-01-01T00:00:00Z",
    }
    started = time.perf_counter()
    for index in range(1000):
        await client._dispatch("MESSAGE_CREATE", {**payload, "id": str(index + 10)})
    result["message_dispatch_seconds"] = time.perf_counter() - started
    result["unique_retained_authors"] = len(
        {id(m.author) for m in client.cached_messages}
    )
    gc.collect()
    result["retained_bytes"], result["peak_bytes"] = tracemalloc.get_traced_memory()
    result["retained_allocation_blocks"] = sum(
        stat.count for stat in tracemalloc.take_snapshot().statistics("filename")
    )
    tracemalloc.stop()
    await client.close()
    bot = Bot(command_prefix="!")
    bot.process_commands = AsyncMock()
    with patch.object(Message, "from_data", wraps=Message.from_data) as parser:
        await bot._dispatch("MESSAGE_CREATE", {**payload, "id": "9"})
        await asyncio.sleep(0)
        result["bot_message_parses"] = parser.call_count
    await bot.close()
    for unrelated in (0, 1000, 5000):
        client = Client()
        await client._dispatch(
            "GUILD_CREATE", {"id": "1", "channels": [{"id": "2", "type": 0}]}
        )
        for index in range(unrelated):
            await client._dispatch(
                "GUILD_CREATE",
                {
                    "id": str(index + 100),
                    "channels": [{"id": str(index + 10000), "type": 0}],
                },
            )
        started = time.perf_counter()
        for _ in range(200):
            await client._dispatch("GUILD_UPDATE", {"id": "1", "name": "updated"})
        result[f"guild_update_200_unrelated_{unrelated}_seconds"] = (
            time.perf_counter() - started
        )
        await client.close()
    return result


if __name__ == "__main__":
    print(json.dumps(asyncio.run(measure()), indent=2))
