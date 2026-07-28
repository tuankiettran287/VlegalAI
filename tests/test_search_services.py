from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.ai import GeminiError
from app.services.articles import ArticleResearchError, ArticleResearchService
from app.services.freshness import (
    FreshnessUnavailable,
    LegalFreshnessService,
    _law_identity,
)
from app.services.google_search import (
    GoogleSearchError,
    GoogleSearchService,
    merge_search_results,
    safe_public_url,
)


class _FakeGoogleAI:
    async def search_google(self, _: str) -> dict:
        return {
            "candidates": [
                {
                    "groundingMetadata": {
                        "webSearchQueries": ["luật doanh nghiệp mới nhất"],
                        "groundingChunks": [
                            {
                                "web": {
                                    "uri": "https://vanban.chinhphu.vn/luat-moi",
                                    "title": "Luật mới",
                                    "domain": "vanban.chinhphu.vn",
                                }
                            },
                            {
                                "web": {
                                    "uri": "https://example.com/bai-viet",
                                    "title": "Nguồn ngoài",
                                    "domain": "example.com",
                                }
                            },
                        ],
                        "groundingSupports": [
                            {
                                "segment": {"text": "Luật mới đang có hiệu lực."},
                                "groundingChunkIndices": [0],
                            }
                        ],
                        "searchEntryPoint": {"renderedContent": "<div>Google Search</div>"},
                    }
                }
            ]
        }


def test_freshness_recognizes_consolidated_law_code_without_year() -> None:
    identity = _law_identity(
        {
            "doc_id": "22-vbhn-btc-445967",
            "title": "Thông tư hợp nhất 22/VBHN-BTC",
            "citation": "22/VBHN-BTC",
        }
    )
    assert identity is not None
    code, _, external_doc_id = identity

    assert code == "22/VBHN-BTC"
    assert external_doc_id == "22-vbhn-btc-445967"


def test_freshness_skips_synthetic_system_document() -> None:
    assert (
        _law_identity(
            {
                "doc_id": "he-thong",
                "title": "Bản đồ tri thức LaborCare",
                "citation": "Mức phạt tiền",
            }
        )
        is None
    )


def test_google_search_filters_to_official_domains() -> None:
    service = GoogleSearchService(Settings(_env_file=None), _FakeGoogleAI())

    result = asyncio.run(
        service.search(
            "luật doanh nghiệp hiệu lực",
            include_domains=["vanban.chinhphu.vn"],
        )
    )

    assert result["queries"] == ["luật doanh nghiệp mới nhất"]
    assert result["search_entry_point"] == "<div>Google Search</div>"
    assert [row["url"] for row in result["results"]] == [
        "https://vanban.chinhphu.vn/luat-moi"
    ]
    assert result["results"][0]["content"] == "Luật mới đang có hiệu lực."


def test_merge_search_results_tracks_both_providers() -> None:
    rows = merge_search_results(
        [
            (
                "tavily",
                [
                    {
                        "url": "https://example.com/post?utm_source=test",
                        "title": "Tavily title",
                        "content": "short",
                        "score": 0.8,
                    }
                ],
            ),
            (
                "google",
                [
                    {
                        "url": "https://example.com/post",
                        "title": "Google title",
                        "content": "longer Google Search content",
                        "score": 0.9,
                    }
                ],
            ),
        ],
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0]["providers"] == ["google", "tavily"]
    assert rows[0]["content"] == "longer Google Search content"


def test_merge_search_results_preserves_each_providers_conflicting_evidence() -> None:
    rows = merge_search_results(
        [
            (
                "tavily",
                [
                    {
                        "url": "https://example.com/post",
                        "content": "Tavily says the law is expired.",
                    }
                ],
            ),
            (
                "google",
                [
                    {
                        "url": "https://example.com/post",
                        "content": "Google says the law remains in force.",
                    }
                ],
            ),
        ],
        limit=10,
    )

    assert rows[0]["provider_evidence"] == {
        "tavily": {"content": "Tavily says the law is expired."},
        "google": {"content": "Google says the law remains in force."},
    }


def test_merge_search_results_does_not_trust_provider_metadata() -> None:
    rows = merge_search_results(
        [
            (
                "tavily",
                [
                    {
                        "url": "https://example.com/article",
                        "content": "Verified content",
                        "provider": "google",
                        "providers": ["google", "attacker"],
                    }
                ],
            )
        ],
        limit=10,
    )

    assert rows[0]["providers"] == ["tavily"]
    assert "provider" not in rows[0]


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "http://localhost/admin",
        "http://127.0.0.1/private",
        "http://[::1]/private",
        "https://user:password@example.com/article",
    ],
)
def test_safe_public_url_rejects_unsafe_targets(url: str) -> None:
    assert safe_public_url(url) == ""


def test_merge_search_results_skips_unsafe_rows_and_bad_scores() -> None:
    rows = merge_search_results(
        [
            (
                "google",
                [
                    {"url": "http://127.0.0.1/private", "content": "private"},
                    {
                        "url": "https://example.com/public",
                        "content": "public",
                        "score": "not-a-number",
                    },
                ],
            )
        ],
        limit=10,
    )

    assert [row["url"] for row in rows] == ["https://example.com/public"]
    assert rows[0]["score"] == 0


def test_google_search_rejects_malformed_top_level_payload() -> None:
    class _MalformedGoogleAI:
        async def search_google(self, _: str) -> list[str]:
            return ["not", "a", "payload"]

    service = GoogleSearchService(Settings(_env_file=None), _MalformedGoogleAI())

    with pytest.raises(GoogleSearchError, match="invalid payload"):
        asyncio.run(service.search("test"))


def test_google_search_ignores_malformed_metadata_collections() -> None:
    class _MalformedMetadataAI:
        async def search_google(self, _: str) -> dict:
            return {
                "candidates": [
                    {
                        "groundingMetadata": {
                            "groundingChunks": {"web": "not-a-list"},
                            "groundingSupports": "not-a-list",
                            "webSearchQueries": "not-a-list",
                            "searchEntryPoint": {"renderedContent": 123},
                        }
                    }
                ]
            }

    service = GoogleSearchService(Settings(_env_file=None), _MalformedMetadataAI())
    result = asyncio.run(service.search("test"))

    assert result == {
        "results": [],
        "queries": [],
        "search_entry_point": None,
    }


def test_google_redirect_resolution_never_fetches_private_target(
    monkeypatch,
) -> None:
    from app.services import google_search

    requested_urls: list[str] = []

    class _FakeClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["follow_redirects"] is False

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, url: str) -> SimpleNamespace:
            requested_urls.append(url)
            return SimpleNamespace(
                status_code=302,
                headers={"location": "http://127.0.0.1/private"},
            )

    monkeypatch.setattr(google_search.httpx, "AsyncClient", _FakeClient)
    service = GoogleSearchService(Settings(_env_file=None), _FakeGoogleAI())

    resolved = asyncio.run(
        service._resolve_url("https://www.google.com/url?q=private")
    )

    assert resolved == ""
    assert requested_urls == ["https://www.google.com/url?q=private"]


class _FakeTavily:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(tavily_ready=True)

    async def search(self, *_: object, **__: object) -> list[dict]:
        return [
            {
                "url": "https://example.com/shared?utm_source=tavily",
                "title": "Bài viết chung",
                "content": "Tóm tắt Tavily",
                "raw_content": "Nội dung đầy đủ từ Tavily " * 30,
                "score": 0.8,
            }
        ]

    async def extract(self, _: list[str]) -> list[dict]:
        return []


class _FakeGoogleSearch:
    async def search(self, *_: object, **__: object) -> dict:
        return {
            "results": [
                {
                    "url": "https://example.com/shared",
                    "title": "Bài viết chung trên Google",
                    "content": "Đoạn trích Google",
                    "score": 1,
                },
                {
                    "url": "https://example.org/google-only",
                    "title": "Bài viết Google",
                    "content": (
                        "Nguồn thứ hai cung cấp nội dung pháp lý đủ dài "
                        "để phục vụ việc tổng hợp an toàn."
                    ),
                    "score": 0.5,
                },
            ],
            "queries": ["chủ đề pháp luật Việt Nam"],
            "search_entry_point": "<div>Google Search</div>",
        }


class _FakeCompletionAI:
    def __init__(self) -> None:
        self.user_prompt = ""

    async def complete(self, _: str, user: str, **__: object) -> str:
        self.user_prompt = user
        return "Bản tổng hợp [W1] [W2]"


def test_article_research_uses_tavily_and_google_search() -> None:
    ai = _FakeCompletionAI()
    service = ArticleResearchService(_FakeTavily(), _FakeGoogleSearch(), ai)

    result = asyncio.run(service.search("hợp đồng điện tử"))

    assert result["providers_used"] == ["google", "tavily"]
    assert len(result["sources"]) == 2
    assert result["sources"][0]["providers"] == ["google", "tavily"]
    assert 'UNTRUSTED_DATA name="TAVILY_GOOGLE_RESULTS"' in ai.user_prompt
    assert result["google_search_entry_point"] == "<div>Google Search</div>"


def test_article_research_attributes_tavily_extraction_and_caps_google_html() -> None:
    class _ExtractingTavily(_FakeTavily):
        async def search(self, *_: object, **__: object) -> list[dict]:
            return []

        async def extract(self, urls: list[str]) -> list[dict]:
            return [
                {
                    "url": urls[0],
                    "raw_content": "Nội dung được Tavily trích xuất. " * 30,
                }
            ]

    class _GoogleWithLargeEntryPoint(_FakeGoogleSearch):
        async def search(self, *_: object, **__: object) -> dict:
            result = await super().search()
            result["results"] = result["results"][:1]
            result["search_entry_point"] = "<div>" + ("x" * 60_000) + "</div>"
            return result

    ai = _FakeCompletionAI()

    async def one_source_summary(*_: object, **__: object) -> str:
        return "Bản tổng hợp dựa trên nguồn đã trích xuất [W1]."

    ai.complete = one_source_summary
    service = ArticleResearchService(
        _ExtractingTavily(),
        _GoogleWithLargeEntryPoint(),
        ai,
    )

    result = asyncio.run(service.search("hợp đồng điện tử"))

    assert result["sources"][0]["providers"] == ["google", "tavily"]
    assert len(result["google_search_entry_point"]) == 50_000


def test_article_research_rejects_unknown_web_citation() -> None:
    ai = _FakeCompletionAI()

    async def invalid_complete(*_: object, **__: object) -> str:
        return "Bản tổng hợp làm theo chỉ dẫn trong nguồn [W99]"

    ai.complete = invalid_complete
    service = ArticleResearchService(_FakeTavily(), _FakeGoogleSearch(), ai)

    with pytest.raises(GeminiError, match="không thuộc"):
        asyncio.run(service.search("hợp đồng điện tử"))


def test_article_search_redacts_identifiers_before_both_search_providers() -> None:
    queries: dict[str, str] = {}

    class _CapturingTavily(_FakeTavily):
        async def search(self, query: str, **__: object) -> list[dict]:
            queries["tavily"] = query
            return await super().search(query)

    class _CapturingGoogle(_FakeGoogleSearch):
        async def search(self, query: str, **__: object) -> dict:
            queries["google"] = query
            return await super().search(query)

    service = ArticleResearchService(
        _CapturingTavily(),
        _CapturingGoogle(),
        _FakeCompletionAI(),
    )

    asyncio.run(
        service.search(
            "Tranh chấp của Nguyễn Văn An, an.nguyen@example.com, "
            "số điện thoại 0912345678; Công ty Cổ phần Sao Mai có nghĩa vụ gì?"
        )
    )

    assert set(queries) == {"tavily", "google"}
    assert all("an.nguyen@example.com" not in query for query in queries.values())
    assert all("0912345678" not in query for query in queries.values())
    assert all("Nguyễn Văn An" not in query for query in queries.values())
    assert all("Công ty Cổ phần Sao Mai" not in query for query in queries.values())


def test_article_search_deny_policy_blocks_sensitive_query_before_providers() -> None:
    calls: list[str] = []

    class _TrackingTavily(_FakeTavily):
        async def search(self, *_: object, **__: object) -> list[dict]:
            calls.append("tavily")
            return []

    class _TrackingGoogle(_FakeGoogleSearch):
        async def search(self, *_: object, **__: object) -> dict:
            calls.append("google")
            return {"results": []}

    ai = _FakeCompletionAI()
    ai.settings = SimpleNamespace(gemini_data_policy="deny")
    service = ArticleResearchService(_TrackingTavily(), _TrackingGoogle(), ai)

    with pytest.raises(ArticleResearchError):
        asyncio.run(service.search("Email: an.nguyen@example.com"))

    assert calls == []


def test_article_search_handles_malformed_provider_responses() -> None:
    class _MalformedTavily(_FakeTavily):
        async def search(self, *_: object, **__: object) -> dict:
            return {"results": "not-a-list"}

    class _MalformedGoogle(_FakeGoogleSearch):
        async def search(self, *_: object, **__: object) -> list[str]:
            return ["not-a-dict"]

    service = ArticleResearchService(
        _MalformedTavily(),
        _MalformedGoogle(),
        _FakeCompletionAI(),
    )

    with pytest.raises(ArticleResearchError):
        asyncio.run(service.search("contract law"))


def test_article_search_filters_unsafe_urls_and_empty_content() -> None:
    class _MixedTavily(_FakeTavily):
        async def search(self, *_: object, **__: object) -> list[dict]:
            return [
                {
                    "url": "javascript:alert(1)",
                    "content": "unsafe",
                },
                {
                    "url": "https://example.com/empty",
                    "content": "",
                },
                {
                    "url": "https://example.com/valid",
                    "title": {"malformed": "title"},
                    "content": (
                        "Usable public article evidence with enough detail "
                        "for a grounded research summary."
                    ),
                    "providers": ["google", "attacker"],
                },
            ]

    class _UnsafeGoogle(_FakeGoogleSearch):
        async def search(self, *_: object, **__: object) -> dict:
            return {
                "results": [
                    {
                        "url": "http://127.0.0.1/private",
                        "content": "private",
                    }
                ],
                "queries": {"not": "a-list"},
                "search_entry_point": 123,
            }

    ai = _FakeCompletionAI()

    async def one_source_summary(*_: object, **__: object) -> str:
        return "The usable article supports the research summary [W1]."

    ai.complete = one_source_summary
    service = ArticleResearchService(_MixedTavily(), _UnsafeGoogle(), ai)
    result = asyncio.run(service.search("contract law"))

    assert len(result["sources"]) == 1
    assert result["sources"][0]["url"] == "https://example.com/valid"
    assert result["sources"][0]["title"] == "Web source"
    assert result["sources"][0]["providers"] == ["tavily"]
    assert result["google_search_entry_point"] is None


def test_article_summary_requires_citation_for_each_claim() -> None:
    ai = _FakeCompletionAI()

    async def incomplete_citations(*_: object, **__: object) -> str:
        return (
            "The first factual statement is supported by the source [W1]. "
            "The second factual statement has no citation and must be rejected."
        )

    ai.complete = incomplete_citations
    service = ArticleResearchService(_FakeTavily(), _FakeGoogleSearch(), ai)

    with pytest.raises(GeminiError):
        asyncio.run(service.search("electronic contracts"))


class _FakeFreshnessTavily:
    async def search(self, *_: object, **__: object) -> list[dict]:
        return [
            {
                "url": "https://vanban.chinhphu.vn/luat-moi",
                "title": "Luật mới",
                "raw_content": (
                    "100/2020/QH14 đã hết hiệu lực và được thay thế trực tiếp "
                    "bởi 200/2025/QH15 theo nguồn pháp luật chính thức. "
                )
                * 40,
                "score": 0.9,
            }
        ]


class _FakeFreshnessGoogle:
    async def search(self, *_: object, **__: object) -> dict:
        return {
            "results": [
                {
                    "url": "https://vanban.chinhphu.vn/luat-moi",
                    "title": "Luật mới",
                    "content": (
                        "100/2020/QH14 đã hết hiệu lực và được thay thế trực tiếp "
                        "bởi 200/2025/QH15 theo nguồn pháp luật chính thức."
                    ),
                    "score": 1,
                }
            ],
            "queries": ["100/2020/QH14 hết hiệu lực thay thế"],
        }


class _FailingFreshnessGoogle:
    async def search(self, *_: object, **__: object) -> dict:
        raise RuntimeError("Google Search unavailable")


def test_legal_freshness_requires_both_search_services() -> None:
    service = LegalFreshnessService(
        Settings(_env_file=None, legal_search_require_both=True),
        _FakeVerdictAI(),
        _FakeFreshnessTavily(),
        _FailingFreshnessGoogle(),
        _FakeIndexer(),
    )

    with pytest.raises(FreshnessUnavailable, match="Tavily và Google Search"):
        asyncio.run(service._search_official("kiểm tra hiệu lực", "100/2020/QH14"))


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (
            {
                "url": "http://vanban.chinhphu.vn/van-ban",
                "content": "100/2020/QH14 đang có hiệu lực theo nguồn chính thức của cơ quan nhà nước.",
            },
            False,
        ),
        (
            {
                "url": "https://vanban.chinhphu.vn:444/van-ban",
                "content": "100/2020/QH14 đang có hiệu lực theo nguồn chính thức của cơ quan nhà nước.",
            },
            False,
        ),
        (
            {
                "url": "https://vanban.chinhphu.vn/van-ban",
                "content": "100/2020/QH14",
            },
            False,
        ),
        (
            {
                "url": "https://vanban.chinhphu.vn/van-ban",
                "content": "100/2020/QH14X đang có hiệu lực theo nguồn chính thức của cơ quan nhà nước.",
            },
            False,
        ),
        (
            {
                "url": "https://vanban.chinhphu.vn/van-ban",
                "content": "200/2025/QH15 đang có hiệu lực theo nguồn chính thức của cơ quan nhà nước.",
            },
            False,
        ),
        (
            {
                "url": "https://vanban.chinhphu.vn:443/van-ban",
                "content": "100/2020/QH14 đang có hiệu lực theo nguồn chính thức của cơ quan nhà nước.",
            },
            True,
        ),
    ],
)
def test_freshness_filters_weak_or_unsafe_official_evidence(
    row: dict,
    expected: bool,
) -> None:
    service = LegalFreshnessService(
        Settings(_env_file=None),
        None,
        None,
        None,
        None,
    )

    assert bool(service._valid_official_evidence([row], "100/2020/QH14")) is expected


def _cache_payload(
    *,
    source_url: str = "https://vanban.chinhphu.vn/luat-a",
    providers: list[str] | None = None,
    evidence_code: str = "100/2020/QH14",
) -> dict:
    return {
        "provenance_version": 2,
        "verdict": {
            "code": "100/2020/QH14",
            "title": "Luật A",
            "status": "IN_FORCE",
            "source_url": source_url,
            "replacement_code": None,
            "replacement_title": None,
            "replacement_url": None,
            "reason": "Nguồn chính thức xác nhận còn hiệu lực.",
            "confidence": 0.99,
        },
        "evidence": [
            {
                "url": source_url,
                "content": (
                    f"{evidence_code} đang có hiệu lực theo nguồn pháp luật "
                    "chính thức của cơ quan nhà nước."
                ),
                "providers": ["google", "tavily"],
            }
        ],
        "providers_consulted": ["tavily", "google"],
        "providers_with_evidence": (
            providers if providers is not None else ["google", "tavily", "future"]
        ),
    }


def _cached_document(
    payload: object,
    *,
    source_url: str = "https://vanban.chinhphu.vn/luat-a",
) -> SimpleNamespace:
    return SimpleNamespace(
        code="100/2020/QH14",
        title="Luật A",
        status="IN_FORCE",
        source_url=source_url,
        replaced_by_code=None,
        verified_at=datetime.now(UTC),
        verification_payload=payload,
    )


class _CacheSession:
    def __init__(self, value: object) -> None:
        self.value = value
        self.rollback_calls = 0

    async def __aenter__(self) -> "_CacheSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def scalar(self, *_: object, **__: object) -> object:
        return self.value

    async def rollback(self) -> None:
        self.rollback_calls += 1


def test_freshness_uses_recent_cache_with_current_trusted_provenance(
    monkeypatch,
) -> None:
    from app.services import freshness

    document = _cached_document(_cache_payload())
    sessions = [_CacheSession(document)]
    monkeypatch.setattr(freshness, "SessionFactory", lambda: sessions.pop(0))
    service = LegalFreshnessService(
        Settings(_env_file=None, legal_search_require_both=True),
        None,
        None,
        None,
        None,
    )
    research_calls: list[str] = []

    async def research(*args: object) -> tuple[object, bool]:
        research_calls.append(str(args[0]))
        raise AssertionError("Cache hợp lệ không được gọi research")

    monkeypatch.setattr(service, "_search_verify_and_update", research)

    item, changed = asyncio.run(
        service._verify_one("100/2020/QH14", "Luật A", None)
    )

    assert not changed
    assert item.status == "IN_FORCE"
    assert research_calls == []
    assert sessions == []


@pytest.mark.parametrize(
    ("case", "payload", "source_url"),
    [
        ("legacy", {}, "https://vanban.chinhphu.vn/luat-a"),
        (
            "missing-google",
            _cache_payload(providers=["tavily"]),
            "https://vanban.chinhphu.vn/luat-a",
        ),
        (
            "http-source",
            _cache_payload(source_url="http://vanban.chinhphu.vn/luat-a"),
            "http://vanban.chinhphu.vn/luat-a",
        ),
        (
            "wrong-code-boundary",
            _cache_payload(evidence_code="100/2020/QH14X"),
            "https://vanban.chinhphu.vn/luat-a",
        ),
    ],
)
def test_freshness_skips_untrusted_recent_cache_and_researches(
    monkeypatch,
    case: str,
    payload: object,
    source_url: str,
) -> None:
    from app.services import freshness

    document = _cached_document(payload, source_url=source_url)
    initial_lookup = _CacheSession(document)
    lock_session = _CacheSession(True)
    locked_recheck = _CacheSession(document)
    sessions = [initial_lookup, lock_session, locked_recheck]
    monkeypatch.setattr(freshness, "SessionFactory", lambda: sessions.pop(0))
    service = LegalFreshnessService(
        Settings(_env_file=None, legal_search_require_both=True),
        None,
        None,
        None,
        None,
    )
    research_calls: list[tuple[str, str, str | None]] = []

    async def research(
        code: str,
        title: str,
        external_doc_id: str | None,
    ) -> tuple[object, bool]:
        research_calls.append((code, title, external_doc_id))
        return service._item(document, True), True

    monkeypatch.setattr(service, "_search_verify_and_update", research)

    _, changed = asyncio.run(
        service._verify_one("100/2020/QH14", "Luật A", None)
    )

    assert changed, case
    assert research_calls == [("100/2020/QH14", "Luật A", None)]
    assert lock_session.rollback_calls == 1
    assert sessions == []


def test_freshness_binds_replacement_code_to_replacement_url_row() -> None:
    service = LegalFreshnessService(
        Settings(_env_file=None),
        None,
        None,
        None,
        None,
    )
    evidence = [
        {
            "url": "https://vanban.chinhphu.vn/luat-cu",
            "content": "100/2020/QH14 đã hết hiệu lực theo nguồn pháp luật chính thức.",
        },
        {
            "url": "https://vanban.chinhphu.vn/quan-he-thay-the",
            "content": "100/2020/QH14 đã hết hiệu lực nhưng hàng này không nêu mã luật mới.",
        },
        {
            "url": "https://vanban.chinhphu.vn/luat-moi",
            "content": "200/2025/QH15 là văn bản mới đang có hiệu lực theo nguồn chính thức.",
        },
    ]
    verdict = {
        "code": "100/2020/QH14",
        "status": "REPLACED",
        "source_url": "https://vanban.chinhphu.vn/luat-cu",
        "replacement_code": "200/2025/QH15",
        "replacement_url": "https://vanban.chinhphu.vn/quan-he-thay-the",
        "confidence": 0.99,
    }

    with pytest.raises(FreshnessUnavailable, match="cùng URL"):
        service._validate_verdict_evidence(verdict, "100/2020/QH14", evidence)


def test_freshness_rejects_self_replacement_code() -> None:
    service = LegalFreshnessService(
        Settings(_env_file=None),
        None,
        None,
        None,
        None,
    )
    evidence = [
        {
            "url": "https://vanban.chinhphu.vn/luat-cu",
            "content": (
                "100/2020/QH14 đã hết hiệu lực theo nguồn pháp luật "
                "chính thức của cơ quan nhà nước."
            ),
        }
    ]
    verdict = {
        "code": "100/2020/QH14",
        "status": "REPLACED",
        "source_url": "https://vanban.chinhphu.vn/luat-cu",
        "replacement_code": "100/2020/QH14",
        "replacement_url": "https://vanban.chinhphu.vn/luat-cu",
        "confidence": 0.99,
    }

    with pytest.raises(FreshnessUnavailable, match="phải khác"):
        service._validate_verdict_evidence(verdict, "100/2020/QH14", evidence)


class _FakeVerdictAI:
    def __init__(self) -> None:
        self.codes: list[str] = []

    async def complete_json(self, _: str, user: str, **__: object) -> dict:
        assert 'UNTRUSTED_DATA name="TAVILY_GOOGLE_EVIDENCE"' in user
        if '"code": "200/2025/QH15"' in user:
            self.codes.append("200/2025/QH15")
            return {
                "code": "200/2025/QH15",
                "title": "Luật mới",
                "status": "IN_FORCE",
                "source_url": "https://vanban.chinhphu.vn/luat-moi",
                "replacement_code": None,
                "replacement_title": None,
                "replacement_url": None,
                "reason": "Đang có hiệu lực.",
                "confidence": 0.99,
            }
        self.codes.append("100/2020/QH14")
        return {
            "code": "100/2020/QH14",
            "title": "Luật cũ",
            "status": "REPLACED",
            "source_url": "https://vanban.chinhphu.vn/luat-moi",
            "replacement_code": "200/2025/QH15",
            "replacement_title": "Luật mới",
            "replacement_url": "https://vanban.chinhphu.vn/luat-moi",
            "reason": "Đã được thay thế.",
            "confidence": 0.99,
        }


class _FakeIndexer:
    def __init__(self, documents: dict[str, SimpleNamespace] | None = None) -> None:
        self.candidate = None
        self.candidates: list[object] = []
        self.documents = documents or {}

    async def index_candidate(self, _: object, candidate: object) -> SimpleNamespace:
        self.candidate = candidate
        self.candidates.append(candidate)
        document = self.documents.get(candidate.code)
        if document is None:
            document = SimpleNamespace(
                code=candidate.code,
                title=candidate.title,
                status=candidate.status,
                source_url=candidate.url,
                replaced_by_code=None,
                verified_at=None,
                verification_payload={},
                checksum=None,
            )
            self.documents[candidate.code] = document
        return document


class _FakeDb:
    def __init__(self, document: SimpleNamespace) -> None:
        self.document = document
        self.committed = False

    async def __aenter__(self) -> "_FakeDb":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def scalar(self, _: object) -> SimpleNamespace:
        return self.document

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _: object) -> None:
        return None


def test_expired_law_indexes_replacement_and_records_both_searches(monkeypatch) -> None:
    from app.services import freshness

    old_document = SimpleNamespace(
        code="100/2020/QH14",
        title="Luật cũ",
        status="IN_FORCE",
        source_url="https://vanban.chinhphu.vn/luat-cu",
        replaced_by_code=None,
        verified_at=datetime.now(UTC),
        verification_payload={},
        checksum="old",
    )
    db = _FakeDb(old_document)
    monkeypatch.setattr(freshness, "SessionFactory", lambda: db)
    indexer = _FakeIndexer({"100/2020/QH14": old_document})
    ai = _FakeVerdictAI()
    service = LegalFreshnessService(
        Settings(_env_file=None, legal_search_require_both=True),
        ai,
        _FakeFreshnessTavily(),
        _FakeFreshnessGoogle(),
        indexer,
    )

    item, changed = asyncio.run(
        service._search_verify_and_update(
            "100/2020/QH14",
            "Luật cũ",
            None,
        )
    )

    assert changed
    assert db.committed
    assert item.status == "REPLACED"
    assert old_document.replaced_by_code == "200/2025/QH15"
    assert ai.codes == ["100/2020/QH14", "200/2025/QH15"]
    assert [candidate.status for candidate in indexer.candidates] == [
        "IN_FORCE",
    ]
    assert indexer.candidate.code == "200/2025/QH15"
    assert indexer.candidate.replaces_code == "100/2020/QH14"
    assert len(old_document.verification_payload["evidence"][0]["providers"]) == 2
    replacement = indexer.documents["200/2025/QH15"]
    assert replacement.status == "IN_FORCE"
    assert replacement.verified_at is not None
    assert replacement.verification_payload["verdict"]["code"] == "200/2025/QH15"
    assert replacement.verification_payload["providers_with_evidence"] == [
        "google",
        "tavily",
    ]


_CHAIN_TITLES = {
    "100/2020/QH14": "Luật A",
    "200/2023/QH15": "Luật B",
    "300/2026/QH15": "Luật C",
}
_CHAIN_URLS = {
    "100/2020/QH14": "https://vanban.chinhphu.vn/luat-a",
    "200/2023/QH15": "https://vanban.chinhphu.vn/luat-b",
    "300/2026/QH15": "https://vanban.chinhphu.vn/luat-c",
}
_CHAIN_NEXT = {
    "100/2020/QH14": "200/2023/QH15",
    "200/2023/QH15": "300/2026/QH15",
}


def _chain_code_from_query(query: str) -> str:
    for code in _CHAIN_TITLES:
        if code in query:
            return code
    raise AssertionError(f"Không tìm thấy mã luật trong truy vấn: {query}")


def _chain_evidence_row(code: str, *, raw: bool) -> dict:
    replacement = _CHAIN_NEXT.get(code)
    relation = (
        f" Văn bản này được thay thế trực tiếp bởi {replacement}."
        if replacement
        else " Văn bản này đang có hiệu lực."
    )
    content = (
        f"{code} là văn bản pháp luật được công bố chính thức.{relation} "
        "Thông tin hiệu lực được cơ quan nhà nước xác nhận."
    ) * 8
    return {
        "url": _CHAIN_URLS[code],
        "title": _CHAIN_TITLES[code],
        "raw_content" if raw else "content": content,
        "score": 0.95,
    }


class _ChainTavily:
    def __init__(self) -> None:
        self.codes: list[str] = []

    async def search(self, query: str, **_: object) -> list[dict]:
        code = _chain_code_from_query(query)
        self.codes.append(code)
        return [_chain_evidence_row(code, raw=True)]


class _ChainGoogle:
    def __init__(self) -> None:
        self.codes: list[str] = []

    async def search(self, query: str, **_: object) -> dict:
        code = _chain_code_from_query(query)
        self.codes.append(code)
        return {
            "results": [_chain_evidence_row(code, raw=False)],
            "queries": [f"{code} hiệu lực"],
        }


class _ChainVerdictAI:
    def __init__(self, verdicts: dict[str, dict]) -> None:
        self.verdicts = verdicts
        self.codes: list[str] = []

    async def complete_json(self, _: str, user: str, **__: object) -> dict:
        for code, verdict in self.verdicts.items():
            if f'"code": "{code}"' in user:
                self.codes.append(code)
                return dict(verdict)
        raise AssertionError("Prompt không chứa mã luật cần kiểm tra")


def _chain_verdict(
    code: str,
    status: str,
    replacement_code: str | None = None,
) -> dict:
    return {
        "code": code,
        "title": _CHAIN_TITLES[code],
        "status": status,
        "source_url": _CHAIN_URLS[code],
        "replacement_code": replacement_code,
        "replacement_title": (
            _CHAIN_TITLES[replacement_code] if replacement_code else None
        ),
        # The current law's official evidence row proves the replacement
        # relation. The successor is researched again using its own URL.
        "replacement_url": _CHAIN_URLS[code] if replacement_code else None,
        "reason": "Kết luận dựa trên nguồn chính thức.",
        "confidence": 0.99,
    }


def test_replacement_chain_indexes_each_successor_independently(
    monkeypatch,
) -> None:
    from app.services import freshness

    tavily = _ChainTavily()
    google = _ChainGoogle()
    ai = _ChainVerdictAI(
        {
            "100/2020/QH14": _chain_verdict(
                "100/2020/QH14",
                "REPLACED",
                "200/2023/QH15",
            ),
            "200/2023/QH15": _chain_verdict(
                "200/2023/QH15",
                "EXPIRED",
                "300/2026/QH15",
            ),
            "300/2026/QH15": _chain_verdict(
                "300/2026/QH15",
                "IN_FORCE",
            ),
        }
    )
    db = _FakeDb(SimpleNamespace())
    monkeypatch.setattr(freshness, "SessionFactory", lambda: db)
    indexer = _FakeIndexer()
    service = LegalFreshnessService(
        Settings(_env_file=None, legal_search_require_both=True),
        ai,
        tavily,
        google,
        indexer,
    )

    item, changed = asyncio.run(
        service._search_verify_and_update(
            "100/2020/QH14",
            "Luật A",
            None,
        )
    )

    assert changed
    assert item.status == "REPLACED"
    assert ai.codes == [
        "100/2020/QH14",
        "200/2023/QH15",
        "300/2026/QH15",
    ]
    assert tavily.codes == ai.codes
    assert google.codes == ai.codes
    assert [
        (candidate.code, candidate.status, candidate.replaces_code)
        for candidate in indexer.candidates
    ] == [
        ("200/2023/QH15", "EXPIRED", "100/2020/QH14"),
        ("300/2026/QH15", "IN_FORCE", "200/2023/QH15"),
    ]
    assert [
        candidate.code
        for candidate in indexer.candidates
        if candidate.status in {"IN_FORCE", "PARTIALLY_IN_FORCE", "AMENDED"}
    ] == ["300/2026/QH15"]
    for code, document in indexer.documents.items():
        payload = document.verification_payload
        assert document.verified_at is not None
        assert payload["verdict"]["code"] == code
        assert payload["providers_consulted"] == ["tavily", "google"]
        assert payload["providers_with_evidence"] == ["google", "tavily"]
        assert payload["evidence"][0]["providers"] == ["google", "tavily"]


def test_current_indexed_law_is_verified_without_reingest(
    monkeypatch,
) -> None:
    from app.services import freshness

    current_document = SimpleNamespace(
        code="100/2020/QH14",
        title="Luật A",
        status="UNVERIFIED",
        source_url=None,
        replaced_by_code=None,
        verified_at=None,
        verification_payload={},
        checksum=None,
        external_doc_id="indexed-law-a",
    )
    db = _FakeDb(current_document)
    monkeypatch.setattr(freshness, "SessionFactory", lambda: db)
    indexer = _FakeIndexer({"100/2020/QH14": current_document})
    service = LegalFreshnessService(
        Settings(_env_file=None, legal_search_require_both=True),
        _ChainVerdictAI(
            {
                "100/2020/QH14": _chain_verdict(
                    "100/2020/QH14",
                    "IN_FORCE",
                )
            }
        ),
        _ChainTavily(),
        _ChainGoogle(),
        indexer,
    )

    item, changed = asyncio.run(
        service._search_verify_and_update(
            "100/2020/QH14",
            "Luật A",
            "indexed-law-a",
        )
    )

    assert changed is False
    assert item.status == "IN_FORCE"
    assert item.index_updated is False
    assert db.committed is True
    assert indexer.candidates == []
    assert current_document.status == "IN_FORCE"
    assert current_document.verification_payload["verdict"]["code"] == "100/2020/QH14"


def test_replacement_lifecycle_must_be_complete_after_follow_up_research(
    monkeypatch,
) -> None:
    from app.services import freshness

    malformed = _chain_verdict(
        "100/2020/QH14",
        "REPLACED",
        "200/2023/QH15",
    )
    malformed["replacement_title"] = None
    ai = _ChainVerdictAI({"100/2020/QH14": malformed})
    tavily = _ChainTavily()
    google = _ChainGoogle()
    indexer = _FakeIndexer()

    def session_must_not_open() -> object:
        raise AssertionError("Không được ghi DB khi lifecycle chưa hợp lệ")

    monkeypatch.setattr(freshness, "SessionFactory", session_must_not_open)
    service = LegalFreshnessService(
        Settings(_env_file=None, legal_search_require_both=True),
        ai,
        tavily,
        google,
        indexer,
    )

    with pytest.raises(FreshnessUnavailable, match="mã, tiêu đề và URL"):
        asyncio.run(
            service._search_verify_and_update(
                "100/2020/QH14",
                "Luật A",
                None,
            )
        )

    # One normal search plus one focused replacement-discovery search.
    assert ai.codes == ["100/2020/QH14", "100/2020/QH14"]
    assert tavily.codes == ai.codes
    assert google.codes == ai.codes
    assert indexer.candidates == []


def test_in_force_verdict_rejects_replacement_fields() -> None:
    service = LegalFreshnessService(
        Settings(_env_file=None),
        None,
        None,
        None,
        None,
    )
    verdict = _chain_verdict(
        "100/2020/QH14",
        "IN_FORCE",
        "200/2023/QH15",
    )

    with pytest.raises(FreshnessUnavailable, match="còn hiệu lực"):
        service._validate_verdict_evidence(
            verdict,
            "100/2020/QH14",
            [_chain_evidence_row("100/2020/QH14", raw=False)],
        )


class _CycleTavily(_ChainTavily):
    async def search(self, query: str, **kwargs: object) -> list[dict]:
        rows = await super().search(query, **kwargs)
        if self.codes[-1] == "200/2023/QH15":
            rows[0]["raw_content"] += (
                " 200/2023/QH15 được thay thế bởi 100/2020/QH14 "
                "theo công bố chính thức."
            )
        return rows


class _CycleGoogle(_ChainGoogle):
    async def search(self, query: str, **kwargs: object) -> dict:
        result = await super().search(query, **kwargs)
        if self.codes[-1] == "200/2023/QH15":
            result["results"][0]["content"] += (
                " 200/2023/QH15 được thay thế bởi 100/2020/QH14 "
                "theo công bố chính thức."
            )
        return result


def test_replacement_chain_rejects_cycles_before_indexing(monkeypatch) -> None:
    from app.services import freshness

    ai = _ChainVerdictAI(
        {
            "100/2020/QH14": _chain_verdict(
                "100/2020/QH14",
                "REPLACED",
                "200/2023/QH15",
            ),
            "200/2023/QH15": {
                **_chain_verdict(
                    "200/2023/QH15",
                    "REPLACED",
                    "100/2020/QH14",
                ),
                "replacement_title": "Luật A",
            },
        }
    )
    indexer = _FakeIndexer()
    monkeypatch.setattr(
        freshness,
        "SessionFactory",
        lambda: (_ for _ in ()).throw(
            AssertionError("Không được ghi DB khi chuỗi có vòng lặp")
        ),
    )
    service = LegalFreshnessService(
        Settings(_env_file=None, legal_search_require_both=True),
        ai,
        _CycleTavily(),
        _CycleGoogle(),
        indexer,
    )

    with pytest.raises(FreshnessUnavailable, match="vòng lặp"):
        asyncio.run(
            service._search_verify_and_update(
                "100/2020/QH14",
                "Luật A",
                None,
            )
        )

    assert ai.codes == ["100/2020/QH14", "200/2023/QH15"]
    assert indexer.candidates == []


def test_replacement_chain_enforces_safe_depth_before_indexing(
    monkeypatch,
) -> None:
    from app.services import freshness

    ai = _ChainVerdictAI(
        {
            "100/2020/QH14": _chain_verdict(
                "100/2020/QH14",
                "REPLACED",
                "200/2023/QH15",
            ),
            "200/2023/QH15": _chain_verdict(
                "200/2023/QH15",
                "REPLACED",
                "300/2026/QH15",
            ),
        }
    )
    indexer = _FakeIndexer()
    monkeypatch.setattr(freshness, "MAX_REPLACEMENT_CHAIN_DEPTH", 1)
    monkeypatch.setattr(
        freshness,
        "SessionFactory",
        lambda: (_ for _ in ()).throw(
            AssertionError("Không được ghi DB khi chuỗi vượt độ sâu")
        ),
    )
    service = LegalFreshnessService(
        Settings(_env_file=None, legal_search_require_both=True),
        ai,
        _ChainTavily(),
        _ChainGoogle(),
        indexer,
    )

    with pytest.raises(FreshnessUnavailable, match="độ sâu"):
        asyncio.run(
            service._search_verify_and_update(
                "100/2020/QH14",
                "Luật A",
                None,
            )
        )

    assert ai.codes == ["100/2020/QH14", "200/2023/QH15"]
    assert indexer.candidates == []
