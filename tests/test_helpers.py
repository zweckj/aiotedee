"""Tests for HTTP helper functions."""

from __future__ import annotations

import pytest
from aiohttp import ClientError, ClientSession

from aiotedee.const import API_URL_DEVICE
from aiotedee.exceptions import (
    TedeeAuthException,
    TedeeClientException,
    TedeeRateLimitException,
)
from aiotedee.helpers import http_request, is_personal_key_valid


@pytest.fixture
async def session():
    """Provide a real aiohttp session, closed after test."""
    s = ClientSession()
    yield s
    await s.close()


# -- http_request --------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "json_data"),
    [(200, {"ok": True}), (201, {"id": 1}), (202, {}), (204, None)],
    ids=["200-ok", "201-created", "202-accepted", "204-no-content"],
)
async def test_http_request_success(mock_api, session, status, json_data):
    mock_api.get("http://test/api", status=status, payload=json_data)
    result = await http_request("http://test/api", "GET", {}, session, timeout=5)
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
async def test_http_request_error_status(mock_api, session, status, exc_type, match):
    mock_api.get("http://test/api", status=status)
    with pytest.raises(exc_type, match=match):
        await http_request("http://test/api", "GET", {}, session, timeout=5)


@pytest.mark.parametrize(
    "exc",
    [ClientError("conn refused"), TimeoutError()],
    ids=["client-error", "timeout"],
)
async def test_http_request_connection_errors(mock_api, session, exc):
    mock_api.get("http://test/api", exception=exc)
    with pytest.raises(TedeeClientException):
        await http_request("http://test/api", "GET", {}, session, timeout=5)


# -- is_personal_key_valid -----------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [(200, True), (201, True), (202, True), (401, False), (500, False)],
    ids=["200-valid", "201-valid", "202-valid", "401-invalid", "500-invalid"],
)
async def test_is_personal_key_valid_by_status(mock_api, session, status, expected):
    mock_api.get(API_URL_DEVICE, status=status)
    assert await is_personal_key_valid("key", session) is expected


async def test_is_personal_key_valid_connection_error(mock_api, session):
    mock_api.get(API_URL_DEVICE, exception=ClientError("connection error"))
    assert await is_personal_key_valid("key", session) is False
