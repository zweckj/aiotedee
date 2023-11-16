"""Exceptions for pytedee_async."""


class TedeeClientException(Exception):
    """General Tedee client exception."""


class TedeeAuthException(Exception):
    """Authentication exception against remote API."""


class TedeeLocalAuthException(Exception):
    """Authentication exception against local API."""


class TedeeRateLimitException(Exception):
    """Rate limit exception (only happens on cloud API)."""


class TedeeWebhookException(Exception):
    """Webhook exception."""


class TedeeDataUpdateException(Exception):
    """Data update exception."""
