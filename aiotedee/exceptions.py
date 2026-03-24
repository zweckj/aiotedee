"""Exceptions for aiotedee."""

class TedeeException(Exception):
    """Base exception for aiotedee."""

class TedeeClientException(TedeeException):
    """General Tedee client exception."""


class TedeeAuthException(TedeeException):
    """Authentication exception against remote API."""


class TedeeLocalAuthException(TedeeException):
    """Authentication exception against local API."""


class TedeeRateLimitException(TedeeException):
    """Rate limit exception (only happens on cloud API)."""


class TedeeWebhookException(TedeeException):
    """Webhook exception."""


class TedeeDataUpdateException(TedeeException):
    """Data update exception."""
