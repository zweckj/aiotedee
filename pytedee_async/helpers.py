"""Helper functions for pytedee_async."""
from typing import Any, Mapping

import httpx

from .const import API_URL_DEVICE, TIMEOUT
from .exception import TedeeAuthException, TedeeClientException, TedeeRateLimitException


async def is_personal_key_valid(personal_key: str, timeout: int = TIMEOUT) -> bool:
    """Check if personal key is valid."""
    try:
        async with httpx.AsyncClient(
            headers={
                "Content-Type": "application/json",
                "Authorization": "PersonalKey " + personal_key,
            },
            timeout=timeout,
        ) as client:
            response = await client.get(API_URL_DEVICE)
            if response.is_success:
                return True
            return False
    except (httpx.HTTPError, TimeoutError):
        return False


async def http_request(
    url: str,
    http_method: str,
    headers: Mapping[str, str] | None,
    timeout: int,
    json_data: Any = None,
) -> Any:
    """HTTP request wrapper."""
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        if http_method == "GET":
            response = await client.get(url)
            return await handle_response(response)
        if http_method == "POST":
            response = await client.post(url, json=json_data)
            return await handle_response(response)
        if http_method == "PUT":
            response = await client.put(url, json=json_data)
            return await handle_response(response)
        if http_method == "DELETE":
            response = await client.delete(url)
            return await handle_response(response)
        raise ValueError(f"Unsupported HTTP method: {http_method}")


async def handle_response(response: httpx.Response) -> Any:
    """Handle HTTP response."""
    if response.is_success:
        return await response.json()

    if response.status_code == 401:
        raise TedeeAuthException("Authentication failed.")
    if response.status_code == 429:
        raise TedeeRateLimitException("Tedee API Rate Limit.")

    raise TedeeClientException(
        f"Error during HTTP request. Status code {response.status_code}"
    )
