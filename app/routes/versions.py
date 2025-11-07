from blacksheep import Router, json, Response
from app.services.database import db
from app.services.cache import cache
from app.services.file_service import file_service
from app.models.schemas import VersionInfo, VersionStats, FileNode

router = Router()


@router.get("/api/v1/versions")
async def get_versions() -> Response:
    cache_key = cache.cache_key_versions()
    cached = await cache.get_json(cache_key)
    if cached:
        return json(cached)

    versions = await db.get_all_versions()
    result = [v.model_dump() for v in versions]

    await cache.set_json(cache_key, result, ttl=300)  # 5 minutes

    return json(result)


@router.get("/api/v1/versions/{version}")
async def get_version(version: str) -> Response:
    cache_key = cache.cache_key_version(version)
    cached = await cache.get_json(cache_key)
    if cached:
        return json(cached)

    version_info = await db.get_version(version)
    if not version_info:
        return json({"error": "Version not found"}, status=404)

    result = version_info.model_dump()

    await cache.set_json(cache_key, result, ttl=3600)

    return json(result)


@router.get("/api/v1/versions/{version}/stats")
async def get_version_stats(version: str) -> Response:
    cache_key = f"stats:{version}"
    cached = await cache.get_json(cache_key)
    if cached:
        return json(cached)

    stats = await db.get_version_stats(version)
    if not stats:
        return json({"error": "Version not found"}, status=404)

    result = stats.model_dump()

    await cache.set_json(cache_key, result, ttl=3600)

    return json(result)


@router.get("/api/v1/versions/{version}/tree")
async def get_file_tree(version: str) -> Response:
    tree = await file_service.get_file_tree(version)
    if not tree:
        return json({"error": "Version not found or not decompiled"}, status=404)

    return json(tree.model_dump())


@router.get("/api/v1/versions/{version}/files")
async def list_files(version: str, directory: str = "") -> Response:
    files = await file_service.list_files(version, directory)
    return json({"version": version, "directory": directory, "files": files})
