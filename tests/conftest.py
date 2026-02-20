"""Pytest fixtures and configuration for tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import src.config

from src.config import ServerConfig, build_tenant_config
from src.library.notebook_library import NotebookLibrary


@pytest.fixture
def tmp_library(tmp_path, monkeypatch):
    """NotebookLibrary backed by an isolated tmp directory."""
    monkeypatch.setattr(src.config.CONFIG, "dataDir", str(tmp_path))
    monkeypatch.setenv("NOTEBOOK_URL", "")
    return NotebookLibrary()


@pytest.fixture
def sample_notebook_data():
    """Minimal valid notebook input data."""
    return {
        "url": "https://notebooklm.google.com/notebook/test-abc",
        "name": "Test Notebook",
        "description": "A notebook for testing purposes",
        "topics": ["testing", "pytest", "automation"],
    }


@pytest.fixture
def tmp_library_with_notebook(tmp_library, sample_notebook_data):
    """NotebookLibrary pre-populated with one notebook."""
    tmp_library.add_notebook(sample_notebook_data)
    return tmp_library


@pytest.fixture
def mock_session_manager():
    """Mock SessionManager that requires no browser."""
    manager = MagicMock()
    manager.close_sessions_for_notebook = AsyncMock(return_value=0)
    manager.list_sessions = MagicMock(return_value=[])
    return manager


@pytest.fixture
def mock_auth_manager():
    """Mock AuthManager that requires no browser."""
    auth = MagicMock()
    auth.is_authenticated = MagicMock(return_value=False)
    return auth


@pytest.fixture
def server_config(tmp_path):
    """ServerConfig pointing to a tmp directory."""
    cfg = ServerConfig()
    cfg.baseDataDir = str(tmp_path)
    cfg.maxTenantsInMemory = 5
    cfg.tenantIdleTimeoutSeconds = 3600
    return cfg


@pytest.fixture
def tenant_config(server_config):
    """A per-user Config derived from server_config."""
    return build_tenant_config(server_config, "test-user")


@pytest.fixture
def tenant_library(tenant_config):
    """NotebookLibrary backed by the tenant's isolated directory."""
    from pathlib import Path
    Path(tenant_config.dataDir).mkdir(parents=True, exist_ok=True)
    return NotebookLibrary(tenant_config)
