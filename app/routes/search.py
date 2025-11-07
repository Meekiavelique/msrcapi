from blacksheep import Router, json, FromJSON, Response
from app.services.search_service import search_service
from app.models.schemas import SearchRequest

router = Router()


@router.get("/api/v1/search")
async def search_get(
    q: str, versions: str = None, limit: int = 50, offset: int = 0
) -> Response:
    if not q or len(q.strip()) == 0:
        return json({"error": "Query parameter 'q' is required"}, status=400)

    version_list = None
    if versions:
        version_list = [v.strip() for v in versions.split(",") if v.strip()]

    request = SearchRequest(query=q, versions=version_list, limit=limit, offset=offset)

    result = await search_service.search(request)
    return json(result.model_dump())


@router.post("/api/v1/search")
async def search_post(request: FromJSON[SearchRequest]) -> Response:
    result = await search_service.search(request.value)
    return json(result.model_dump())
