import aiohttp
from .const import API_URL_DEVICE, TIMEOUT

async def is_personal_key_valid(personal_key, timeout=TIMEOUT) -> bool:
    try:
        async with aiohttp.ClientSession(
            headers={"Content-Type": "application/json", "Authorization": "PersonalKey " + personal_key}, 
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            async with session.get(API_URL_DEVICE) as response:
                if response.status == 200:
                    return True
                else:
                    return False
    except:
        return False