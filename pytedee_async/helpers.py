import aiohttp
from .const import API_URL_DEVICE, TIMEOUT
from .exception import TedeeAuthException, TedeeClientException, TedeeRateLimitException


async def is_personal_key_valid(personal_key, timeout=TIMEOUT) -> bool:
    try:
        async with aiohttp.ClientSession(
            headers={
                "Content-Type": "application/json",
                "Authorization": "PersonalKey " + personal_key,
            },
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as session:
            async with session.get(API_URL_DEVICE) as response:
                if response.status == 200:
                    return True
                else:
                    return False
    except Exception:
        return False


async def http_request(
    url: str, http_method: str, headers, timeout, json_data: dict = None
):
    async with aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)
    ) as session:
        if http_method == "GET":
            async with session.get(url) as response:
                return await handle_response(response)
        elif http_method == "POST":
            async with session.post(url, json=json_data) as response:
                return await handle_response(response)
        elif http_method == "PUT":
            async with session.put(url, json=json_data) as response:
                return await handle_response(response)
        elif http_method == "DELETE":
            async with session.delete(url) as response:
                return await handle_response(response)
        else:
            raise ValueError(f"Unsupported HTTP method: {http_method}")


async def handle_response(response):
    status_code = response.status
    if status_code == 200 or status_code == 202 or status_code == 204:
        return await response.json()
    elif response.status == 401:
        raise TedeeAuthException("Authentication failed.")
    elif response.status == 429:
        raise TedeeRateLimitException("Tedee API Rate Limit.")
    else:
        raise TedeeClientException(
            f"Error during HTTP request. Status code {response.status}"
        )
