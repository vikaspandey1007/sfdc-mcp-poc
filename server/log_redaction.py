"""Defense-in-depth log redaction for the hosted runtime.

`logger.exception()` / `exc_info=True` bypasses any redaction applied to a
log *message* string: Python's logging/traceback machinery re-serializes
the raw exception object (`str(exc)`, plus every frame's traceback text)
independently of whatever string was passed to the logging call. A
third-party exception whose own message happens to embed a credential --
e.g. a URL with an API key as a query parameter, or some library's debug
repr dumping a Bearer header -- would leak through even a carefully-worded
log message if `exc_info=True` is used naively on it.

Checked empirically, not assumed, for the exceptions this app actually
sees: `google.genai`'s client sends its API key via the `x-goog-api-key`
*header*, not a URL query parameter (`.venv/Lib/site-packages/google/genai/_api_client.py`),
and `httpx`'s own `Request`/`Response.__repr__` include only method/URL/
status, never headers. This module exists anyway, as defense-in-depth
against a future dependency change or an exception type this app hasn't
hit yet -- not because a leak has actually been observed.

server/app.py's catch-all exception handler must go through
`log_exception_redacted()` here rather than calling `logger.exception()`
directly, for exactly this reason.
"""

from __future__ import annotations

import logging
import os
import re
import traceback

# Every secret this process is actually configured with, read fresh from
# os.environ on each call (so a rotated value is picked up automatically,
# and nothing here caches a stale copy of a secret in memory).
_SECRET_ENV_VARS = ("GOOGLE_API_KEY", "SF_ECA_CONSUMER_KEY", "DEMO_API_KEY", "CREDENTIAL_ENCRYPTION_KEY")

# Generic shapes, for a value this process wasn't itself configured with --
# e.g. a stale/rotated Salesforce access token still embedded in a cached
# third-party exception, which _SECRET_ENV_VARS above can't catch since the
# live token isn't a fixed env var.
_PATTERN_REDACTIONS = (
    (re.compile(r"Bearer\s+[A-Za-z0-9\-_.~+/]+=*", re.IGNORECASE), "Bearer [REDACTED]"),
    (
        re.compile(
            r"([?&](?:key|api[_-]?key|access_token|refresh_token|client_secret|code)=)[^&\s'\"]+",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]",
    ),
)


def redact(text: str) -> str:
    """Scrubs known-sensitive substrings from a piece of log text."""
    for name in _SECRET_ENV_VARS:
        value = os.environ.get(name)
        if value:
            text = text.replace(value, f"[REDACTED:{name}]")
    for pattern, replacement in _PATTERN_REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def log_exception_redacted(logger: logging.Logger, message: str, exc: BaseException) -> None:
    """Logs an exception's full traceback, redacted, without ever calling
    `logger.exception()` or passing `exc_info=True` -- see this module's
    docstring for why those bypass redaction entirely."""
    formatted_traceback = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("%s\n%s", message, redact(formatted_traceback))
