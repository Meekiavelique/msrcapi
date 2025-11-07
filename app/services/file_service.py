import aiofiles
import os
from pathlib import Path
from typing import Optional, Dict, List
from app.config import settings
from app.services.cache import cache
from app.services.database import db
from app.models.schemas import FileContent, FileNode


class FileService:
    def __init__(self):
        self.data_dir = settings.data_dir

    def get_file_path(self, version: str, relative_path: str) -> Path:
        return self.data_dir / version / "src" / relative_path

    async def get_file_content(self, version: str, path: str) -> Optional[FileContent]:
        cache_key = cache.cache_key_file(version, path)
        cached = await cache.get_str(cache_key)
        if cached:
            file_path = self.get_file_path(version, path)
            size = file_path.stat().st_size if file_path.exists() else 0
            return FileContent(
                path=path, content=cached, size=size, language="java", version=version
            )

        file_path = self.get_file_path(version, path)
        if not file_path.exists():
            return None

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()

            size = file_path.stat().st_size

            await cache.set_str(cache_key, content, ttl=settings.cache_ttl)

            return FileContent(
                path=path, content=content, size=size, language="java", version=version
            )
        except Exception:
            return None

    async def get_file_tree(self, version: str) -> Optional[FileNode]:
        cache_key = cache.cache_key_tree(version)
        cached = await cache.get_json(cache_key)
        if cached:
            return FileNode(**cached)

        db_cached = await db.get_file_tree(version)
        if db_cached:
            await cache.set_json(cache_key, db_cached, ttl=settings.cache_ttl)
            return FileNode(**db_cached)

        version_dir = self.data_dir / version / "src"
        if not version_dir.exists():
            return None

        tree = self._build_tree(version_dir, version_dir)

        tree_dict = tree.model_dump()
        await cache.set_json(cache_key, tree_dict, ttl=settings.cache_ttl)
        await db.cache_file_tree(version, tree_dict)

        return tree

    def _build_tree(self, root: Path, current: Path) -> FileNode:
        relative = current.relative_to(root)
        name = current.name if current != root else "src"

        if current.is_file():
            size = current.stat().st_size
            return FileNode(
                name=name, path=str(relative), type="file", size=size, children=None
            )

        children = []
        try:
            for child in sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
                children.append(self._build_tree(root, child))
        except PermissionError:
            pass

        return FileNode(name=name, path=str(relative), type="directory", children=children)

    async def list_files(self, version: str, directory: str = "") -> List[str]:
        dir_path = self.data_dir / version / "src" / directory
        if not dir_path.exists() or not dir_path.is_dir():
            return []

        files = []
        for item in dir_path.rglob("*.java"):
            relative = item.relative_to(self.data_dir / version / "src")
            files.append(str(relative))

        return sorted(files)

    def get_version_size(self, version: str) -> int:
        version_dir = self.data_dir / version / "src"
        if not version_dir.exists():
            return 0

        total = 0
        for item in version_dir.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
        return total

    def count_files(self, version: str) -> int:
        version_dir = self.data_dir / version / "src"
        if not version_dir.exists():
            return 0

        return len(list(version_dir.rglob("*.java")))


file_service = FileService()
