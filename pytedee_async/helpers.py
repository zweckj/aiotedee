"""Helper functions for pytedee_async."""
from typing import Any, Mapping

import aiohttp

from .const import API_URL_DEVICE, TIMEOUT
from .exception import TedeeAuthException, TedeeClientException, TedeeRateLimitException


async def is_personal_key_valid(
    personal_key: str,
    session: aiohttp.ClientSession,
    timeout: int = TIMEOUT,
) -> bool:
    """Check if personal key is valid."""

    try:
        async with session.get(
            API_URL_DEVICE,
            headers={
                "Content-Type": "application/json",
                "Authorization": "PersonalKey " + personal_key,
            },
            timeout=timeout,
        ) as response:
            if response.status in (200, 201, 204):
                return True
            return False
    except (aiohttp.ClientError, aiohttp.ServerConnectionError, TimeoutError):
        return False


async def http_request(
    url: str,
    http_method: str,
    headers: Mapping[str, str] | None,
    session: aiohttp.ClientSession,
    timeout: int = TIMEOUT,
    json_data: Any = None,
) -> Any:
    """HTTP request wrapper."""
    if http_method == "GET":
        method = session.get
    elif http_method == "POST":
        method = session.post
    elif http_method == "PUT":
        method = session.put
    elif http_method == "DELETE":
        method = session.delete
    else:
        raise ValueError(f"Unsupported HTTP method: {http_method}")

    try:
        async with method(
            url,
            headers=headers,
            json=json_data,
            timeout=timeout,
        ) as response:
            status_code = response.status
            if status_code in (200, 201, 204):
                return await response.json()
            if status_code == 401:
                raise TedeeAuthException("Authentication failed.")
            if status_code == 429:
                raise TedeeRateLimitException("Tedee API Rate Limit.")

            raise TedeeClientException(
                f"Error during HTTP request. Status code {status_code}"
            )
    except (
        aiohttp.ServerConnectionError,
        aiohttp.ClientError,
        TimeoutError,
    ) as exc:
        raise TedeeClientException(f"Error during http call: {exc}") from exc

    status_code = response.status
