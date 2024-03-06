"""Test run."""

import asyncio
import json

from pathlib import Path

from pytedee_async import TedeeClient
from pytedee_async.lock import TedeeLock


async def main():
    with open(f"{Path(__file__).parent}/config.json", encoding="utf-8") as f:
        data = json.load(f)
    # personal_token = data["personalToken"]
    ip = data["ip"]
    local_token = data["localToken"]

    # client = await TedeeClient.create(personal_token, local_token, ip)
    client = TedeeClient(local_ip=ip, local_token=local_token)
    # await client.cleanup_webhooks_by_host("test")
    # bridge = await client.get_local_bridge()
    # await client.delete_webhook(5)
    # await client.register_webhook("http://192.168.1.151/events")
    await client.get_locks()
    #  await client.sync()
    # await client.sync()
    # bridges = await client.get_bridges()
    # client = await TedeeClient.create(
    #     personal_token, local_token, ip, bridge_id=bridges[0].bridge_id
    # )
    locks = client.locks
    print(1)
    await client.sync()
    print(2)
    await client.sync()

    for lock in locks:
        print("----------------------------------------------")
        print("Lock name: " + lock.lock_name)
        print("Lock id: " + str(lock.lock_id))
        print("Lock Battery: " + str(lock.battery_level))
        print("Is Locked: " + str(client.is_locked(lock.lock_id)))
        print("Is Unlocked: " + str(client.is_unlocked(lock.lock_id)))
        # await client.register_webhook("http://test.local", headers=[{"Authorization": "Basic " + "test"}])
        print(3)
        await client.sync()
        await client.unlock(lock.lock_id)
        # await asyncio.sleep(5)
        # await client.open(lock.id)
        # await asyncio.sleep(5)
        # await client.open(lock.id)
        # await asyncio.sleep(5)
        # await client.lock(lock.id)
        # await asyncio.sleep(5)
        # await client.unlock(lock.id)
        # await asyncio.sleep(5)
        # await client.pull(lock.id)


asyncio.run(main())
