"""Tests for HTTP helper functions."""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientError, ClientSession, ServerConnectionError

from aiotedee.exceptions import (
    TedeeAuthException,
    TedeeClientException,
    TedeeRateLimitException,
)
from aiotedee.helpers import http_request, is_personal_key_valid


# -- http_request --------------------------------------------------------------


def _mock_response(status: int, json_data=None):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    return resp


class TestHttpRequest:
    async def test_success_returns_json(self):
        session = MagicMock(spec=ClientSession)
        session.request = AsyncMock(return_value=_mock_response(200, {"ok": True}))

        result = await http_request("http://x", "GET", {}, session, timeout=5)
        assert result == {"ok": True}

    async def test_201_accepted(self):
        session = MagicMock(spec=ClientSession)
        session.request = AsyncMock(return_value=_mock_response(201, {"id": 1}))

        result = await http_request("http://x", "POST", {}, session, timeout=5)
        assert result == {"id": 1}

    async def test_401_raises_auth_exception(self):
        session = MagicMock(spec=ClientSession)
        session.request = AsyncMock(return_value=_mock_response(401))

        with pytest.raises(TedeeAuthException):
            await http_request("http://x", "GET", {}, session, timeout=5)

    async def test_429_raises_rate_limit(self):
        session = MagicMock(spec=ClientSession)
        session.request = AsyncMock(return_value=_mock_response(429))

        with pytest.raises(TedeeRateLimitException):
            await http_request("http://x", "GET", {}, session, timeout=5)

    async def test_404_raises_client_exception(self):
        session = MagicMock(spec=ClientSession)
        session.request = AsyncMock(return_value=_mock_response(404))

        with pytest.raises(TedeeClientException, match="not found"):
            await http_request("http://x", "GET", {}, session, timeout=5)

    async def test_406_raises_client_exception(self):
        session = MagicMock(spec=ClientSession)
        session.request = AsyncMock(return_value=_mock_response(406))

        with pytest.raises(TedeeClientException, match="not acceptable"):
            await http_request("http://x", "GET", {}, session, timeout=5)

    async def test_409_raises_client_exception(self):
        session = MagicMock(spec=ClientSession)
        session.request = AsyncMock(return_value=_mock_response(409))

        with pytest.raises(TedeeClientException, match="Conflict"):
            await http_request("http://x", "GET", {}, session, timeout=5)

    async def test_500_raises_generic_client_exception(self):
        session = MagicMock(spec=ClientSession)
        session.request = AsyncMock(return_value=_mock_response(500))

        with pytest.raises(TedeeClientException, match="500"):
            await http_request("http://x", "GET", {}, session, timeout=5)

    async def test_connection_error_raises_client_exception(self):
        session = MagicMock(spec=ClientSession)
        session.request = AsyncMock(side_effect=ClientError("conn refused"))

        with pytest.raises(TedeeClientException, match="Error during http call"):
            await http_request("http://x", "GET", {}, session, timeout=5)

    async def test_timeout_error_raises_client_exception(self):
        session = MagicMock(spec=ClientSession)
        session.request = AsyncMock(side_effect=TimeoutError())

        with pytest.raises(TedeeClientException):
            await http_request("http://x", "GET", {}, session, timeout=5)


# -- is_personal_key_valid -----------------------------------------------------


class TestIsPersonalKeyValid:
    async def test_valid_key(self):
        session = MagicMock(spec=ClientSession)
        resp = AsyncMock()
        resp.status = 200
        session.get = AsyncMock(return_value=resp)

        assert await is_personal_key_valid("key", session) is True

    async def test_invalid_key_401(self):
        session = MagicMock(spec=ClientSession)
        resp = AsyncMock()
        resp.status = 401
        session.get = AsyncMock(return_value=resp)

        assert await is_personal_key_valid("bad", session) is False

    async def test_connection_error_returns_false(self):
        session = MagicMock(spec=ClientSession)
        session.get = AsyncMock(side_effect=ClientError())

        assert await is_personal_key_valid("key", session) is False
