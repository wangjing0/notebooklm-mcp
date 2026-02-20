import time

from dataclasses import dataclass, field

from .auth.auth_manager import AuthManager
from .config import Config, ServerConfig, build_tenant_config, ensure_directories
from .library.notebook_library import NotebookLibrary
from .session.session_manager import SessionManager
from .utils.logger import log


@dataclass
class TenantResources:
    user_id: str
    config: Config
    auth: AuthManager
    sessions: SessionManager
    library: NotebookLibrary
    last_access: float = field(default_factory=time.time)


class TenantManager:
    def __init__(self, server_config: ServerConfig) -> None:
        self._server_config = server_config
        self._tenants: dict[str, TenantResources] = {}

    async def get_tenant(self, user_id: str) -> TenantResources:
        if user_id in self._tenants:
            tenant = self._tenants[user_id]
            tenant.last_access = time.time()
            log.info(f"Tenant cache hit: {user_id}")
            return tenant

        if len(self._tenants) >= self._server_config.maxTenantsInMemory:
            await self._evict_lru()

        tenant = await self._create_tenant(user_id)
        self._tenants[user_id] = tenant
        log.info(f"Tenant created: {user_id} ({len(self._tenants)} active)")
        return tenant

    async def _create_tenant(self, user_id: str) -> TenantResources:
        config = build_tenant_config(self._server_config, user_id)
        ensure_directories(config)
        auth = AuthManager(config)
        sessions = SessionManager(auth, config)
        library = NotebookLibrary(config)
        return TenantResources(
            user_id=user_id,
            config=config,
            auth=auth,
            sessions=sessions,
            library=library,
        )

    async def _evict_lru(self) -> None:
        if not self._tenants:
            return
        lru_id = min(self._tenants, key=lambda uid: self._tenants[uid].last_access)
        tenant = self._tenants.pop(lru_id)
        log.warning(f"Evicting LRU tenant: {lru_id}")
        try:
            await tenant.sessions.close_all_sessions()
        except Exception as e:
            log.warning(f"Error closing sessions for evicted tenant {lru_id}: {e}")

    async def evict_idle_tenants(self) -> int:
        now = time.time()
        idle = [
            uid for uid, t in self._tenants.items()
            if (now - t.last_access) > self._server_config.tenantIdleTimeoutSeconds
        ]
        for uid in idle:
            tenant = self._tenants.pop(uid)
            log.info(f"Evicting idle tenant: {uid}")
            try:
                await tenant.sessions.close_all_sessions()
            except Exception as e:
                log.warning(f"Error closing sessions for idle tenant {uid}: {e}")
        return len(idle)

    async def shutdown(self) -> None:
        log.info(f"Shutting down TenantManager ({len(self._tenants)} tenants)...")
        for uid, tenant in list(self._tenants.items()):
            try:
                await tenant.sessions.close_all_sessions()
            except Exception as e:
                log.warning(f"Error shutting down tenant {uid}: {e}")
        self._tenants.clear()
        log.info("TenantManager shutdown complete")

    @property
    def active_tenant_count(self) -> int:
        return len(self._tenants)
