"""Tests for HTTP helper functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientError, ClientSession

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


@pytest.mark.parametrize(
    ("status", "json_data"),
    [(200, {"ok": True}), (201, {"id": 1}), (202, {}), (204, None)],
    ids=["200-ok", "201-created", "202-accepted", "204-no-content"],
)
async def test_http_request_success(status, json_data):
    session = MagicMock(spec=ClientSession)
    session.request = AsyncMock(return_value=_mock_response(status, json_data))
    result = await http_request("http://x", "GET", {}, session, timeout=5)
    assert result == json_data


@pytest.mark.parametrize(
    ("status", "exc_type", "match"),
    [
        (401, TedeeAuthException, "Authentication"),
        (429, TedeeRateLimitException, "Rate Limit"),
        (404, TedeeClientException, "not found"),
        (406, TedeeClientException, "not acceptable"),
        (409, TedeeClientException, "Conflict"),
        (500, TedeeClientException, "500"),
    ],
    ids=["401-auth", "429-rate-limit", "404-not-found", "406-not-acceptable", "409-conflict", "500-server-error"],
)
async def test_http_request_error_status(status, exc_type, match):
    session = MagicMock(spec=ClientSession)
    session.request = AsyncMock(return_value=_mock_response(status))
    with pytest.raises(exc_type, match=match):
        await http_request("http://x", "GET", {}, session, timeout=5)


@pytest.mark.parametrize(
    "exc",
    [ClientError("conn refused"), TimeoutError()],
    ids=["client-error", "timeout"],
)
async def test_http_request_connection_errors(exc):
    session = MagicMock(spec=ClientSession)
    session.request = AsyncMock(side_effect=exc)
    with pytest.raises(TedeeClientException):
        await http_request("http://x", "GET", {}, session, timeout=5)


# -- is_personal_key_valid -----------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [(200, True), (201, True), (202, True), (401, False), (500, False)],
    ids=["200-valid", "201-valid", "202-valid", "401-invalid", "500-invalid"],
)
async def test_is_personal_key_valid_by_status(status, expected):
    session = MagicMock(spec=ClientSession)
    resp = AsyncMock()
    resp.status = status
    session.get = AsyncMock(return_value=resp)
    assert await is_personal_key_valid("key", session) is expected


async def test_is_personal_key_valid_connection_error():
    session = MagicMock(spec=ClientSession)
    session.get = AsyncMock(side_effect=ClientError())
    assert await is_personal_key_valid("key", session) is False
