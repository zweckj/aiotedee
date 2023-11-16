"""Helper functions for pytedee_async."""
from typing import Any, Mapping

import aiohttp

from .const import API_URL_DEVICE, TIMEOUT
from .exception import TedeeAuthException, TedeeClientException, TedeeRateLimitException


async def is_personal_key_valid(personal_key: str, timeout: int = TIMEOUT) -> bool:
    """Check if personal key is valid."""
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
                return False
    except aiohttp.ClientError:
        return False


async def http_request(
    url: str,
    http_method: str,
    headers: Mapping[str, str] | None,
    timeout: int,
    json_data: Any = None,
) -> Any:
    """HTTP request wrapper."""
    async with aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)
    ) as session:
        if http_method == "GET":
            async with session.get(url) as response:
                return await handle_response(response)
        if http_method == "POST":
            async with session.post(url, json=json_data) as response:
                return await handle_response(response)
        if http_method == "PUT":
            async with session.put(url, json=json_data) as response:
                return await handle_response(response)
        if http_method == "DELETE":
            async with session.delete(url) as response:
                return await handle_response(response)
        raise ValueError(f"Unsupported HTTP method: {http_method}")


async def handle_response(response) -> Any:
    """Handle HTTP response."""
    status_code = response.status
    if status_code in (200, 202, 204):
        return await response.json()
    if response.status == 401:
        raise TedeeAuthException("Authentication failed.")
    if response.status == 429:
        raise TedeeRateLimitException("Tedee API Rate Limit.")

    raise TedeeClientException(
        f"Error during HTTP request. Status code {response.status}"
    )
