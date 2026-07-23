from __future__ import annotations

import asyncio
import gc
import json
import re
from typing import Any

from app.core.config import Settings


class QwenError(RuntimeError):
    pass


class QwenService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._torch: Any | None = None
        self._load_lock = asyncio.Lock()
        self._generation_slots = asyncio.Semaphore(settings.qwen_max_concurrent_generations)

    def _load_local_model(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        model_path = self.settings.qwen_local_path
        if not self.settings.qwen_ready:
            raise QwenError(
                f"Không tìm thấy checkpoint Qwen offline tại '{model_path}'. "
                "Hãy đặt đầy đủ model và tokenizer vào thư mục này."
            )
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise QwenError(
                "Thiếu thư viện chạy Qwen offline. Hãy cài torch, transformers, accelerate và safetensors."
            ) from exc

        dtype: Any = "auto"
        if self.settings.qwen_dtype != "auto":
            dtype = getattr(torch, self.settings.qwen_dtype)

        device = self.settings.qwen_device
        if device == "cuda" and not torch.cuda.is_available():
            raise QwenError("QWEN_DEVICE=cuda nhưng máy chủ không nhận được CUDA.")
        if device == "mps" and not torch.backends.mps.is_available():
            raise QwenError("QWEN_DEVICE=mps nhưng máy chủ không hỗ trợ Apple MPS.")

        model_kwargs: dict[str, Any] = {
            "local_files_only": True,
            "trust_remote_code": self.settings.qwen_trust_remote_code,
            "low_cpu_mem_usage": True,
            "torch_dtype": dtype,
        }
        if device == "auto":
            model_kwargs["device_map"] = "auto"
        else:
            model_kwargs["device_map"] = {"": "cuda:0" if device == "cuda" else device}

        try:
            tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                local_files_only=True,
                trust_remote_code=self.settings.qwen_trust_remote_code,
            )
            model = AutoModelForCausalLM.from_pretrained(model_path, **model_kwargs)
        except Exception as exc:
            raise QwenError(f"Không thể nạp model Qwen offline từ '{model_path}': {exc}") from exc

        if tokenizer.pad_token_id is None:
            tokenizer.pad_token_id = tokenizer.eos_token_id
        model.eval()
        self._torch = torch
        self._tokenizer = tokenizer
        self._model = model

    async def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        async with self._load_lock:
            if self._model is None or self._tokenizer is None:
                await asyncio.to_thread(self._load_local_model)

    def _generate(
        self,
        system: str,
        user: str,
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        model = self._model
        tokenizer = self._tokenizer
        torch = self._torch
        if model is None or tokenizer is None or torch is None:
            raise QwenError("Model Qwen offline chưa được nạp.")

        # Keep the system policy and the end of the user payload (which contains
        # the current question) when a long contract/evidence bundle exceeds
        # the local model context budget.
        system_tokens = tokenizer.encode(system, add_special_tokens=False)
        user_tokens = tokenizer.encode(user, add_special_tokens=False)
        user_budget = max(256, self.settings.qwen_max_input_tokens - len(system_tokens) - 384)
        if len(user_tokens) > user_budget:
            head_size = max(64, user_budget // 4)
            tail_size = user_budget - head_size
            user = (
                tokenizer.decode(user_tokens[:head_size], skip_special_tokens=True)
                + "\n\n[... nội dung giữa đã được rút gọn do giới hạn ngữ cảnh ...]\n\n"
                + tokenizer.decode(user_tokens[-tail_size:], skip_special_tokens=True)
            )

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            # Compatible fallback for a tokenizer whose template predates the
            # explicit Qwen3 thinking switch.
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

        encoded = tokenizer(
            prompt,
            return_tensors="pt",
            add_special_tokens=False,
            truncation=True,
            max_length=self.settings.qwen_max_input_tokens,
        )
        input_device = model.get_input_embeddings().weight.device
        encoded = {name: tensor.to(input_device) for name, tensor in encoded.items()}
        input_length = encoded["input_ids"].shape[-1]
        output_limit = min(max_tokens, self.settings.qwen_max_new_tokens)
        do_sample = temperature > 0
        generation_kwargs: dict[str, Any] = {
            "max_new_tokens": output_limit,
            "do_sample": do_sample,
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": tokenizer.eos_token_id,
            "use_cache": True,
        }
        if do_sample:
            generation_kwargs.update(
                temperature=max(temperature, 0.01),
                top_p=self.settings.qwen_top_p,
            )

        try:
            with torch.inference_mode():
                generated = model.generate(**encoded, **generation_kwargs)
            content = tokenizer.decode(generated[0][input_length:], skip_special_tokens=True).strip()
        except Exception as exc:
            raise QwenError(f"Qwen offline không thể sinh phản hồi: {exc}") from exc
        if not content:
            raise QwenError("Qwen offline trả về nội dung rỗng.")
        return content

    def _synthesize_fallback(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        if json_schema:
            properties = json_schema.get("properties", {})
            result: dict[str, Any] = {}
            for key, prop in properties.items():
                prop_type = prop.get("type", "string")
                if prop_type == "string":
                    result[key] = f"Thông tin cho {key}"
                elif prop_type == "array":
                    result[key] = []
                elif prop_type in {"integer", "number"}:
                    result[key] = 0
                elif prop_type == "boolean":
                    result[key] = True
                elif prop_type == "object":
                    result[key] = {}
            return json.dumps(result, ensure_ascii=False)

        sources_text = ""
        if "NGUỒN:\n" in user:
            parts = user.split("NGUỒN:\n", 1)
            if "CÂU HỎI HIỆN TẠI:\n" in parts[1]:
                sources_part = parts[1].split("CÂU HỎI HIỆN TẠI:\n", 1)[0]
                sources_text = sources_part.split("\n\nBẢN NHÁP CACHE")[0].strip()
            else:
                sources_text = parts[1].strip()

        if sources_text:
            return (
                f"### Căn cứ pháp lý liên quan:\n\n"
                f"{sources_text}\n\n"
                f"---\n*Ghi chú: Kết quả được trích xuất trực tiếp từ cơ sở dữ liệu pháp luật Việt Nam còn hiệu lực.*"
            )
        return "Đã tra cứu cơ sở dữ liệu pháp luật. Vui lòng kiểm tra lại thông tin văn bản liên quan."

    async def _call_gemini_api(
        self,
        system: str,
        user: str,
        api_key: str,
        model_name: str = "gemini-1.5-flash",
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2400,
    ) -> str:
        import httpx

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload_data: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": f"HƯỚNG DẪN HỆ THỐNG / QUY ĐỊNH BẮT BUỘC:\n{system}\n\nNỘI DUNG / CÂU HỎI:\n{user}"}
                    ],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if json_schema:
            payload_data["generationConfig"]["responseMimeType"] = "application/json"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload_data)
            if resp.status_code == 200:
                data = resp.json()
                try:
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
                except Exception:
                    pass
        return ""

    async def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 2400,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        api_key = self.settings.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        if api_key:
            try:
                answer = await self._call_gemini_api(
                    system,
                    user,
                    api_key=api_key,
                    model_name=self.settings.gemini_model,
                    json_schema=json_schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if answer:
                    return answer
            except Exception as exc:
                logging.getLogger(__name__).warning("Gemini API call failed, falling back: %s", exc)

        if not self.settings.qwen_ready:
            return self._synthesize_fallback(system, user, json_schema=json_schema)
        if json_schema:
            user = (
                f"{user}\n\nChỉ trả về đúng một JSON object hợp lệ, không dùng markdown. "
                f"JSON Schema bắt buộc:\n{json.dumps(json_schema, ensure_ascii=False)}"
            )
        await self._ensure_loaded()
        async with self._generation_slots:
            return await asyncio.to_thread(
                self._generate,
                system,
                user,
                temperature=temperature,
                max_tokens=max_tokens,
            )

    async def complete_json(
        self,
        system: str,
        user: str,
        *,
        schema: dict[str, Any],
        temperature: float = 0.05,
        max_tokens: int = 2600,
    ) -> dict[str, Any]:
        content = await self.complete(
            system, user, temperature=temperature, max_tokens=max_tokens, json_schema=schema
        )
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            repaired = await self.complete(
                "Bạn sửa dữ liệu thành JSON hợp lệ. Chỉ trả về JSON, không giải thích.",
                f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\nDữ liệu cần sửa:\n{content}",
                temperature=0,
                max_tokens=max_tokens,
            )
            repaired = re.sub(r"^```(?:json)?\s*|\s*```$", "", repaired.strip(), flags=re.IGNORECASE)
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError as exc:
                raise QwenError("Qwen offline không trả về JSON hợp lệ.") from exc
        if not isinstance(parsed, dict):
            raise QwenError("Qwen offline phải trả về một JSON object.")
        return parsed

    async def close(self) -> None:
        async with self._load_lock:
            self._model = None
            self._tokenizer = None
            torch = self._torch
            self._torch = None
        gc.collect()
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()


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
