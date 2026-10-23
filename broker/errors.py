"""Typed broker errors (plan A8)."""


class BrokerError(Exception):
    """Base broker error."""


class AuthError(BrokerError):
    """Session/token invalid — re-login once."""


class RateLimited(BrokerError):
    """AB1021 / too many requests — backoff."""


class Rejected(BrokerError):
    """Order rejected — do not retry."""


class Unavailable(BrokerError):
    """Network / 5xx — retry reads only."""
