import time
from typing import Dict, List, Optional

from app.config import settings
from app.models.schemas import SearchRequest, SearchResponse, SearchResult
from app.services.file_service import file_service
from app.services.database import db


class SearchService:
    def __init__(self) -> None:
        self._ready = False
        self._file_registry: Dict[str, List[str]] = {}

    async def connect(self) -> None:
        await self.refresh_index()

    async def init_index(self) -> None:
        await self.refresh_index()

    async def refresh_index(self) -> None:
        versions: List[str] = []
        try:
            versions = await db.get_decompiled_versions()
        except Exception:
            versions = []

        if not versions and settings.data_dir.exists():
            versions = [d.name for d in settings.data_dir.iterdir() if d.is_dir()]

        for version in versions:
            self._file_registry[version] = await file_service.list_files(version)

        self._ready = True

    async def is_connected(self) -> bool:
        return self._ready

    async def register_version(self, version: str, files: Optional[List[str]] = None) -> None:
        if files is None:
            files = await file_service.list_files(version)
        self._file_registry[version] = files

    def _build_snippet(self, content: str, index: int, length: int) -> str:
        window = 150
        start = max(0, index - window)
        end = min(len(content), index + length + window)
        snippet = content[start:end].strip().replace("\n", " ")
        return snippet

    async def search(self, request: SearchRequest) -> SearchResponse:
        start_time = time.perf_counter()

        if not self._ready:
            await self.refresh_index()

        query = request.query.lower()
        versions = request.versions or list(self._file_registry.keys())

        if not versions and settings.data_dir.exists():
            versions = [d.name for d in settings.data_dir.iterdir() if d.is_dir()]

        results: List[SearchResult] = []
        total_matches = 0

        for version in versions:
            file_paths = self._file_registry.get(version)
            if file_paths is None:
                file_paths = await file_service.list_files(version)
                self._file_registry[version] = file_paths

            for file_path in file_paths:
                file_content = await file_service.get_file_content(version, file_path)
                if not file_content or not file_content.content:
                    continue

                lower_content = file_content.content.lower()
                match_index = lower_content.find(query)
                if match_index == -1:
                    continue

                total_matches += 1
                if total_matches <= request.offset:
                    continue
                if len(results) >= request.limit:
                    continue

                line_number = file_content.content.count("\n", 0, match_index) + 1
                snippet = self._build_snippet(file_content.content, match_index, len(query))

                results.append(
                    SearchResult(
                        version=version,
                        file_path=file_path,
                        class_name=None,
                        line_number=line_number,
                        snippet=snippet,
                        score=1.0,
                    )
                )

        processing_time = (time.perf_counter() - start_time) * 1000

        return SearchResponse(
            query=request.query,
            total=total_matches,
            results=results,
            processing_time_ms=round(processing_time, 2),
        )

search_service = SearchService()
