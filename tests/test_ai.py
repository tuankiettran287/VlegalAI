from __future__ import annotations

import asyncio
import base64
import copy
import json
import time
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import AsyncMock

import httpx
import pytest
from google.auth.exceptions import DefaultCredentialsError

from app.core.config import Settings
from app.services import ai as ai_module
from app.services.ai import (
    VERTEX_SCOPE,
    GeminiError,
    GeminiService,
    _response_text,
    _vertex_response_schema,
)


MISSING_CREDENTIALS = "tests/definitely-missing-env.json"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "gemini_credentials_path": MISSING_CREDENTIALS,
        "gemini_max_retries": 1,
        "gemini_model": "gemini-2.5-flash",
        "gemini_location": "global",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _FakeCredentials:
    def __init__(
        self,
        *,
        valid: bool = True,
        token: str | None = "test-token",
        refreshed_token: str | None = "refreshed-token",
        refresh_error: Exception | None = None,
    ) -> None:
        self.valid = valid
        self.token = token
        self.refreshed_token = refreshed_token
        self.refresh_error = refresh_error
        self.refresh_count = 0

    def refresh(self, _: object) -> None:
        self.refresh_count += 1
        if self.refresh_error:
            raise self.refresh_error
        self.token = self.refreshed_token
        self.valid = True


def _mocked_service(
    handler: Callable[[httpx.Request], httpx.Response],
    **settings_overrides: object,
) -> tuple[GeminiService, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = GeminiService(_settings(**settings_overrides), client=client)
    service._credentials = _FakeCredentials()
    service._project_id = "test-project"
    return service, client


def test_vertex_response_schema_converts_nested_nullable_schema_without_mutation() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "source_url"],
        "properties": {
            "title": {
                "type": "string",
                "description": "Tiêu đề",
                "enum": ["A", "B"],
            },
            "source_url": {"type": ["string", "null"], "format": "uri"},
            "items": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0, "maximum": 10},
            },
        },
    }
    original = copy.deepcopy(schema)

    converted = _vertex_response_schema(schema)

    assert schema == original
    assert converted["type"] == "OBJECT"
    assert "additionalProperties" not in converted
    assert converted["required"] == ["title", "source_url"]
    assert converted["propertyOrdering"] == ["title", "source_url", "items"]
    assert converted["properties"]["source_url"] == {
        "type": "STRING",
        "nullable": True,
        "format": "uri",
    }
    assert converted["properties"]["title"]["enum"] == ["A", "B"]
    assert converted["properties"]["items"]["items"] == {
        "type": "INTEGER",
        "minimum": 0,
        "maximum": 10,
    }


def test_response_text_combines_visible_parts_and_ignores_thoughts() -> None:
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Kết quả "},
                        {"text": "không được lộ", "thought": True},
                        {"text": "hợp lệ."},
                    ]
                },
                "finishReason": "STOP",
            }
        ]
    }

    assert _response_text(payload) == "Kết quả hợp lệ."


def test_response_text_reports_prompt_feedback_when_no_candidate_exists() -> None:
    with pytest.raises(GeminiError, match="SAFETY"):
        _response_text(
            {
                "candidates": [],
                "promptFeedback": {"blockReason": "SAFETY"},
            }
        )


def test_response_text_reports_finish_reason_when_candidate_is_empty() -> None:
    with pytest.raises(GeminiError, match="MAX_TOKENS"):
        _response_text(
            {
                "candidates": [
                    {
                        "content": {"parts": []},
                        "finishReason": "MAX_TOKENS",
                    }
                ]
            }
        )


@pytest.mark.parametrize("finish_reason", ["MAX_TOKENS", "SAFETY", "RECITATION"])
def test_response_text_rejects_incomplete_or_blocked_finish_reason(
    finish_reason: str,
) -> None:
    with pytest.raises(GeminiError, match=finish_reason):
        _response_text(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Nội dung mới chỉ sinh được một phần"}]
                        },
                        "finishReason": finish_reason,
                    }
                ]
            }
        )


def test_response_text_normalizes_malformed_candidate_to_gemini_error() -> None:
    with pytest.raises(GeminiError):
        _response_text({"candidates": [None]})


def test_load_credentials_uses_service_account_scope_and_detected_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials_file = "tests/test_ai.py"
    credentials = SimpleNamespace(project_id="credential-project")
    captured: dict[str, Any] = {}

    def fake_load(path: object, *, scopes: list[str]) -> object:
        captured["path"] = path
        captured["scopes"] = scopes
        return credentials

    monkeypatch.setattr(
        ai_module.service_account.Credentials,
        "from_service_account_file",
        fake_load,
    )
    service = GeminiService(
        _settings(
            gemini_credentials_path=str(credentials_file),
            gemini_project_id="",
        )
    )
    try:
        loaded, project_id = service._load_credentials()
    finally:
        asyncio.run(service.close())

    assert loaded is credentials
    assert project_id == "credential-project"
    assert captured == {
        "path": service.settings.gemini_credentials_local_path,
        "scopes": [VERTEX_SCOPE],
    }


def test_configured_project_overrides_service_account_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials_file = "tests/test_ai.py"
    credentials = SimpleNamespace(project_id="credential-project")
    monkeypatch.setattr(
        ai_module.service_account.Credentials,
        "from_service_account_file",
        lambda *_args, **_kwargs: credentials,
    )
    service = GeminiService(
        _settings(
            gemini_credentials_path=str(credentials_file),
            gemini_project_id="configured-project",
        )
    )
    try:
        _, project_id = service._load_credentials()
    finally:
        asyncio.run(service.close())

    assert project_id == "configured-project"


@pytest.mark.parametrize(
    "load_error",
    [
        OSError("permission denied"),
        ValueError("invalid credential JSON"),
    ],
)
def test_service_account_load_errors_are_wrapped(
    monkeypatch: pytest.MonkeyPatch,
    load_error: Exception,
) -> None:
    def fail_load(*_: object, **__: object) -> object:
        raise load_error

    monkeypatch.setattr(
        ai_module.service_account.Credentials,
        "from_service_account_file",
        fail_load,
    )
    service = GeminiService(
        _settings(gemini_credentials_path="tests/test_ai.py")
    )
    try:
        with pytest.raises(GeminiError, match=str(load_error)):
            service._load_credentials()
    finally:
        asyncio.run(service.close())


def test_adc_uses_cloud_scope_and_detected_project(monkeypatch: pytest.MonkeyPatch) -> None:
    credentials = SimpleNamespace(project_id=None)
    captured: dict[str, object] = {}

    def fake_default(*, scopes: list[str]) -> tuple[object, str]:
        captured["scopes"] = scopes
        return credentials, "detected-project"

    monkeypatch.setattr(ai_module.google.auth, "default", fake_default)
    service = GeminiService(
        _settings(
            gemini_use_adc=True,
            gemini_project_id="",
        )
    )
    try:
        loaded_credentials, project_id = service._load_credentials()
    finally:
        asyncio.run(service.close())

    assert loaded_credentials is credentials
    assert project_id == "detected-project"
    assert captured["scopes"] == [VERTEX_SCOPE]


def test_readiness_accepts_adc_project_auto_detection() -> None:
    settings = _settings(gemini_use_adc=True, gemini_project_id="")

    assert settings.gemini_ready


def test_readiness_rejects_invalid_service_account_file() -> None:
    settings = _settings(
        gemini_credentials_path="tests/test_ai.py",
        gemini_use_adc=False,
    )

    assert not settings.gemini_ready


def test_load_credentials_wraps_adc_discovery_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_default(**_: object) -> tuple[object, str]:
        raise DefaultCredentialsError("ADC unavailable")

    monkeypatch.setattr(ai_module.google.auth, "default", fail_default)
    service = GeminiService(_settings(gemini_use_adc=True))
    try:
        with pytest.raises(GeminiError, match="ADC unavailable"):
            service._load_credentials()
    finally:
        asyncio.run(service.close())


def test_load_credentials_fails_without_file_or_adc() -> None:
    service = GeminiService(_settings(gemini_use_adc=False))
    try:
        with pytest.raises(GeminiError, match="Không tìm thấy"):
            service._load_credentials()
    finally:
        asyncio.run(service.close())


def test_load_credentials_requires_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ai_module.google.auth,
        "default",
        lambda **_: (SimpleNamespace(project_id=None), ""),
    )
    service = GeminiService(
        _settings(
            gemini_use_adc=True,
            gemini_project_id="",
        )
    )
    try:
        with pytest.raises(GeminiError, match="project_id"):
            service._load_credentials()
    finally:
        asyncio.run(service.close())


def test_concurrent_credential_initialization_loads_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GeminiService(_settings())
    credentials = _FakeCredentials()
    load_count = 0

    def fake_load() -> tuple[object, str]:
        nonlocal load_count
        load_count += 1
        time.sleep(0.02)
        return credentials, "test-project"

    monkeypatch.setattr(service, "_load_credentials", fake_load)

    async def scenario() -> None:
        loaded = await asyncio.gather(*(service._ensure_credentials() for _ in range(8)))
        assert all(item is credentials for item in loaded)
        await service.close()

    asyncio.run(scenario())

    assert load_count == 1
    assert service._project_id == "test-project"


def test_access_token_reuses_valid_token_without_refresh() -> None:
    service = GeminiService(_settings())
    credentials = _FakeCredentials(valid=True, token="cached-token")
    service._credentials = credentials

    async def scenario() -> str:
        try:
            return await service._access_token()
        finally:
            await service.close()

    assert asyncio.run(scenario()) == "cached-token"
    assert credentials.refresh_count == 0


def test_access_token_refreshes_invalid_credentials() -> None:
    service = GeminiService(_settings())
    credentials = _FakeCredentials(
        valid=False,
        token=None,
        refreshed_token="new-token",
    )
    service._credentials = credentials

    async def scenario() -> str:
        try:
            return await service._access_token()
        finally:
            await service.close()

    assert asyncio.run(scenario()) == "new-token"
    assert credentials.refresh_count == 1


def test_concurrent_access_token_requests_refresh_once() -> None:
    service = GeminiService(_settings())
    credentials = _FakeCredentials(
        valid=False,
        token=None,
        refreshed_token="shared-token",
    )
    service._credentials = credentials

    async def scenario() -> list[str]:
        try:
            return await asyncio.gather(
                *(service._access_token() for _ in range(8))
            )
        finally:
            await service.close()

    assert asyncio.run(scenario()) == ["shared-token"] * 8
    assert credentials.refresh_count == 1


def test_access_token_wraps_refresh_failure() -> None:
    service = GeminiService(_settings())
    credentials = _FakeCredentials(
        valid=False,
        token=None,
        refresh_error=RuntimeError("refresh failed"),
    )
    service._credentials = credentials

    async def scenario() -> None:
        try:
            with pytest.raises(GeminiError, match="refresh failed"):
                await service._access_token()
        finally:
            await service.close()

    asyncio.run(scenario())
    assert credentials.refresh_count == 1


def test_access_token_rejects_empty_token_after_refresh() -> None:
    service = GeminiService(_settings())
    credentials = _FakeCredentials(
        valid=False,
        token=None,
        refreshed_token=None,
    )
    service._credentials = credentials

    async def scenario() -> None:
        try:
            with pytest.raises(GeminiError, match="access token"):
                await service._access_token()
        finally:
            await service.close()

    asyncio.run(scenario())


def test_complete_calls_vertex_with_structured_output() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": '{"summary":"Hợp lệ"}'}],
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    async def scenario() -> dict[str, object]:
        service, client = _mocked_service(handler)
        try:
            return await service.complete_json(
                "Chỉ trả lời từ nguồn.",
                "Tóm tắt dữ liệu đã trích xuất.",
                schema={
                    "type": "object",
                    "required": ["summary"],
                    "properties": {"summary": {"type": "string"}},
                },
            )
        finally:
            await client.aclose()

    result = asyncio.run(scenario())

    assert result == {"summary": "Hợp lệ"}
    assert captured["url"] == (
        "https://aiplatform.googleapis.com/v1/projects/test-project/locations/global/"
        "publishers/google/models/gemini-2.5-flash:generateContent"
    )
    assert captured["authorization"] == "Bearer test-token"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["systemInstruction"]["parts"][0]["text"] == "Chỉ trả lời từ nguồn."
    assert payload["contents"][0]["parts"][0]["text"] == "Tóm tắt dữ liệu đã trích xuất."
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["generationConfig"]["responseSchema"]["type"] == "OBJECT"
    assert payload["generationConfig"]["thinkingConfig"] == {
        "thinkingBudget": 0,
        "includeThoughts": False,
    }


def test_gemini_37_payload_uses_supported_thinking_level() -> None:
    service = GeminiService(
        _settings(
            gemini_model="gemini-3.7-flash",
            gemini_thinking_level="minimal",
        )
    )
    try:
        payload = service._payload(
            "System instruction",
            "User question",
            temperature=0.1,
            max_tokens=1024,
            json_schema=None,
            thinking_level="minimal",
        )
    finally:
        asyncio.run(service.close())

    generation_config = payload["generationConfig"]
    assert "temperature" not in generation_config
    assert generation_config["thinkingConfig"] == {
        "thinkingLevel": "LOW",
        "includeThoughts": False,
    }


def test_extract_attachment_text_sends_inline_data_to_vertex() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Điều 1. Thời giờ làm việc"}]},
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    async def scenario() -> str:
        service, client = _mocked_service(handler)
        try:
            return await service.extract_attachment_text(
                b"\x89PNG\r\n\x1a\nimage",
                "image/png",
                "noi-quy.png",
            )
        finally:
            await client.aclose()

    assert asyncio.run(scenario()) == "Điều 1. Thời giờ làm việc"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    inline_data = payload["contents"][0]["parts"][1]["inlineData"]
    assert inline_data["mimeType"] == "image/png"
    assert base64.b64decode(inline_data["data"]).startswith(b"\x89PNG")
    assert payload["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0


@pytest.mark.parametrize(
    ("system", "user", "message"),
    [
        (" ", "Nội dung", "System instruction"),
        ("Hướng dẫn", "\n", "Nội dung"),
    ],
)
def test_complete_rejects_blank_prompts(system: str, user: str, message: str) -> None:
    service = GeminiService(_settings())

    async def scenario() -> None:
        try:
            with pytest.raises(GeminiError, match=message):
                await service.complete(system, user)
        finally:
            await service.close()

    asyncio.run(scenario())


def test_error_detail_prefers_google_message_and_truncates_plain_text() -> None:
    request = httpx.Request("POST", "https://example.test")
    google_error = httpx.Response(
        400,
        request=request,
        json={"error": {"message": "specific provider detail"}},
    )
    plain_error = httpx.Response(
        500,
        request=request,
        content=("x" * 1200).encode(),
    )

    assert GeminiService._error_detail(google_error) == "specific provider detail"
    assert GeminiService._error_detail(plain_error) == "x" * 800


def test_response_error_sanitizes_disabled_vertex_api_details() -> None:
    request = httpx.Request("POST", "https://aiplatform.googleapis.com")
    response = httpx.Response(
        403,
        request=request,
        json={
            "error": {
                "message": (
                    "API disabled for private-project. Enable it at "
                    "https://console.example/private-project"
                ),
                "status": "PERMISSION_DENIED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": "SERVICE_DISABLED",
                        "metadata": {
                            "consumer": "projects/private-project",
                            "service": "aiplatform.googleapis.com",
                            "activationUrl": "https://console.example/private-project",
                        },
                    }
                ],
            }
        },
    )

    error = GeminiService._response_error(response)

    assert "aiplatform.googleapis.com" in str(error)
    assert "private-project" not in str(error)
    assert "console.example" not in str(error)


def test_ensure_ready_probes_vertex_once_and_refreshes_unauthorized_token() -> None:
    attempts = 0
    authorization_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        authorization_headers.append(request.headers["Authorization"])
        assert request.url.path.endswith(":countTokens")
        assert json.loads(request.content) == {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "readiness"}],
                }
            ]
        }
        if attempts == 1:
            return httpx.Response(
                401,
                json={"error": {"message": "expired"}},
            )
        return httpx.Response(200, json={"totalTokens": 1})

    async def scenario() -> None:
        service, client = _mocked_service(handler)
        credentials = _FakeCredentials(
            valid=True,
            token="expired-token",
            refreshed_token="fresh-token",
        )
        service._credentials = credentials
        try:
            projects = await asyncio.gather(
                service.ensure_ready(),
                service.ensure_ready(),
                service.ensure_ready(),
            )
            assert projects == ["test-project"] * 3
            assert credentials.refresh_count == 1
        finally:
            await client.aclose()

    asyncio.run(scenario())

    assert attempts == 2
    assert authorization_headers == [
        "Bearer expired-token",
        "Bearer fresh-token",
    ]


@pytest.mark.parametrize("retryable_status", [408, 429, 500, 502, 503, 504])
def test_request_retries_retryable_status_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    retryable_status: int,
) -> None:
    attempts = 0
    sleep_delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                retryable_status,
                json={"error": {"message": "temporary"}},
            )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "ok"}]},
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    async def fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(ai_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(ai_module.random, "uniform", lambda *_: 0)

    async def scenario() -> str:
        service, client = _mocked_service(handler, gemini_max_retries=2)
        try:
            return await service.complete("Hướng dẫn", "Nội dung")
        finally:
            await client.aclose()

    assert asyncio.run(scenario()) == "ok"
    assert attempts == 2
    assert sleep_delays == [1]


def test_request_retries_network_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("network down", request=request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "recovered"}]},
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(ai_module.asyncio, "sleep", no_sleep)

    async def scenario() -> str:
        service, client = _mocked_service(handler, gemini_max_retries=2)
        try:
            return await service.complete("Hướng dẫn", "Nội dung")
        finally:
            await client.aclose()

    assert asyncio.run(scenario()) == "recovered"
    assert attempts == 2


def test_request_stops_after_transport_retry_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timed out", request=request)

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(ai_module.asyncio, "sleep", no_sleep)

    async def scenario() -> None:
        service, client = _mocked_service(handler, gemini_max_retries=3)
        try:
            with pytest.raises(GeminiError, match="timed out"):
                await service.complete("Hướng dẫn", "Nội dung")
        finally:
            await client.aclose()

    asyncio.run(scenario())
    assert attempts == 3


def test_request_stops_after_http_retry_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleep_delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": {"message": "still unavailable"}})

    async def fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(ai_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(ai_module.random, "uniform", lambda *_: 0)

    async def scenario() -> None:
        service, client = _mocked_service(handler, gemini_max_retries=3)
        try:
            with pytest.raises(GeminiError, match="still unavailable"):
                await service.complete("Hướng dẫn", "Nội dung")
        finally:
            await client.aclose()

    asyncio.run(scenario())
    assert attempts == 3
    assert sleep_delays == [1, 2]


def test_request_does_not_retry_non_retryable_400() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, json={"error": {"message": "invalid argument"}})

    async def scenario() -> None:
        service, client = _mocked_service(handler, gemini_max_retries=3)
        try:
            with pytest.raises(GeminiError, match="invalid argument"):
                await service.complete("Hướng dẫn", "Nội dung")
        finally:
            await client.aclose()

    asyncio.run(scenario())
    assert attempts == 1


def test_request_refreshes_token_after_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization_headers: list[str] = []
    credentials = _FakeCredentials(
        valid=True,
        token="expired-token",
        refreshed_token="fresh-token",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        authorization_headers.append(request.headers["Authorization"])
        if len(authorization_headers) == 1:
            return httpx.Response(401, json={"error": {"message": "expired"}})
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "authorized"}]},
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(ai_module.asyncio, "sleep", no_sleep)

    async def scenario() -> str:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = GeminiService(
            _settings(gemini_max_retries=2),
            client=client,
        )
        service._credentials = credentials
        service._project_id = "test-project"
        try:
            return await service.complete("Hướng dẫn", "Nội dung")
        finally:
            await client.aclose()

    assert asyncio.run(scenario()) == "authorized"
    assert authorization_headers == [
        "Bearer expired-token",
        "Bearer fresh-token",
    ]
    assert credentials.refresh_count == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json=[]),
    ],
)
def test_request_rejects_invalid_success_payload(response: httpx.Response) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return response

    async def scenario() -> None:
        service, client = _mocked_service(handler)
        try:
            with pytest.raises(GeminiError, match="không hợp lệ"):
                await service.complete("Hướng dẫn", "Nội dung")
        finally:
            await client.aclose()

    asyncio.run(scenario())


def test_complete_json_accepts_fenced_json_object() -> None:
    service = GeminiService(_settings())
    service.complete = AsyncMock(
        return_value='```json\n{"summary": "Hợp lệ"}\n```'
    )

    async def scenario() -> dict[str, Any]:
        try:
            return await service.complete_json(
                "Hướng dẫn",
                "Nội dung",
                schema={
                    "type": "object",
                    "required": ["summary"],
                    "properties": {"summary": {"type": "string"}},
                },
            )
        finally:
            await service.close()

    assert asyncio.run(scenario()) == {"summary": "Hợp lệ"}


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not-json", "JSON hợp lệ"),
        ('["not", "an", "object"]', "JSON object"),
    ],
)
def test_complete_json_rejects_invalid_or_non_object_output(
    content: str,
    message: str,
) -> None:
    service = GeminiService(_settings())
    service.complete = AsyncMock(return_value=content)

    async def scenario() -> None:
        try:
            with pytest.raises(GeminiError, match=message):
                await service.complete_json(
                    "Hướng dẫn",
                    "Nội dung",
                    schema={"type": "object"},
                )
        finally:
            await service.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "model_output",
    [
        '{"confidence": 0.9}',
        '{"status": 123, "confidence": 0.9}',
        '{"status": "NOT_A_STATUS", "confidence": 0.9}',
        '{"status": "IN_FORCE", "confidence": 2, "unexpected": true}',
        '{"status": "IN_FORCE", "confidence": NaN}',
        '{"status": "IN_FORCE", "confidence": Infinity}',
    ],
)
def test_complete_json_validates_parsed_object_against_schema(
    model_output: str,
) -> None:
    service = GeminiService(_settings())
    service.complete = AsyncMock(return_value=model_output)

    async def scenario() -> None:
        try:
            with pytest.raises(GeminiError, match="schema"):
                await service.complete_json(
                    "Hướng dẫn",
                    "Nội dung",
                    schema={
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["status", "confidence"],
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": ["IN_FORCE", "EXPIRED"],
                            },
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                    },
                )
        finally:
            await service.close()

    asyncio.run(scenario())


def test_google_search_uses_grounding_tool_and_deterministic_config() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Kết quả có căn cứ."}]},
                        "finishReason": "STOP",
                        "groundingMetadata": {
                            "webSearchQueries": ["văn bản pháp luật mới nhất"],
                            "groundingChunks": [],
                        },
                    }
                ]
            },
        )

    async def scenario() -> dict[str, object]:
        service, client = _mocked_service(handler)
        try:
            return await service.search_google("văn bản pháp luật mới nhất")
        finally:
            await client.aclose()

    result = asyncio.run(scenario())

    assert result["candidates"][0]["groundingMetadata"]["webSearchQueries"]
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["tools"] == [{"googleSearch": {}}]
    assert payload["generationConfig"] == {
        "temperature": 0,
        "maxOutputTokens": 16384,
        "thinkingConfig": {
            "thinkingBudget": 0,
            "includeThoughts": False,
        },
    }
    assert "tối đa 120 từ" in payload["systemInstruction"]["parts"][0]["text"]


def test_google_search_rejects_blank_query() -> None:
    service = GeminiService(_settings())

    async def scenario() -> None:
        try:
            with pytest.raises(GeminiError, match="không được để trống"):
                await service.search_google(" \n ")
        finally:
            await service.close()

    asyncio.run(scenario())


def test_generation_semaphore_limits_google_search_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GeminiService(
        _settings(gemini_max_concurrent_generations=1)
    )
    active = 0
    maximum_active = 0

    async def fake_request(_: dict[str, Any]) -> dict[str, Any]:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0)
        active -= 1
        return {"candidates": [{"finishReason": "STOP"}]}

    monkeypatch.setattr(service, "_request_payload", fake_request)

    async def scenario() -> None:
        try:
            await asyncio.gather(
                service.search_google("truy vấn 1"),
                service.search_google("truy vấn 2"),
                service.search_google("truy vấn 3"),
            )
        finally:
            await service.close()

    asyncio.run(scenario())

    assert maximum_active == 1


def test_close_closes_only_owned_http_client() -> None:
    async def scenario() -> None:
        owned_service = GeminiService(_settings())
        owned_client = owned_service._client
        await owned_service.close()
        await owned_service.close()
        assert owned_client.is_closed

        external_client = httpx.AsyncClient()
        external_service = GeminiService(_settings(), client=external_client)
        await external_service.close()
        assert not external_client.is_closed
        await external_client.aclose()

    asyncio.run(scenario())
