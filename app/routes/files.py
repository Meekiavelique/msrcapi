from blacksheep import Router, json, Response
from blacksheep.server.responses import text
from app.services.file_service import file_service

router = Router()


@router.get("/api/v1/versions/{version}/file")
async def get_file(version: str, path: str) -> Response:
    if not path:
        return json({"error": "Path parameter is required"}, status=400)

    file_content = await file_service.get_file_content(version, path)
    if not file_content:
        return json({"error": "File not found"}, status=404)

    return json(file_content.model_dump())


@router.get("/api/v1/versions/{version}/file/raw")
async def get_file_raw(version: str, path: str) -> Response:
    if not path:
        return text("Path parameter is required", status=400)

    file_content = await file_service.get_file_content(version, path)
    if not file_content:
        return text("File not found", status=404)

    return text(file_content.content, headers={"Content-Type": "text/plain; charset=utf-8"})
