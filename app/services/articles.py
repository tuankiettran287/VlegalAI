from __future__ import annotations

import json
from typing import Any

from app.services.ai import QwenService
from app.services.tavily import TavilyService


class ArticleResearchService:
    def __init__(self, tavily: TavilyService, ai: QwenService):
        self.tavily = tavily
        self.ai = ai

    async def search(self, query: str) -> dict[str, Any]:
        results = await self.tavily.search(
            f"{query} pháp luật Việt Nam",
            max_results=10,
            include_raw_content=True,
            topic="general",
        )
        sources = [
            {
                "id": f"W{index}",
                "title": row.get("title") or "Nguồn web",
                "url": row.get("url"),
                "excerpt": (row.get("content") or "")[:700],
                "published_date": row.get("published_date"),
                "score": row.get("score", 0),
            }
            for index, row in enumerate(results, start=1)
        ]
        evidence = [
            {
                **source,
                "content": (row.get("raw_content") or row.get("content") or "")[:6500],
            }
            for source, row in zip(sources, results, strict=True)
        ]
        summary = await self.ai.complete(
            """Bạn là biên tập viên pháp lý Việt Nam. Tổng hợp kết quả tìm kiếm thành bản nghiên cứu ngắn.
Mọi thông tin phải gắn [W1], [W2] theo nguồn web. Phân biệt tin tức/bài phân tích với văn bản pháp luật;
không coi bài viết là căn cứ pháp lý chính thức và nêu ngày xuất bản nếu có.""",
            f"Chủ đề: {query}\nKết quả web:\n{json.dumps(evidence, ensure_ascii=False)}",
            max_tokens=1800,
            temperature=0.15,
        )
        return {"query": query, "summary": summary, "sources": sources}

