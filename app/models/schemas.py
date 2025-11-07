from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class VersionInfo(BaseModel):
    id: str
    type: str  # release, snapshot, old_alpha, old_beta
    url: str
    release_time: datetime
    decompiled: bool = False
    file_count: Optional[int] = None
    size_bytes: Optional[int] = None


class FileNode(BaseModel):
    name: str
    path: str
    type: str  # file, directory
    size: Optional[int] = None
    children: Optional[list["FileNode"]] = None


class FileContent(BaseModel):
    path: str
    content: str
    size: int
    language: str = "java"
    version: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    versions: Optional[list[str]] = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class SearchResult(BaseModel):
    version: str
    file_path: str
    class_name: Optional[str] = None
    line_number: Optional[int] = None
    snippet: str
    score: float


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]
    processing_time_ms: float


class VersionStats(BaseModel):
    version: str
    total_files: int
    total_classes: int
    total_lines: int
    size_bytes: int
    packages: int


class APIHealth(BaseModel):
    status: str
    version_count: int
    cache_hit_rate: Optional[float] = None
    db_connected: bool
    cache_ready: bool
    search_ready: bool
