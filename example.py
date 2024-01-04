"""Test run."""
import asyncio
import json

from pytedee_async import TedeeClient
from pytedee_async.lock import TedeeLock


async def main():
    with open("config.json", encoding="utf-8") as f:
        data = json.load(f)
    personal_token = data["personalToken"]
    ip = data["ip"]
    local_token = data["localToken"]

    # client = await TedeeClient.create(personal_token, local_token, ip)
    client = await TedeeClient.create(personal_token)
    bridge = await client.get_local_bridge()
    bridges = await client.get_bridges()
    client = await TedeeClient.create(
        personal_token, local_token, ip, bridge_id=bridges[0].bridge_id
    )
    locks = client.locks

    locks_list = [lock.to_dict() for _, lock in client.locks_dict.items()]
    print(locks_list)
    json_locks = json.dumps(locks_list)
    loaded = json.loads(json_locks)
    for lock in loaded:
        dec = TedeeLock(**lock)
    for lock in locks:
        print("----------------------------------------------")
        print("Lock name: " + lock.lock_name)
        print("Lock id: " + str(lock.lock_id))
        print("Lock Battery: " + str(lock.battery_level))
        print("Is Locked: " + str(client.is_locked(lock.id)))
        print("Is Unlocked: " + str(client.is_unlocked(lock.id)))
        # await client.register_webhook("http://test.local", headers=[{"Authorization": "Basic " + "test"}])
        await client.sync()
        # await client.lock(lock.id)
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
