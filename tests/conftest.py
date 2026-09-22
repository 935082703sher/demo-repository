"""Shared isolated application fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app

# A developer's local .env (see README) must never leak into the test suite.
# Tests construct Settings(...) with explicit values and rely on those init
# arguments taking effect; with fields that use validation_alias, a loaded
# .env otherwise overrides them. Disable dotenv loading for the whole session
# and drop any cached settings built before this ran.
Settings.model_config["env_file"] = None
get_settings.cache_clear()


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
