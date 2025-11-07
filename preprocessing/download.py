import asyncio
import httpx
import json
from pathlib import Path
from typing import List, Dict
from datetime import datetime


class MinecraftVersionDownloader:

    def __init__(self, data_dir: Path, min_version: str = "1.13", max_version: str = "1.21"):
        self.data_dir = data_dir
        self.min_version = self._parse_version(min_version)
        self.max_version = self._parse_version(max_version)
        self.manifest_url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

    def _parse_version(self, version: str) -> tuple:
        parts = version.split(".")
        return tuple(int(p) if p.isdigit() else p for p in parts)

    def _version_in_range(self, version: str) -> bool:
        try:
            v = self._parse_version(version)
            return self.min_version <= v <= self.max_version
        except Exception:
            return False

    async def get_version_manifest(self) -> List[Dict]:
        async with httpx.AsyncClient() as client:
            response = await client.get(self.manifest_url, timeout=30.0)
            response.raise_for_status()
            manifest = response.json()

            # filter versions in range
            filtered = []
            for version in manifest["versions"]:
                vid = version["id"]
                if self._version_in_range(vid):
                    filtered.append(
                        {
                            "id": vid,
                            "type": version["type"],
                            "url": version["url"],
                            "release_time": version["releaseTime"],
                        }
                    )

            return filtered

    async def download_version_json(self, version: Dict) -> Dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(version["url"], timeout=30.0)
            response.raise_for_status()
            return response.json()

    async def download_version_jar(self, version_id: str, download_url: str) -> Path:
        version_dir = self.data_dir / version_id
        version_dir.mkdir(parents=True, exist_ok=True)

        jar_path = version_dir / f"{version_id}.jar"

        if jar_path.exists():
            print(f"  JAR already exists: {jar_path}")
            return jar_path

        print(f"  Downloading JAR: {download_url}")
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", download_url, timeout=300.0) as response:
                response.raise_for_status()

                total = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(jar_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            progress = (downloaded / total) * 100
                            print(f"\r  Progress: {progress:.1f}%", end="", flush=True)

                print()  #

        return jar_path

    async def download_mappings(self, version_id: str, mappings_url: str) -> Path:
        version_dir = self.data_dir / version_id
        mappings_path = version_dir / "client.txt"

        if mappings_path.exists():
            print(f"  Mappings already exist: {mappings_path}")
            return mappings_path

        print(f"  Downloading mappings: {mappings_url}")
        async with httpx.AsyncClient() as client:
            response = await client.get(mappings_url, timeout=60.0)
            response.raise_for_status()

            with open(mappings_path, "wb") as f:
                f.write(response.content)

        return mappings_path

    async def download_version(self, version: Dict) -> tuple[Path, Path]:
        version_id = version["id"]
        print(f"\nDownloading {version_id}...")

        version_json = await self.download_version_json(version)

        client_url = version_json["downloads"]["client"]["url"]
        jar_path = await self.download_version_jar(version_id, client_url)

        mappings_path = None
        if "client_mappings" in version_json["downloads"]:
            mappings_url = version_json["downloads"]["client_mappings"]["url"]
            mappings_path = await self.download_mappings(version_id, mappings_url)
        else:
            print(f"  No official mappings available for {version_id}")

        return jar_path, mappings_path

    async def download_all(self) -> List[tuple[str, Path, Path]]:
        print("Fetching version manifest...")
        versions = await self.get_version_manifest()

        print(f"Found {len(versions)} versions in range {self.min_version} to {self.max_version}")

        results = []
        for version in versions:
            try:
                jar_path, mappings_path = await self.download_version(version)
                results.append((version["id"], jar_path, mappings_path))
            except Exception as e:
                print(f"Failed to download {version['id']}: {e}")

        return results


async def main():
    from pathlib import Path

    data_dir = Path("./data/minecraft")
    downloader = MinecraftVersionDownloader(data_dir, min_version="1.20", max_version="1.20.1")

    results = await downloader.download_all()
    print(f"\nDownloaded {len(results)} versions")


if __name__ == "__main__":
    asyncio.run(main())
