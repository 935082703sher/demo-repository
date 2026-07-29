"""Shared isolated application fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Create fresh in-memory session and draft stores for each test."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def complete_network_fields() -> dict[str, str]:
    """Synthetic, non-personal complaint values."""
    return {
        "operator": "Demo Operator",
        "service_type": "mobile_data",
        "region": "Demo Region",
        "district": "Demo District",
        "approximate_location": "Demo central area",
        "event_time": "2026-07-28T10:00:00Z",
        "frequency": "several times",
        "duration": "about five minutes",
        "impact": "The synthetic demo connection becomes unavailable.",
    }
