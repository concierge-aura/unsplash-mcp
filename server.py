#!/usr/bin/env python3
import os, json, httpx
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("unsplash_mcp")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
BASE_URL = "https://api.unsplash.com"

def _headers():
    return {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}

def _format_photo(p):
    return {"id": p["id"], "description": p.get("description") or p.get("alt_description") or "No description", "width": p.get("width"), "height": p.get("height"), "color": p.get("color", "#000000"), "urls": {"small": p["urls"]["small"], "regular": p["urls"]["regular"], "full": p["urls"]["full"]}, "links": {"download": p["links"]["download"], "html": p["links"]["html"]}, "photographer": {"name": p["user"]["name"], "username": p["user"]["username"], "profile": p["user"]["links"]["html"]}, "likes": p.get("likes", 0)}

def _handle_error(e):
    if isinstance(e, httpx.HTTPStatusError):
        s = e.response.status_code
        if s == 401: return "Error: Invalid API key."
        if s == 429: return "Error: Rate limit exceeded."
        return f"Error: status {s}."
    if isinstance(e, httpx.TimeoutException): return "Error: timeout."
    return f"Error: {type(e).__name__}: {e}"

class SearchPhotosInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(..., min_length=1, max_length=200)
    per_page: Optional[int] = Field(default=5, ge=1, le=10)
    order_by: Optional[str] = Field(default="relevant")
    orientation: Optional[str] = Field(default=None)

class PopularPhotosInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    per_page: Optional[int] = Field(default=5, ge=1, le=10)

class TriggerDownloadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    photo_id: str = Field(..., min_length=1)

@mcp.tool(name="unsplash_search_photos")
async def unsplash_search_photos(params: SearchPhotosInput) -> str:
    """Search Unsplash. For Baleares/Aura designs use Mediterranean context queries."""
    try:
        p = {"query": params.query, "per_page": params.per_page, "order_by": params.order_by}
        if params.orientation: p["orientation"] = params.orientation
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/search/photos", headers=_headers(), params=p, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
        photos = [_format_photo(x) for x in data.get("results", [])]
        if not photos: return f"No photos for '{params.query}'."
        return json.dumps({"query": params.query, "total": data.get("total", 0), "photos": photos}, indent=2, ensure_ascii=False)
    except Exception as e:
        return _handle_error(e)

@mcp.tool(name="unsplash_get_popular_photos")
async def unsplash_get_popular_photos(params: PopularPhotosInput) -> str:
    """Get trending photos on Unsplash."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/photos", headers=_headers(), params={"per_page": params.per_page, "order_by": "popular"}, timeout=15.0)
            resp.raise_for_status()
        return json.dumps({"photos": [_format_photo(p) for p in resp.json()]}, indent=2)
    except Exception as e:
        return _handle_error(e)

@mcp.tool(name="unsplash_trigger_download")
async def unsplash_trigger_download(params: TriggerDownloadInput) -> str:
    """Register download — required by Unsplash TOS."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/photos/{params.photo_id}/download", headers=_headers(), timeout=15.0)
            resp.raise_for_status()
        return json.dumps({"photo_id": params.photo_id, "status": "registered"}, indent=2)
    except Exception as e:
        return _handle_error(e)

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
        from starlette.responses import JSONResponse
        async def health(request):
            return JSONResponse({"status": "ok"})
        mcp_app = mcp.streamable_http_app()
        app = Starlette(routes=[Route("/", health), Route("/health", health), Mount("/mcp", app=mcp_app)])
        port = int(os.environ.get("PORT", 10000))
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        mcp.run()
