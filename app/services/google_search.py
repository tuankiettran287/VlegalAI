from __future__ import annotations

import asyncio
import ipaddress
import math
import re
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

from app.core.config import Settings
from app.services.ai import GeminiError, GeminiService


TRACKING_QUERY_PREFIXES = ("utm_", "gclid", "fbclid")
GOOGLE_REDIRECT_HOSTS = {
    "vertexaisearch.cloud.google.com",
    "www.google.com",
    "google.com",
}
TRUSTED_SEARCH_PROVIDERS = {"google", "tavily"}
HOST_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class GoogleSearchError(RuntimeError):
    pass


def safe_public_url(value: Any) -> str:
    """Return a stripped public HTTP(S) URL, or an empty string when unsafe."""
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if not raw or any(character.isspace() or ord(character) < 32 for character in raw):
        return ""
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"}:
        return ""
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        return ""
    if port is not None and not 1 <= port <= 65535:
        return ""

    hostname = parsed.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            ascii_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError:
            return ""
        if (
            len(ascii_hostname) > 253
            or "." not in ascii_hostname
            or ascii_hostname == "localhost"
            or ascii_hostname.endswith((".localhost", ".local", ".internal"))
            or any(
                not HOST_LABEL_RE.fullmatch(label)
                for label in ascii_hostname.split(".")
            )
        ):
            return ""
    else:
        if not address.is_global:
            return ""
    return raw


def canonical_url(value: str) -> str:
    safe_url = safe_public_url(value)
    if not safe_url:
        return ""
    parsed = urlparse(safe_url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    try:
        hostname = hostname.encode("idna").decode("ascii")
        port = parsed.port
    except (UnicodeError, ValueError):
        return ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith(TRACKING_QUERY_PREFIXES)
        ]
    )
    return urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path.rstrip("/") or "/",
            "",
            query,
            "",
        )
    )


def _safe_score(value: Any) -> float:
    try:
        score = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return score if math.isfinite(score) else 0.0


def _provider_names(provider: str, row: dict[str, Any]) -> set[str]:
    normalized_provider = (
        provider.strip().lower() if isinstance(provider, str) else ""
    )
    if normalized_provider:
        # The group label is assigned by our integration and is authoritative.
        return (
            {normalized_provider}
            if normalized_provider in TRUSTED_SEARCH_PROVIDERS
            else set()
        )

    # Empty provider groups are used when already-normalized rows are re-ranked.
    raw_providers = row.get("providers")
    if not isinstance(raw_providers, (list, tuple, set)):
        return set()
    return {
        item.strip().lower()
        for item in raw_providers
        if isinstance(item, str)
        and item.strip().lower() in TRUSTED_SEARCH_PROVIDERS
    }


def _provider_evidence(
    provider: str,
    row: dict[str, Any],
    providers: set[str],
) -> dict[str, dict[str, str]]:
    fields = ("title", "content", "raw_content", "published_date")
    if isinstance(provider, str) and provider.strip():
        snapshot = {
            field: value
            for field in fields
            if isinstance((value := row.get(field)), str) and value
        }
        return {name: dict(snapshot) for name in providers}

    raw = row.get("provider_evidence")
    if not isinstance(raw, dict):
        return {}
    return {
        name: {
            field: value
            for field in fields
            if isinstance((value := raw_row.get(field)), str) and value
        }
        for name, raw_row in raw.items()
        if name in providers and isinstance(raw_row, dict)
    }


def merge_search_results(
    groups: Iterable[tuple[str, list[dict[str, Any]]]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for provider, rows in groups:
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = safe_public_url(row.get("url"))
            if not url:
                continue
            key = canonical_url(url)
            if not key:
                continue
            row_providers = _provider_names(provider, row)
            row_evidence = _provider_evidence(provider, row, row_providers)
            current = merged.get(key)
            if current is None:
                current = dict(row)
                current["url"] = url
                current["score"] = _safe_score(current.get("score"))
                current.pop("provider", None)
                for field in ("raw_content", "content", "title", "published_date"):
                    if field in current and not isinstance(current[field], str):
                        current.pop(field)
                current["providers"] = sorted(row_providers)
                current["provider_evidence"] = row_evidence
                merged[key] = current
                continue
            providers = set(current.get("providers") or [])
            providers.update(row_providers)
            current["providers"] = sorted(providers)
            current_evidence = current.get("provider_evidence")
            if not isinstance(current_evidence, dict):
                current_evidence = {}
            for provider_name, snapshot in row_evidence.items():
                existing = current_evidence.get(provider_name)
                if not isinstance(existing, dict):
                    current_evidence[provider_name] = dict(snapshot)
                    continue
                for field, candidate in snapshot.items():
                    if len(candidate) > len(str(existing.get(field) or "")):
                        existing[field] = candidate
            current["provider_evidence"] = current_evidence
            current["score"] = max(
                _safe_score(current.get("score")),
                _safe_score(row.get("score")),
            )
            for field in ("raw_content", "content", "title", "published_date"):
                candidate = row.get(field)
                if (
                    isinstance(candidate, str)
                    and candidate
                    and len(candidate) > len(str(current.get(field) or ""))
                ):
                    current[field] = candidate

    rows = list(merged.values())
    rows.sort(
        key=lambda row: (
            len(row.get("providers") or []),
            _safe_score(row.get("score")),
        ),
        reverse=True,
    )
    return rows[: max(0, int(limit))]


class GoogleSearchService:
    def __init__(self, settings: Settings, ai: GeminiService):
        self.settings = settings
        self.ai = ai

    @staticmethod
    def _allowed_domain(url: str, domains: list[str] | None) -> bool:
        safe_url = safe_public_url(url)
        if not safe_url:
            return False
        if not domains:
            return True
        host = (
            (urlparse(safe_url).hostname or "")
            .lower()
            .rstrip(".")
            .removeprefix("www.")
        )
        normalized_domains: list[str] = []
        for domain in domains:
            if not isinstance(domain, str):
                continue
            raw_domain = domain.strip().lower().rstrip(".")
            if not raw_domain:
                continue
            try:
                parsed_domain = urlparse(
                    raw_domain if "://" in raw_domain else f"//{raw_domain}"
                )
            except ValueError:
                continue
            allowed_host = (
                (parsed_domain.hostname or "")
                .lower()
                .rstrip(".")
                .removeprefix("www.")
            )
            if allowed_host:
                normalized_domains.append(allowed_host)
        return any(
            host == domain or host.endswith(f".{domain}")
            for domain in normalized_domains
        )

    async def _resolve_url(
        self,
        url: str,
        include_domains: list[str] | None = None,
    ) -> str:
        current_url = safe_public_url(url)
        if not current_url:
            return ""
        host = (urlparse(current_url).hostname or "").lower()
        if host not in GOOGLE_REDIRECT_HOSTS:
            return (
                current_url
                if self._allowed_domain(current_url, include_domains)
                else ""
            )
        try:
            async with httpx.AsyncClient(
                timeout=min(self.settings.gemini_timeout_seconds, 20),
                follow_redirects=False,
                headers={"User-Agent": "VLegalAI/3.0 (+google-search-grounding)"},
            ) as client:
                # Follow only Google-owned hops ourselves. The first non-Google
                # target is validated and returned without fetching it locally.
                for _ in range(3):
                    response = await client.get(current_url)
                    location = response.headers.get("location")
                    if not location or not 300 <= response.status_code < 400:
                        return ""
                    candidate = safe_public_url(urljoin(current_url, location))
                    if not candidate:
                        return ""
                    candidate_host = (urlparse(candidate).hostname or "").lower()
                    if candidate_host not in GOOGLE_REDIRECT_HOSTS:
                        return (
                            candidate
                            if self._allowed_domain(candidate, include_domains)
                            else ""
                        )
                    current_url = candidate
        except (httpx.HTTPError, ValueError):
            return ""
        return ""

    async def search(
        self,
        query: str,
        *,
        include_domains: list[str] | None = None,
        max_results: int = 10,
    ) -> dict[str, Any]:
        include_domains = (
            [
                domain.strip()
                for domain in include_domains
                if isinstance(domain, str) and domain.strip()
            ]
            if isinstance(include_domains, list)
            else None
        )
        try:
            result_limit = max(0, int(max_results))
        except (TypeError, ValueError):
            result_limit = 10
        domain_hint = ""
        if include_domains:
            domain_hint = "\nChỉ tìm trên các tên miền: " + ", ".join(include_domains)
        try:
            payload = await self.ai.search_google(query + domain_hint)
        except GeminiError as exc:
            raise GoogleSearchError(str(exc)) from exc

        if not isinstance(payload, dict):
            raise GoogleSearchError("Google Search returned an invalid payload.")
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise GoogleSearchError("Google Search không trả về kết quả.")
        if not isinstance(candidates[0], dict):
            raise GoogleSearchError("Google Search returned an invalid candidate.")
        candidate = candidates[0]
        metadata = candidate.get("groundingMetadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        chunks = metadata.get("groundingChunks") or []
        supports = metadata.get("groundingSupports") or []
        if not isinstance(chunks, list):
            chunks = []
        if not isinstance(supports, list):
            supports = []

        snippets: dict[int, list[str]] = {}
        for support in supports:
            if not isinstance(support, dict):
                continue
            segment = support.get("segment") or {}
            segment_text = segment.get("text") if isinstance(segment, dict) else None
            text = segment_text.strip() if isinstance(segment_text, str) else ""
            indices = support.get("groundingChunkIndices") or []
            if not isinstance(indices, list):
                continue
            for index in indices:
                if isinstance(index, int) and text:
                    snippets.setdefault(index, []).append(text)

        raw_rows: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict) or not isinstance(chunk.get("web"), dict):
                continue
            web = dict(chunk["web"])
            raw_title = web.get("title") or web.get("domain")
            web["title"] = (
                raw_title.strip()[:500]
                if isinstance(raw_title, str) and raw_title.strip()
                else "Google Search source"
            )
            web["domain"] = ""
            url = safe_public_url(web.get("uri"))
            if not url:
                continue
            raw_rows.append(
                {
                    "title": web.get("title") or web.get("domain") or "Nguồn Google Search",
                    "url": url,
                    "content": " ".join(dict.fromkeys(snippets.get(index, [])))[:3000],
                    "raw_content": "",
                    "published_date": None,
                    "score": round(1 / (index + 1), 4),
                    "provider": "google",
                }
            )

        resolved_urls = await asyncio.gather(
            *(
                self._resolve_url(str(row["url"]), include_domains)
                for row in raw_rows
            )
        )
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row, resolved_url in zip(raw_rows, resolved_urls, strict=True):
            key = canonical_url(resolved_url)
            if not key or key in seen:
                continue
            if len(results) >= result_limit:
                break
            seen.add(key)
            row["url"] = resolved_url
            results.append(row)

        entry_point = metadata.get("searchEntryPoint") or {}
        raw_queries = metadata.get("webSearchQueries") or []
        return {
            "results": results,
            "queries": (
                [
                    item[:500]
                    for item in raw_queries
                    if isinstance(item, str) and item.strip()
                ]
                if isinstance(raw_queries, list)
                else []
            ),
            "search_entry_point": (
                entry_point.get("renderedContent")
                if isinstance(entry_point, dict)
                and isinstance(entry_point.get("renderedContent"), str)
                else None
            ),
        }
