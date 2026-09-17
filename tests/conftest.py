"""Shared pytest configuration.

Registers the `integration` marker and keeps that suite opt-in: it hits the
real Salesforce org and real Gemini API, so per the Gate 3 plan's Step 5
split it stays a deliberately-invoked, slower suite rather than part of the
default fast unit run.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run the opt-in integration suite against the real Salesforce org and Gemini API.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: hits the real Salesforce org and Gemini API; opt-in via --run-integration",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration"):
        return
    skip_integration = pytest.mark.skip(reason="need --run-integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
