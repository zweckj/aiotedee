"""Helper functions for pytedee_async."""
from typing import Any, Mapping

import aiohttp

from .const import API_URL_DEVICE, TIMEOUT
from .exception import TedeeAuthException, TedeeClientException, TedeeRateLimitException


async def is_personal_key_valid(
    personal_key: str,
    timeout: int = TIMEOUT,
    session: aiohttp.ClientSession | None = None,
) -> bool:
    """Check if personal key is valid."""
    if session is None:
        session = aiohttp.ClientSession()
    try:
        async with session:
            response = await session.get(
                API_URL_DEVICE,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "PersonalKey " + personal_key,
                },
                timeout=timeout,
            )
            if response.status in (200, 201, 204):
                return True
            return False
    except (aiohttp.ClientError, aiohttp.ServerConnectionError, TimeoutError):
        return False


async def http_request(
    url: str,
    http_method: str,
    headers: Mapping[str, str] | None,
    timeout: int = TIMEOUT,
    json_data: Any = None,
    session: aiohttp.ClientSession | None = None,
) -> Any:
    """HTTP request wrapper."""
    if session is None:
        session = aiohttp.ClientSession()
    async with session:
        try:
            if http_method == "GET":
                response = await session.get(url, headers=headers, timeout=timeout)
            elif http_method == "POST":
                response = await session.post(
                    url, headers=headers, json=json_data, timeout=timeout
                )
            elif http_method == "PUT":
                response = await session.put(
                    url, headers=headers, json=json_data, timeout=timeout
                )
            elif http_method == "DELETE":
                response = await session.delete(url, headers=headers, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {http_method}")
        except (
            aiohttp.ServerDisconnectedError,
            aiohttp.ClientError,
            TimeoutError,
        ) as exc:
            raise TedeeClientException(f"Error during http call: {exc}") from exc

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
