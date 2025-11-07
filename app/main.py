from blacksheep import Application, json
from blacksheep.server.routing import Router
from blacksheep.server.responses import text
import time
from app.config import settings
from app.services.database import db
from app.services.cache import cache
from app.services.search_service import search_service
from app.models.schemas import APIHealth

from app.routes.versions import router as versions_router
from app.routes.files import router as files_router
from app.routes.search import router as search_router

api_router = Router(sub_routers=[versions_router, files_router, search_router])
app = Application(router=api_router)


@app.on_start
async def on_start(application: Application) -> None:

    try:
        await db.connect()
        await db.init_schema()
        print("✓ Database connected")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")

    try:
        await cache.connect()
        print("✓ Cache initialized")
    except Exception as e:
        print(f"✗ Cache initialization failed: {e}")

    try:
        await search_service.connect()
        await search_service.init_index()
        print("✓ Search service ready")
    except Exception as e:
        print(f"✗ Search service initialization failed: {e}")

    print(f"API running at http://{settings.api_host}:{settings.api_port}")


@app.on_stop
async def on_stop(application: Application) -> None:
    print("Shutting down...")
    await db.disconnect()
    await cache.disconnect()
    print("Bye!")


@app.router.get("/")
async def index():
    return json(
        {
            "name": "Minecraft Source API",
            "version": "1.0.0",
            "description": "Blazingly fast API for serving decompiled Minecraft source code",
            "endpoints": {
                "versions": "/api/v1/versions",
                "version_detail": "/api/v1/versions/{version}",
                "version_stats": "/api/v1/versions/{version}/stats",
                "file_tree": "/api/v1/versions/{version}/tree",
                "file_content": "/api/v1/versions/{version}/file?path=...",
                "search": "/api/v1/search?q=...",
                "health": "/health",
            },
        }
    )


@app.router.get("/health")
async def health():
    db_connected = await db.is_connected()
    cache_ready = await cache.is_connected()
    search_ready = await search_service.is_connected()

    version_count = 0
    if db_connected:
        try:
            version_count = await db.get_version_count()
        except Exception:
            pass

    cache_hit_rate = cache.get_hit_rate() if cache_ready else None

    health_status = APIHealth(
        status="healthy" if all([db_connected, cache_ready, search_ready]) else "degraded",
        version_count=version_count,
        cache_hit_rate=cache_hit_rate,
        db_connected=db_connected,
        cache_ready=cache_ready,
        search_ready=search_ready,
    )

    status_code = 200 if health_status.status == "healthy" else 503
    return json(health_status.model_dump(), status=status_code)


@app.router.get("/metrics")
async def metrics():
    cache_hit_rate = cache.get_hit_rate()
    version_count = await db.get_version_count() if await db.is_connected() else 0

    metrics_text = f"""# HELP minecraft_api_cache_hit_rate Cache hit rate
# TYPE minecraft_api_cache_hit_rate gauge
minecraft_api_cache_hit_rate {cache_hit_rate}

# HELP minecraft_api_version_count Total decompiled versions
# TYPE minecraft_api_version_count gauge
minecraft_api_version_count {version_count}

# HELP minecraft_api_cache_hits Total cache hits
# TYPE minecraft_api_cache_hits counter
minecraft_api_cache_hits {cache.hits}

# HELP minecraft_api_cache_misses Total cache misses
# TYPE minecraft_api_cache_misses counter
minecraft_api_cache_misses {cache.misses}
"""
    return text(metrics_text, headers={"Content-Type": "text/plain; charset=utf-8"})



@app.on_middlewares_configuration
def configure_middlewares(app: Application):
    from blacksheep import Request

    async def timing_middleware(request: Request, handler):
        start = time.perf_counter()
        response = await handler(request)
        elapsed = (time.perf_counter() - start) * 1000
        response.headers[b"X-Response-Time"] = f"{elapsed:.2f}ms".encode()
        return response

    app.middlewares.append(timing_middleware)
