import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import List
import aiofiles
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.services.database import db
from app.services.search_service import search_service
from app.models.schemas import VersionInfo

class VersionIndexer:
    def __init__(self):
        self.data_dir = settings.data_dir

    async def _count_lines(self, path: Path) -> int:
        count = 0
        async with aiofiles.open(path, "r", encoding="utf-8", errors="ignore") as f:
            async for _ in f:
                count += 1
        return count

    async def _gather_file_metadata(self, src_dir: Path) -> List[dict]:
        java_files = list(src_dir.rglob("*.java"))
        total_files = len(java_files)
        if total_files == 0:
            return []

        print(f"  Found {total_files} Java files")
        semaphore = asyncio.Semaphore(settings.threads)
        metadata: List[dict] = []

        async def process(path: Path):
            async with semaphore:
                relative_path = path.relative_to(src_dir)
                size = path.stat().st_size
                line_count = await self._count_lines(path)

                parts = str(relative_path).replace("\\", "/").split("/")
                class_name = parts[-1].replace(".java", "") if parts else None
                package = ".".join(parts[:-1]) if len(parts) > 1 else None

                return {
                    "path": str(relative_path),
                    "size_bytes": size,
                    "line_count": line_count,
                    "class_name": class_name,
                    "package": package,
                }

        tasks = [asyncio.create_task(process(path)) for path in java_files]
        completed = 0
        for task in asyncio.as_completed(tasks):
            try:
                result = await task
                if result:
                    metadata.append(result)
            except Exception as exc:
                print(f"  Failed to process file: {exc}")
            completed += 1
            if completed % 200 == 0:
                print(f"  Processed {completed}/{total_files} files...", end="\r")

        return metadata

    async def index_version_files(self, version_id: str, src_dir: Path):
        print(f"\nIndexing files for {version_id}...")

        metadata = await self._gather_file_metadata(src_dir)
        await db.add_files_bulk(version_id, metadata)

        print(f"  Indexed {len(metadata)} files for {version_id}")
        return metadata

    async def index_version_search(self, version_id: str, file_metadata: List[dict]):
        print(f"\nIndexing {version_id} for search...")

        file_paths = sorted([item["path"] for item in file_metadata])
        await search_service.register_version(version_id, file_paths)

        print(f"  Registered {len(file_paths)} files for search")
        return len(file_paths)

    async def update_version_metadata(
        self, version_id: str, version_type: str, url: str, release_time: str, file_count: int, size_bytes: int
    ):
        version_info = VersionInfo(
            id=version_id,
            type=version_type,
            url=url,
            release_time=datetime.fromisoformat(release_time.replace("Z", "+00:00")),
            decompiled=True,
            file_count=file_count,
            size_bytes=size_bytes,
        )

        await db.upsert_version(version_info)
        print(f"  Updated metadata for {version_id}")

    def _calculate_directory_size(self, directory: Path) -> int:
        total = 0
        for file in directory.rglob("*"):
            if file.is_file():
                total += file.stat().st_size
        return total

    async def index_version(
        self,
        version_id: str,
        version_type: str,
        url: str,
        release_time: str,
        src_dir: Path,
        size_bytes: int,
    ):
        print(f"\n{'=' * 60}")
        print(f"Indexing {version_id}")
        print(f"{'=' * 60}")

        file_metadata = await self.index_version_files(version_id, src_dir)
        file_count = len(file_metadata)

        await self.index_version_search(version_id, file_metadata)

        computed_size = size_bytes or sum(item["size_bytes"] for item in file_metadata)

        await self.update_version_metadata(
            version_id, version_type, url, release_time, file_count, computed_size
        )

        print(f"\n✓ Completed indexing {version_id}")
        print(f"  Files: {file_count}")
        print(f"  Size: {computed_size / 1024 / 1024:.2f} MB")

    async def index_all_versions(self, versions: List[dict]):
        for version in versions:
            version_id = version["id"]
            src_dir = self.data_dir / version_id / "src"

            if not src_dir.exists():
                print(f"Skipping {version_id} - not decompiled")
                continue

            await self.index_version(
                version_id,
                version["type"],
                version["url"],
                version["release_time"],
                src_dir,
                self._calculate_directory_size(src_dir),
            )

async def main():

    await db.connect()
    await db.init_schema()
    await search_service.connect()
    await search_service.init_index()

    indexer = VersionIndexer()

    test_version = {
        "id": "1.20.1",
        "type": "release",
        "url": "https://example.com/1.20.1.json",
        "release_time": "2023-06-12T12:00:00Z",
    }

    src_dir = settings.data_dir / test_version["id"] / "src"
    if src_dir.exists():
        size_bytes = indexer._calculate_directory_size(src_dir)
        await indexer.index_version(
            test_version["id"],
            test_version["type"],
            test_version["url"],
            test_version["release_time"],
            src_dir,
            size_bytes,
        )
    else:
        print(f"Source directory not found: {src_dir}")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())