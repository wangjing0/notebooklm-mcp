"""Tests for TenantManager: cache, isolation, and LRU eviction."""

import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.config import ServerConfig, build_tenant_config
from src.tenant_manager import TenantManager, TenantResources


@pytest.fixture
def small_server_config(tmp_path):
    cfg = ServerConfig()
    cfg.baseDataDir = str(tmp_path)
    cfg.maxTenantsInMemory = 3
    cfg.tenantIdleTimeoutSeconds = 60
    return cfg


class TestTenantManagerCacheBehavior:
    async def test_cache_miss_creates_tenant(self, small_server_config):
        mgr = TenantManager(small_server_config)
        tenant = await mgr.get_tenant("alice")
        assert isinstance(tenant, TenantResources)
        assert tenant.user_id == "alice"

    async def test_cache_hit_returns_same_object(self, small_server_config):
        mgr = TenantManager(small_server_config)
        first = await mgr.get_tenant("alice")
        second = await mgr.get_tenant("alice")
        assert first is second

    async def test_cache_hit_updates_last_access(self, small_server_config):
        mgr = TenantManager(small_server_config)
        tenant = await mgr.get_tenant("alice")
        before = tenant.last_access
        time.sleep(0.01)
        await mgr.get_tenant("alice")
        assert tenant.last_access >= before

    async def test_active_tenant_count(self, small_server_config):
        mgr = TenantManager(small_server_config)
        await mgr.get_tenant("alice")
        await mgr.get_tenant("bob")
        assert mgr.active_tenant_count == 2

    async def test_same_tenant_not_duplicated(self, small_server_config):
        mgr = TenantManager(small_server_config)
        for _ in range(5):
            await mgr.get_tenant("alice")
        assert mgr.active_tenant_count == 1


class TestTenantIsolation:
    async def test_different_users_get_different_resources(self, small_server_config):
        mgr = TenantManager(small_server_config)
        alice = await mgr.get_tenant("alice")
        bob = await mgr.get_tenant("bob")
        assert alice is not bob
        assert alice.config.dataDir != bob.config.dataDir
        assert alice.library is not bob.library
        assert alice.sessions is not bob.sessions

    async def test_tenant_data_dir_is_user_scoped(self, small_server_config, tmp_path):
        mgr = TenantManager(small_server_config)
        tenant = await mgr.get_tenant("carol")
        expected = str(tmp_path / "users" / "carol")
        assert tenant.config.dataDir == expected

    async def test_tenant_directories_are_created(self, small_server_config, tmp_path):
        mgr = TenantManager(small_server_config)
        await mgr.get_tenant("dave")
        assert Path(tmp_path / "users" / "dave").exists()

    async def test_library_files_are_isolated(self, small_server_config, tmp_path):
        mgr = TenantManager(small_server_config)
        alice = await mgr.get_tenant("alice")
        bob = await mgr.get_tenant("bob")
        alice_lib_path = Path(alice.config.dataDir) / "library.json"
        bob_lib_path = Path(bob.config.dataDir) / "library.json"
        assert alice_lib_path != bob_lib_path


class TestLRUEviction:
    async def test_lru_evicts_when_limit_reached(self, small_server_config):
        mgr = TenantManager(small_server_config)
        with patch.object(mgr, "_evict_lru", wraps=mgr._evict_lru) as mock_evict:
            for name in ["alice", "bob", "carol"]:
                await mgr.get_tenant(name)
            assert mgr.active_tenant_count == 3
            await mgr.get_tenant("dave")
            mock_evict.assert_called_once()

    async def test_lru_evicts_least_recently_accessed(self, small_server_config):
        mgr = TenantManager(small_server_config)
        await mgr.get_tenant("alice")
        time.sleep(0.01)
        await mgr.get_tenant("bob")
        time.sleep(0.01)
        await mgr.get_tenant("carol")
        assert mgr.active_tenant_count == 3
        await mgr.get_tenant("dave")
        assert mgr.active_tenant_count == 3
        assert "alice" not in mgr._tenants

    async def test_eviction_calls_close_all_sessions(self, small_server_config):
        mgr = TenantManager(small_server_config)
        for name in ["alice", "bob", "carol"]:
            t = await mgr.get_tenant(name)
            t.sessions.close_all_sessions = AsyncMock()
        alice_sessions = mgr._tenants["alice"].sessions
        alice_sessions.last_access = mgr._tenants["alice"].last_access = 0.0
        await mgr.get_tenant("dave")
        alice_sessions.close_all_sessions.assert_called_once()


class TestIdleEviction:
    async def test_evict_idle_tenants_removes_stale(self, small_server_config):
        small_server_config.tenantIdleTimeoutSeconds = 0
        mgr = TenantManager(small_server_config)
        await mgr.get_tenant("alice")
        time.sleep(0.01)
        evicted = await mgr.evict_idle_tenants()
        assert evicted == 1
        assert mgr.active_tenant_count == 0

    async def test_evict_idle_skips_recent_tenants(self, small_server_config):
        small_server_config.tenantIdleTimeoutSeconds = 3600
        mgr = TenantManager(small_server_config)
        await mgr.get_tenant("alice")
        evicted = await mgr.evict_idle_tenants()
        assert evicted == 0
        assert mgr.active_tenant_count == 1


class TestShutdown:
    async def test_shutdown_clears_all_tenants(self, small_server_config):
        mgr = TenantManager(small_server_config)
        await mgr.get_tenant("alice")
        await mgr.get_tenant("bob")
        await mgr.shutdown()
        assert mgr.active_tenant_count == 0

    async def test_shutdown_calls_close_sessions(self, small_server_config):
        mgr = TenantManager(small_server_config)
        t = await mgr.get_tenant("alice")
        t.sessions.close_all_sessions = AsyncMock()
        await mgr.shutdown()
        t.sessions.close_all_sessions.assert_called_once()


class TestBuildTenantConfig:
    def test_tenant_config_has_isolated_dirs(self, tmp_path):
        server_config = ServerConfig()
        server_config.baseDataDir = str(tmp_path)
        cfg = build_tenant_config(server_config, "frank")
        assert "frank" in cfg.dataDir
        assert "frank" in cfg.browserStateDir
        assert "frank" in cfg.chromeProfileDir
        assert "frank" in cfg.chromeInstancesDir

    def test_two_users_have_different_configs(self, tmp_path):
        server_config = ServerConfig()
        server_config.baseDataDir = str(tmp_path)
        cfg_alice = build_tenant_config(server_config, "alice")
        cfg_bob = build_tenant_config(server_config, "bob")
        assert cfg_alice.dataDir != cfg_bob.dataDir
