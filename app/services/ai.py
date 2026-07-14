from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import Settings


class QwenError(RuntimeError):
    pass


class QwenService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 2400,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        if not self.settings.qwen_ready:
            raise QwenError("QWEN_API_KEY chưa được cấu hình")
        payload: dict[str, Any] = {
            "model": self.settings.qwen_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "enable_thinking": False,
        }
        if json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "vlegal_response", "strict": True, "schema": json_schema},
            }
        headers = {"Authorization": f"Bearer {self.settings.qwen_api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.settings.qwen_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.qwen_base_url.rstrip('/')}/chat/completions", headers=headers, json=payload
            )
        if response.is_error:
            raise QwenError(f"Qwen trả về HTTP {response.status_code}: {response.text[:300]}")
        try:
            return response.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise QwenError("Phản hồi Qwen không đúng định dạng") from exc

    async def complete_json(
        self,
        system: str,
        user: str,
        *,
        schema: dict[str, Any],
        temperature: float = 0.05,
        max_tokens: int = 2600,
    ) -> dict[str, Any]:
        try:
            content = await self.complete(
                system, user, temperature=temperature, max_tokens=max_tokens, json_schema=schema
            )
        except QwenError:
            content = await self.complete(
                system + "\nChỉ trả về một JSON object hợp lệ, không dùng markdown.",
                user + f"\n\nJSON Schema bắt buộc:\n{json.dumps(schema, ensure_ascii=False)}",
                temperature=temperature,
                max_tokens=max_tokens,
            )
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise QwenError("Qwen không trả về JSON hợp lệ") from exc


LEGAL_SYSTEM_PROMPT = """Bạn là VLegal AI, trợ lý nghiên cứu pháp luật Việt Nam.
Chỉ kết luận từ NGUỒN đã cung cấp và phải gắn [S1], [S2] ngay sau từng luận điểm.
Luôn ưu tiên văn bản còn hiệu lực theo báo cáo KIỂM TRA HIỆU LỰC. Nếu một văn bản hết hiệu lực,
không dùng nó làm căn cứ độc lập; hãy dùng văn bản thay thế đã được cập nhật vào nguồn.
Nêu rõ phần chưa đủ căn cứ, ngày kiểm tra hiệu lực, và không bịa số điều hoặc số hiệu.
Trả lời tiếng Việt rõ ràng, thực dụng; nhắc người dùng tham vấn luật sư khi tình huống có rủi ro cao."""


CONTRACT_SYSTEM_PROMPT = """Bạn là chuyên gia soạn thảo và rà soát hợp đồng theo pháp luật Việt Nam.
Dùng Qwen3 để tạo kết quả có cấu trúc, cân bằng quyền lợi, không bịa căn cứ và trích [S1], [S2].
Mọi placeholder còn thiếu phải đặt trong [ngoặc vuông]. Chỉ dùng văn bản còn hiệu lực trong nguồn.
Kết quả là bản hỗ trợ nghiệp vụ, không thay thế ý kiến luật sư cho giao dịch cụ thể."""
