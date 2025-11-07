import copy
import fnmatch
import time
from typing import Any, Dict, Optional


class CacheEntry:
    def __init__(self, value: Any, expires_at: Optional[float]):
        self.value = value
        self.expires_at = expires_at


class CacheService:
    def __init__(self):
        self._store: Dict[str, CacheEntry] = {}
        self.hits = 0
        self.misses = 0
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._store.clear()
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [key for key, entry in self._store.items() if entry.expires_at and entry.expires_at < now]
        for key in expired:
            del self._store[key]

    def get_hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    async def get(self, key: str) -> Optional[Any]:
        self._purge_expired()
        entry = self._store.get(key)
        if entry:
            self.hits += 1
            return entry.value
        self.misses += 1
        return None

    async def get_json(self, key: str) -> Optional[Any]:
        value = await self.get(key)
        return copy.deepcopy(value) if value is not None else None

    async def get_str(self, key: str) -> Optional[str]:
        value = await self.get(key)
        return value if isinstance(value, str) else None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        expires_at = time.time() + ttl if ttl else None
        self._store[key] = CacheEntry(value, expires_at)

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        await self.set(key, copy.deepcopy(value), ttl)

    async def set_str(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        await self.set(key, value, ttl)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def delete_pattern(self, pattern: str) -> None:
        to_remove = [key for key in self._store if fnmatch.fnmatch(key, pattern)]
        for key in to_remove:
            del self._store[key]

    async def exists(self, key: str) -> bool:
        self._purge_expired()
        return key in self._store

    def cache_key_file(self, version: str, path: str) -> str:
        return f"file:{version}:{path}"

    def cache_key_tree(self, version: str) -> str:
        return f"tree:{version}"

    def cache_key_versions(self) -> str:
        return "versions:all"

    def cache_key_version(self, version: str) -> str:
        return f"version:{version}"


cache = CacheService()
