#!/usr/bin/env python3
"""
Unsplash MCP Server — Baleares Edition
Runs as stdio (Cowork) or HTTP (claude.ai / Claude Design)
"""

import os
import json
import httpx
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("unsplash_mcp")

UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
BASE_URL = "https://api.unsplash.com"


def _headers() -> dict:
    return {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}


def _format_photo(p: dict) -> dict:
    return {
        "id": p["id"],
        "description": p.get("description") or p.get("alt_description") or "No description",
        "width": p.get("width"),
        "height": p.get("height"),
        "color": p.get("color", "#000000"),
        "urls": {
            "small": p["urls"]["small"],
            "regular": p["urls"]["regular"],
            "full": p["urls"]["full"],
        },
        "links": {
            "download": p["links"]["download"],
            "html": p["links"]["html"],
        },
        "photographer": {
            "name": p["user"]["name"],
            "username": p["user"]["username"],
            "profile": p["user"]["links"]["html"],
        },
        "likes": p.get("likes", 0),
    }


def _handle_error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 401:
            return "Error: Invalid Unsplash API key."
        if status == 429:
            return "Error: Rate limit exceeded. Wait before retrying."
        return f"Error: API returned status {status}."
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out."
    return f"Error: {type(e).__name__}: {e}"


class SearchPhotosInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(..., description="Search keywords in English, e.g. 'sailing Mediterranean Mallorca'", min_length=1, max_length=200)
    per_page: Optional[int] = Field(default=5, ge=1, le=10)
    order_by: Optional[str] = Field(default="relevant")
    orientation: Optional[str] = Field(default=None, description="'landscape', 'portrait', or 'squarish'")


class PopularPhotosInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    per_page: Optional[int] = Field(default=5, ge=1, le=10)


class TriggerDownloadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    photo_id: str = Field(..., min_length=1)


@mcp.tool(
    name="unsplash_search_photos",
    annotations={"title": "Search Unsplash Photos", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def unsplash_search_photos(params: SearchPhotosInput) -> str:
    """Search Unsplash for photos. Returns URLs, photographer credits, dominant color, and dimensions.

    Always use English queries. For Aura Concierge / Baleares designs, include Mediterranean context:
    e.g. 'sailing Mediterranean lifestyle Mallorca', 'luxury villa Mallorca sea view',
    'snorkeling turquoise water Balearic Islands', 'paddleboard Mediterranean sea lifestyle'.

    Prefer photos with:
    - Clean areas suitable for text overlay (sky, water, sand, blurred backgrounds)
    - Dominant colors: navy blue (#0c2040), sky blue (#a6d9f3), sand (#f5e6c8), turquoise (#4fa8b8)
    - Luxury lifestyle, minimalist, aspirational composition
    - Avoid: busy patterns, tropical greens, cold greys, crowded scenes
    """
    try:
        p = {"query": params.query, "per_page": params.per_page, "order_by": params.order_by}
        if params.orientation:
            p["orientation"] = params.orientation
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/search/photos", headers=_headers(), params=p, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
        photos = [_format_photo(x) for x in data.get("results", [])]
        if not photos:
            return f"No photos found for '{params.query}'. Try different keywords."
        return json.dumps({"query": params.query, "total_results": data.get("total", 0), "returned": len(photos), "photos": photos}, indent=2, ensure_ascii=False)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="unsplash_get_popular_photos",
    annotations={"title": "Get Trending Unsplash Photos", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def unsplash_get_popular_photos(params: PopularPhotosInput) -> str:
    """Get currently trending/popular photos on Unsplash."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/photos", headers=_headers(), params={"per_page": params.per_page, "order_by": "popular"}, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
        return json.dumps({"returned": len(data), "photos": [_format_photo(p) for p in data]}, indent=2, ensure_ascii=False)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="unsplash_trigger_download",
    annotations={"title": "Register Photo Download (TOS)", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def unsplash_trigger_download(params: TriggerDownloadInput) -> str:
    """Register a photo download — required by Unsplash TOS when using a photo in a design."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/photos/{params.photo_id}/download", headers=_headers(), timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
        return json.dumps({"photo_id": params.photo_id, "download_url": data.get("url", ""), "status": "registered"}, indent=2)
    except Exception as e:
        return _handle_error(e)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        port = int(os.environ.get("PORT", 8000))
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port, path="/mcp")
    else:
        mcp.run()
