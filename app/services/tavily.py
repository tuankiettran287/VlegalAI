from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings


class TavilyError(RuntimeError):
    pass


class TavilyService:
    SEARCH_URL = "https://api.tavily.com/search"
    EXTRACT_URL = "https://api.tavily.com/extract"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def search(
        self,
        query: str,
        *,
        include_domains: list[str] | None = None,
        max_results: int = 8,
        include_raw_content: bool = True,
        topic: str = "general",
    ) -> list[dict[str, Any]]:
        if not self.settings.tavily_ready:
            raise TavilyError("TAVILY_API_KEY chưa được cấu hình")
        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "topic": topic,
            "search_depth": self.settings.tavily_search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": include_raw_content,
            "include_domains": include_domains or [],
        }
        async with httpx.AsyncClient(timeout=self.settings.tavily_timeout_seconds) as client:
            response = await client.post(self.SEARCH_URL, json=payload)
        if response.is_error:
            raise TavilyError(f"Tavily trả về HTTP {response.status_code}: {response.text[:300]}")
        return list(response.json().get("results") or [])

    async def extract(self, urls: list[str]) -> list[dict[str, Any]]:
        if not self.settings.tavily_ready:
            raise TavilyError("TAVILY_API_KEY chưa được cấu hình")
        payload = {
            "api_key": self.settings.tavily_api_key,
            "urls": urls,
            "extract_depth": "advanced",
            "include_images": False,
        }
        async with httpx.AsyncClient(timeout=self.settings.tavily_timeout_seconds) as client:
            response = await client.post(self.EXTRACT_URL, json=payload)
        if response.is_error:
            raise TavilyError(f"Tavily extract trả về HTTP {response.status_code}: {response.text[:300]}")
        return list(response.json().get("results") or [])

