"""Test run."""

import asyncio
import json
from pathlib import Path

from aiotedee import TedeeLocalClient


async def main():
    with open(f"{Path(__file__).parent}/config.json", encoding="utf-8") as f:
        data = json.load(f)
    ip = data["ip"]
    local_token = data["localToken"]

    client = TedeeLocalClient(local_ip=ip, local_token=local_token)
    await client.get_locks()
    await client.sync()

    for lock in client.locks:
        print("----------------------------------------------")
        print(f"Lock name: {lock.name}")
        print(f"Lock id: {lock.id}")
        print(f"Lock Battery: {lock.battery_level}")
        print(f"Is Locked: {lock.is_locked}")
        print(f"Is Unlocked: {lock.is_unlocked}")
        await client.unlock(lock.id)


asyncio.run(main())
