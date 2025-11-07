import json
from pathlib import Path
from typing import List, Optional

import aiosqlite

from app.config import settings
from app.models.schemas import VersionInfo, VersionStats


class DatabaseService:
    def __init__(self) -> None:
        self.db_path: Path = settings.database_path
        self._connected: bool = False

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.execute("PRAGMA synchronous=NORMAL;")
            await conn.commit()
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    async def init_schema(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON;")
            await conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS versions (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    url TEXT NOT NULL,
                    release_time TEXT NOT NULL,
                    decompiled INTEGER DEFAULT 0,
                    file_count INTEGER,
                    size_bytes INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_versions_type ON versions(type);
                CREATE INDEX IF NOT EXISTS idx_versions_decompiled ON versions(decompiled);
                CREATE INDEX IF NOT EXISTS idx_versions_release_time ON versions(release_time);

                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    package TEXT,
                    class_name TEXT,
                    size_bytes INTEGER NOT NULL,
                    line_count INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(version_id, path),
                    FOREIGN KEY(version_id) REFERENCES versions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_files_version ON files(version_id);
                CREATE INDEX IF NOT EXISTS idx_files_package ON files(package);
                CREATE INDEX IF NOT EXISTS idx_files_class ON files(class_name);

                CREATE TABLE IF NOT EXISTS file_tree_cache (
                    version_id TEXT PRIMARY KEY,
                    tree_json TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(version_id) REFERENCES versions(id) ON DELETE CASCADE
                );
                """
            )
            await conn.commit()

    async def _fetchall(self, query: str, params: tuple = ()) -> list[aiosqlite.Row]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            await cursor.close()
            return rows

    async def _fetchone(self, query: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            await cursor.close()
            return row

    async def execute(self, query: str, params: tuple = ()) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON;")
            await conn.execute(query, params)
            await conn.commit()

    async def get_all_versions(self) -> List[VersionInfo]:
        rows = await self._fetchall(
            """
            SELECT id, type, url, release_time, decompiled, file_count, size_bytes
            FROM versions
            ORDER BY release_time DESC
            """
        )
        return [VersionInfo(**dict(row)) for row in rows]

    async def get_version(self, version_id: str) -> Optional[VersionInfo]:
        row = await self._fetchone(
            """
            SELECT id, type, url, release_time, decompiled, file_count, size_bytes
            FROM versions
            WHERE id = ?
            """,
            (version_id,),
        )
        return VersionInfo(**dict(row)) if row else None

    async def get_decompiled_versions(self) -> List[str]:
        rows = await self._fetchall(
            "SELECT id FROM versions WHERE decompiled = 1 ORDER BY release_time DESC"
        )
        return [row["id"] for row in rows]

    async def upsert_version(self, version: VersionInfo) -> None:
        release_time = version.release_time.isoformat()
        await self.execute(
            """
            INSERT INTO versions (id, type, url, release_time, decompiled, file_count, size_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type=excluded.type,
                url=excluded.url,
                release_time=excluded.release_time,
                decompiled=excluded.decompiled,
                file_count=excluded.file_count,
                size_bytes=excluded.size_bytes
            """,
            (
                version.id,
                version.type,
                version.url,
                release_time,
                1 if version.decompiled else 0,
                version.file_count,
                version.size_bytes,
            ),
        )

    async def add_file(self, version_id: str, path: str, size: int, line_count: int = 0) -> None:
        package = None
        class_name = None
        if path.endswith(".java"):
            parts = path.replace("\\", "/").split("/")
            if len(parts) > 1:
                class_name = parts[-1].replace(".java", "")
                package = ".".join(parts[:-1])

        await self.execute(
            """
            INSERT INTO files (version_id, path, package, class_name, size_bytes, line_count)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(version_id, path) DO UPDATE SET
                size_bytes=excluded.size_bytes,
                line_count=excluded.line_count,
                package=excluded.package,
                class_name=excluded.class_name
            """,
            (version_id, path, package, class_name, size, line_count),
        )

    async def add_files_bulk(self, version_id: str, files: List[dict]) -> None:
        if not files:
            return

        records = []
        for file_info in files:
            path = file_info["path"]
            package = file_info.get("package")
            class_name = file_info.get("class_name")
            size = file_info.get("size_bytes", 0)
            line_count = file_info.get("line_count", 0)
            records.append((version_id, path, package, class_name, size, line_count))

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON;")
            await conn.executemany(
                """
                INSERT INTO files (version_id, path, package, class_name, size_bytes, line_count)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(version_id, path) DO UPDATE SET
                    size_bytes=excluded.size_bytes,
                    line_count=excluded.line_count,
                    package=excluded.package,
                    class_name=excluded.class_name
                """,
                records,
            )
            await conn.commit()

    async def get_file_tree(self, version_id: str) -> Optional[dict]:
        row = await self._fetchone(
            "SELECT tree_json FROM file_tree_cache WHERE version_id = ?",
            (version_id,),
        )
        if row:
            try:
                return json.loads(row["tree_json"])
            except json.JSONDecodeError:
                return None
        return None

    async def cache_file_tree(self, version_id: str, tree: dict) -> None:
        await self.execute(
            """
            INSERT INTO file_tree_cache (version_id, tree_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(version_id) DO UPDATE SET
                tree_json=excluded.tree_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (version_id, json.dumps(tree)),
        )

    async def get_version_stats(self, version_id: str) -> Optional[VersionStats]:
        row = await self._fetchone(
            """
            SELECT
                v.id as version,
                COALESCE(v.file_count, 0) as total_files,
                COUNT(DISTINCT f.class_name) as total_classes,
                COALESCE(SUM(f.line_count), 0) as total_lines,
                COALESCE(v.size_bytes, 0) as size_bytes,
                COUNT(DISTINCT f.package) as packages
            FROM versions v
            LEFT JOIN files f ON v.id = f.version_id
            WHERE v.id = ?
            GROUP BY v.id, v.file_count, v.size_bytes
            """,
            (version_id,),
        )
        return VersionStats(**dict(row)) if row else None

    async def get_version_count(self) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) as total FROM versions WHERE decompiled = 1"
        )
        return int(row["total"]) if row else 0


db = DatabaseService()


db = DatabaseService()
