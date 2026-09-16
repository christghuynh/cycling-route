from collections.abc import Iterator
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        ors_api_key="test-key",
        ors_base_url="https://ors.test",
        photon_base_url="https://photon.test",
    )


@pytest.fixture
def api_mock() -> Iterator[respx.MockRouter]:
    """Intercept all outgoing HTTP calls. Unmocked external requests fail the test."""
    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def client(settings: Settings, api_mock: respx.MockRouter) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
