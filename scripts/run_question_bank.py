"""Run the LaborCare question bank against the GraphRAG system.

Two modes:

* ``--mode retrieval`` (default) grades the retriever alone. It does not call
  the generation model, but dense retrieval still calls Vertex AI embeddings.
  Grading remains deterministic: for each question the bank declares which
  legal citations must come back and which facts must appear in retrieved text.
* ``--mode full`` runs the production answer path — retrieve → build context →
  Gemini with ``LEGAL_SYSTEM_PROMPT`` — then grades the generated answer for
  fact coverage, citation validity and (optionally) with an LLM judge, while
  recording per-stage latency.

The bank is tiered single-hop → multi-hop → multi-abstract so the report shows
where reasoning depth starts to cost accuracy.

Usage
-----
    python scripts/run_question_bank.py
    python scripts/run_question_bank.py --mode full --report storage/eval/full.json
    python scripts/run_question_bank.py --tier multi_abstract --top-k 14
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_BANK = PROJECT_ROOT / "evaluation" / "question_bank.json"
ARTICLE_IN_CITATION_RE = re.compile(r"Điều\s+(\d+[a-zA-Z]?)", re.IGNORECASE)
NODE_ID_RE = re.compile(r"^(dieu|khoan|diem):(?P<doc>[^:]+):(?P<article>[^:]+)")
SOURCE_TAG_RE = re.compile(r"\[(S\d+)\]")

JUDGE_SYSTEM_PROMPT = (
    "Bạn là giám khảo chấm câu trả lời pháp luật lao động Việt Nam. "
    "Chấm dựa trên tính chính xác pháp lý, mức độ đầy đủ so với câu hỏi, và việc có dẫn đúng căn cứ. "
    "Chỉ trả về JSON. Không giải thích ngoài JSON."
)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "correct": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["score", "correct", "reason"],
}


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def strip_accents(text: str) -> str:
    text = (text or "").replace("Đ", "D").replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def normalize_fact(text: str) -> str:
    """Fold a fact string so "300%" == "300 %" and diacritics do not matter."""

    return re.sub(r"\s+", " ", strip_accents(text or "").lower()).replace(" %", "%")


def article_numbers(row: dict[str, Any]) -> set[str]:
    numbers: set[str] = set()
    match = NODE_ID_RE.match(str(row.get("node_id") or ""))
    if match:
        numbers.add(match.group("article").lower())
    for found in ARTICLE_IN_CITATION_RE.finditer(str(row.get("citation") or "")):
        numbers.add(found.group(1).lower())
    return numbers


def describe_expectation(expected: dict[str, Any]) -> str:
    doc = str(expected.get("doc") or "?")
    if expected.get("article"):
        return f"{doc} Điều {expected['article']}"
    if expected.get("article_any"):
        return f"{doc} Điều {'/'.join(str(a) for a in expected['article_any'])}"
    if expected.get("table"):
        return f"{doc} (bảng)"
    return doc


class CitationMatcher:
    """Resolve "document + article" expectations against retrieved rows."""

    def __init__(self, code_to_doc: dict[str, str]):
        self.code_to_doc = code_to_doc

    def matches(self, expected: dict[str, Any], row: dict[str, Any]) -> bool:
        code = str(expected.get("doc") or "")
        doc_id = self.code_to_doc.get(code)
        row_doc = str(row.get("doc_id") or "")
        citation = str(row.get("citation") or "")

        if doc_id:
            if row_doc != doc_id:
                return False
        elif code and code.lower() not in citation.lower():
            return False

        wanted = [str(a).lower() for a in (expected.get("article_any") or [])]
        if expected.get("article"):
            wanted.append(str(expected["article"]).lower())
        if not wanted:
            # Document-level expectation, optionally pinned to a table chunk.
            return str(row.get("chunk_type") or "") == "table" if expected.get("table") else True

        found = article_numbers(row)
        if found & set(wanted):
            return True
        # A wage/fee table has no article number of its own but answers for the
        # article that introduces it.
        return bool(expected.get("table")) and str(row.get("chunk_type") or "") == "table"


def load_code_map(store: Any) -> dict[str, str]:
    conn = getattr(store, "conn", None)
    if conn is None:
        return {}
    try:
        rows = conn.execute("SELECT doc_id, code FROM docs").fetchall()
    except Exception:
        return {}
    return {str(row["code"]): str(row["doc_id"]) for row in rows if row["code"]}


def open_store(kind: str) -> Any:
    if kind == "local":
        from app.legal_graphrag import GraphRAGStore

        return GraphRAGStore()

    from app.external_graphrag import (
        ExternalGraphRAGConfig,
        Neo4jGraphRAGStore,
        Neo4jPostgresGraphRAGStore,
        PostgresGraphRAGStore,
    )

    config = ExternalGraphRAGConfig.from_env()
    if kind == "hybrid":
        return Neo4jPostgresGraphRAGStore(config)
    if kind == "postgres":
        return PostgresGraphRAGStore(config)
    if kind == "neo4j":
        return Neo4jGraphRAGStore(config)
    raise SystemExit(f"Unknown store: {kind}")


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


def grade_retrieval(
    question: dict[str, Any],
    rows: list[dict[str, Any]],
    matcher: CitationMatcher,
) -> dict[str, Any]:
    expect_any = question.get("expect_any") or []
    expect_all = question.get("expect_all") or []
    expect_text = question.get("expect_text") or []
    expect_min = question.get("expect_min")

    required = expect_all or expect_any
    first_hit_rank = 0
    matched: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for expected in required:
        rank = 0
        for index, row in enumerate(rows, start=1):
            if matcher.matches(expected, row):
                rank = index
                break
        if rank:
            matched.append({"expected": describe_expectation(expected), "rank": rank})
            if not first_hit_rank or rank < first_hit_rank:
                first_hit_rank = rank
        else:
            missing.append(expected)

    if expect_all:
        citation_score = len(matched) / len(expect_all)
        threshold = expect_min if expect_min else len(expect_all)
        hit = len(matched) >= threshold
    else:
        citation_score = 1.0 if matched else 0.0
        hit = bool(matched)

    haystack = normalize_fact(" ".join(str(row.get("text") or "") for row in rows))
    facts_found = [fact for fact in expect_text if normalize_fact(fact) in haystack]
    fact_score = len(facts_found) / len(expect_text) if expect_text else None

    return {
        "id": question["id"],
        "tier": question.get("tier", "single_hop"),
        "level": question["level"],
        "hops": question.get("hops", 1),
        "topic": question.get("topic", ""),
        "question": question["question"],
        "hit": hit,
        "citation_score": round(citation_score, 4),
        "source_fact_score": None if fact_score is None else round(fact_score, 4),
        "first_hit_rank": first_hit_rank,
        "reciprocal_rank": round(1.0 / first_hit_rank, 4) if first_hit_rank else 0.0,
        "matched": matched,
        "missing": [describe_expectation(item) for item in missing],
        "missing_facts": [fact for fact in expect_text if fact not in facts_found],
        "retrieved": len(rows),
        "top_citations": [
            {
                "source_id": row.get("source_id"),
                "score": row.get("score"),
                "chunk_type": row.get("chunk_type"),
                "citation": str(row.get("citation") or "")[:160],
            }
            for row in rows[:5]
        ],
    }


def grade_answer(question: dict[str, Any], answer: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    required = question.get("answer_must_contain") or []
    normalized = normalize_fact(answer)
    found = [fact for fact in required if normalize_fact(fact) in normalized]

    allowed = {str(row.get("source_id")) for row in sources}
    cited = set(SOURCE_TAG_RE.findall(answer or ""))
    invalid = sorted(cited - allowed)

    return {
        "answer_fact_score": round(len(found) / len(required), 4) if required else None,
        "answer_missing_facts": [fact for fact in required if fact not in found],
        "citations_used": len(cited),
        "invalid_citations": invalid,
        "citation_valid": not invalid,
        "grounded": bool(cited),
        "answer_chars": len(answer or ""),
    }


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def summarise(subset: list[dict[str, Any]]) -> dict[str, Any]:
    if not subset:
        return {}

    def mean_of(key: str) -> float | None:
        values = [row[key] for row in subset if row.get(key) is not None]
        return round(sum(values) / len(values), 4) if values else None

    stats: dict[str, Any] = {
        "questions": len(subset),
        "hit_rate": round(sum(1 for row in subset if row["hit"]) / len(subset), 4),
        "citation_recall": round(sum(row["citation_score"] for row in subset) / len(subset), 4),
        "source_fact_coverage": mean_of("source_fact_score"),
        "mrr": round(sum(row["reciprocal_rank"] for row in subset) / len(subset), 4),
    }

    latencies = [row["retrieval_ms"] for row in subset if row.get("retrieval_ms") is not None]
    if latencies:
        stats["retrieval_ms_p50"] = round(percentile(latencies, 0.5), 1)
        stats["retrieval_ms_p95"] = round(percentile(latencies, 0.95), 1)

    if any("answer_fact_score" in row for row in subset):
        stats["answer_fact_coverage"] = mean_of("answer_fact_score")
        graded = [row for row in subset if row.get("citation_valid") is not None]
        if graded:
            stats["citation_validity"] = round(
                sum(1 for row in graded if row["citation_valid"]) / len(graded), 4
            )
            stats["grounded_rate"] = round(sum(1 for row in graded if row.get("grounded")) / len(graded), 4)
        judged = [row["judge_score"] for row in subset if row.get("judge_score") is not None]
        if judged:
            stats["judge_score_avg"] = round(sum(judged) / len(judged), 3)
            stats["judge_pass_rate"] = round(
                sum(1 for row in subset if row.get("judge_correct")) / len(judged), 4
            )
        generation = [row["generation_ms"] for row in subset if row.get("generation_ms") is not None]
        if generation:
            stats["generation_ms_p50"] = round(percentile(generation, 0.5), 1)
            stats["generation_ms_p95"] = round(percentile(generation, 0.95), 1)
        net = [
            row.get("generation_ms_net", row["generation_ms"])
            for row in subset
            if row.get("generation_ms") is not None and not row.get("rate_limited")
        ]
        if net:
            stats["generation_ms_net_p50"] = round(percentile(net, 0.5), 1)
            stats["generation_ms_net_p95"] = round(percentile(net, 0.95), 1)
            stats["rate_limited_calls"] = sum(1 for row in subset if row.get("rate_limited"))
        totals = [row["total_ms"] for row in subset if row.get("total_ms") is not None]
        if totals:
            stats["total_ms_p50"] = round(percentile(totals, 0.5), 1)
            stats["total_ms_p95"] = round(percentile(totals, 0.95), 1)
            stats["total_ms_mean"] = round(statistics.fmean(totals), 1)
    return stats


def aggregate(bank: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    tier_order = {key: spec.get("order", 99) for key, spec in bank.get("tiers", {}).items()}
    tiers = sorted({row["tier"] for row in results}, key=lambda name: tier_order.get(name, 99))
    return {
        "overall": summarise(results),
        "by_tier": {tier: summarise([row for row in results if row["tier"] == tier]) for tier in tiers},
        "by_level": {
            str(level): summarise([row for row in results if row["level"] == level])
            for level in sorted({row["level"] for row in results})
        },
        "by_topic": {
            topic: summarise([row for row in results if row["topic"] == topic])
            for topic in sorted({row["topic"] for row in results if row["topic"]})
        },
    }


# ---------------------------------------------------------------------------
# Full-system execution
# ---------------------------------------------------------------------------


async def call_with_backoff(action: Any, attempts: int = 6, base_delay: float = 12.0) -> Any:
    """Retry a Vertex call through provider rate limiting.

    A 70-question sweep issues far more requests per minute than an interactive
    session, so 429 is expected rather than exceptional; without backoff the
    whole run degrades into a wall of quota errors and reports nothing.
    """

    last: Exception | None = None
    waited = 0.0
    for attempt in range(attempts):
        try:
            return await action(), waited
        except Exception as exc:
            message = str(exc)
            retryable = "429" in message or "Resource exhausted" in message or "503" in message
            last = exc
            if not retryable or attempt == attempts - 1:
                raise
            delay = base_delay * (attempt + 1)
            waited += delay
            await asyncio.sleep(delay)
    raise last if last else RuntimeError("retry loop exhausted")


async def run_full_pipeline(
    questions: list[dict[str, Any]],
    results: list[dict[str, Any]],
    retrieved: dict[str, list[dict[str, Any]]],
    concurrency: int,
    judge: bool,
) -> None:
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
    from app.core.config import Settings
    from app.services.ai import LEGAL_SYSTEM_PROMPT, GeminiService, untrusted_data_block
    from app.services.retrieval import build_context

    settings = Settings()
    ai = GeminiService(settings)
    by_id = {row["id"]: row for row in results}
    semaphore = asyncio.Semaphore(concurrency)
    done = 0

    async def answer_one(question: dict[str, Any]) -> None:
        nonlocal done
        row = by_id[question["id"]]
        sources = retrieved[question["id"]]
        async with semaphore:
            started = time.perf_counter()
            try:
                answer, waited = await call_with_backoff(
                    lambda: ai.complete(
                        LEGAL_SYSTEM_PROMPT,
                        f"NGUỒN:\n{build_context(sources)}\n\n"
                        f"CÂU HỎI HIỆN TẠI:\n{untrusted_data_block('CURRENT_QUESTION', question['question'])}",
                        max_tokens=2200,
                    )
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                row["generation_ms"] = round(elapsed_ms, 1)
                # Time spent sleeping through provider rate limiting is not a
                # property of the system under test.
                row["generation_ms_net"] = round(max(0.0, elapsed_ms - waited * 1000), 1)
                row["rate_limited"] = waited > 0
                row["answer"] = answer
                row["answer_error"] = None
                row.update(grade_answer(question, answer, sources))
            except Exception as exc:  # network, quota, safety filter...
                row["generation_ms"] = round((time.perf_counter() - started) * 1000, 1)
                row["answer"] = ""
                row["answer_error"] = f"{type(exc).__name__}: {exc}"[:300]
                row.update(grade_answer(question, "", sources))
            row["total_ms"] = round((row.get("retrieval_ms") or 0) + row["generation_ms"], 1)
        done += 1
        print(f"  answering [{done:3d}/{len(questions)}] {question['id']}   ", end="\r", flush=True)

    await asyncio.gather(*(answer_one(question) for question in questions))

    if judge:
        judged = 0

        async def judge_one(question: dict[str, Any]) -> None:
            nonlocal judged
            row = by_id[question["id"]]
            if not row.get("answer"):
                return
            expected = "; ".join(
                describe_expectation(item)
                for item in (question.get("expect_all") or question.get("expect_any") or [])
            )
            async with semaphore:
                try:
                    verdict, _waited = await call_with_backoff(
                        lambda: ai.complete_json(
                            JUDGE_SYSTEM_PROMPT,
                            "Chấm câu trả lời sau theo thang điểm 0-5 (5 = chính xác và đầy đủ).\n"
                            f"CÂU HỎI: {question['question']}\n"
                            f"CĂN CỨ PHÁP LÝ MONG ĐỢI: {expected or '(không chỉ định)'}\n"
                            f"GHI CHÚ CỦA ĐỀ: {question.get('notes', '(không có)')}\n\n"
                            f"CÂU TRẢ LỜI CẦN CHẤM:\n{row['answer'][:6000]}\n\n"
                            "Trả JSON: {\"score\": 0-5, \"correct\": true/false, \"reason\": \"...\"}. "
                            "correct = true khi câu trả lời đúng pháp lý và trả lời trúng câu hỏi.",
                            schema=JUDGE_SCHEMA,
                            max_tokens=400,
                        )
                    )
                    row["judge_score"] = int(verdict.get("score", 0))
                    row["judge_correct"] = bool(verdict.get("correct"))
                    row["judge_reason"] = str(verdict.get("reason", ""))[:400]
                except Exception as exc:
                    row["judge_error"] = f"{type(exc).__name__}: {exc}"[:200]
            judged += 1
            print(f"  judging   [{judged:3d}/{len(questions)}] {question['id']}   ", end="\r", flush=True)

        await asyncio.gather(*(judge_one(question) for question in questions))

    await ai.close()


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(bank: dict[str, Any], results: list[dict[str, Any]], summary: dict[str, Any], mode: str) -> None:
    tiers = bank.get("tiers", {})
    full = mode == "full"

    print("\n" + "=" * 108)
    print(f"KẾT QUẢ CHẠY BỘ CÂU HỎI GRAPHRAG — chế độ: {mode.upper()}")
    print("=" * 108)

    header = f"{'ID':8s} {'Tầng':14s} {'Hit':5s} {'Cit':5s} {'SrcF':5s}"
    if full:
        header += f" {'AnsF':5s} {'J':3s} {'Ret ms':>8s} {'Gen ms':>8s}"
    header += "  Câu hỏi"
    print("\n" + header)
    print("-" * 108)
    for row in results:
        src = "  -  " if row["source_fact_score"] is None else f"{row['source_fact_score']:.2f} "
        line = (
            f"{row['id']:8s} {row['tier']:14s} {'PASS ' if row['hit'] else 'FAIL '} "
            f"{row['citation_score']:.2f}  {src:5s}"
        )
        if full:
            ans = "  -  " if row.get("answer_fact_score") is None else f"{row['answer_fact_score']:.2f} "
            judge = str(row.get("judge_score", "-"))
            line += f" {ans:5s} {judge:3s} {row.get('retrieval_ms', 0):>8.0f} {row.get('generation_ms', 0):>8.0f}"
        line += f"  {row['question'][:44]}"
        print(line)

    print("\n" + "-" * 108)
    print("TỔNG HỢP THEO TẦNG SUY LUẬN")
    print("-" * 108)
    columns = f"{'Tầng':22s} {'Câu':>4s} {'Hit@k':>7s} {'Recall':>7s} {'SrcFact':>8s}"
    if full:
        columns += f" {'AnsFact':>8s} {'Cit.OK':>7s} {'Judge':>6s} {'p50 ms':>8s} {'p95 ms':>8s}"
    print(columns)
    print("-" * 108)
    for tier, stats in summary["by_tier"].items():
        name = tiers.get(tier, {}).get("name", tier)
        src = "-" if stats.get("source_fact_coverage") is None else f"{stats['source_fact_coverage']:.3f}"
        line = (
            f"{name:22s} {stats['questions']:>4d} {stats['hit_rate']:>7.3f} "
            f"{stats['citation_recall']:>7.3f} {src:>8s}"
        )
        if full:
            ans = "-" if stats.get("answer_fact_coverage") is None else f"{stats['answer_fact_coverage']:.3f}"
            cit = "-" if stats.get("citation_validity") is None else f"{stats['citation_validity']:.3f}"
            judge = "-" if stats.get("judge_score_avg") is None else f"{stats['judge_score_avg']:.2f}"
            line += (
                f" {ans:>8s} {cit:>7s} {judge:>6s} "
                f"{stats.get('total_ms_p50', 0):>8.0f} {stats.get('total_ms_p95', 0):>8.0f}"
            )
        print(line)

    overall = summary["overall"]
    src = "-" if overall.get("source_fact_coverage") is None else f"{overall['source_fact_coverage']:.3f}"
    line = (
        f"{'TỔNG':22s} {overall['questions']:>4d} {overall['hit_rate']:>7.3f} "
        f"{overall['citation_recall']:>7.3f} {src:>8s}"
    )
    if full:
        ans = "-" if overall.get("answer_fact_coverage") is None else f"{overall['answer_fact_coverage']:.3f}"
        cit = "-" if overall.get("citation_validity") is None else f"{overall['citation_validity']:.3f}"
        judge = "-" if overall.get("judge_score_avg") is None else f"{overall['judge_score_avg']:.2f}"
        line += (
            f" {ans:>8s} {cit:>7s} {judge:>6s} "
            f"{overall.get('total_ms_p50', 0):>8.0f} {overall.get('total_ms_p95', 0):>8.0f}"
        )
    print("-" * 108)
    print(line)

    print("\nĐỘ TRỄ (ms)")
    print("-" * 108)
    print(
        f"  Truy hồi   p50={overall.get('retrieval_ms_p50', 0):>8.0f}   "
        f"p95={overall.get('retrieval_ms_p95', 0):>8.0f}"
    )
    if full:
        print(
            f"  Sinh câu   p50={overall.get('generation_ms_p50', 0):>8.0f}   "
            f"p95={overall.get('generation_ms_p95', 0):>8.0f}"
        )
        print(
            f"  Tổng       p50={overall.get('total_ms_p50', 0):>8.0f}   "
            f"p95={overall.get('total_ms_p95', 0):>8.0f}   "
            f"mean={overall.get('total_ms_mean', 0):>8.0f}"
        )

    failures = [row for row in results if not row["hit"]]
    if failures:
        print(f"\n{len(failures)} câu chưa đạt ngưỡng trích dẫn:")
        for row in failures:
            print(f"  {row['id']} [{row['tier']}]: thiếu {', '.join(row['missing']) or '(không khớp)'}")

    if full:
        bad_citations = [row for row in results if row.get("invalid_citations")]
        if bad_citations:
            print(f"\n{len(bad_citations)} câu trích dẫn ID không hợp lệ (dấu hiệu bịa nguồn):")
            for row in bad_citations:
                print(f"  {row['id']}: {', '.join(row['invalid_citations'])}")
        errors = [row for row in results if row.get("answer_error")]
        if errors:
            print(f"\n{len(errors)} câu lỗi khi sinh câu trả lời:")
            for row in errors:
                print(f"  {row['id']}: {row['answer_error']}")


def write_markdown(path: Path, bank: dict[str, Any], summary: dict[str, Any], results: list[dict[str, Any]], mode: str, meta: dict[str, Any]) -> None:
    tiers = bank.get("tiers", {})
    full = mode == "full"
    lines: list[str] = []
    lines.append(f"# Báo cáo đánh giá GraphRAG — {bank.get('name')} v{bank.get('version')}")
    lines.append("")
    lines.append(f"- Chế độ chạy: **{mode}**")
    lines.append(f"- Kho truy hồi: `{meta['store']}` · top-k = {meta['top_k']}")
    if full:
        lines.append(f"- Mô hình sinh câu trả lời: `{meta.get('model', 'n/a')}`")
    lines.append(f"- Tổng thời gian: {meta['elapsed_seconds']}s · {summary['overall']['questions']} câu hỏi")
    lines.append("")

    lines.append("## 1. Kết quả tổng hợp theo tầng suy luận")
    lines.append("")
    head = "| Tầng | Số câu | Hit@k | Citation recall | Fact (nguồn) |"
    sep = "| --- | ---: | ---: | ---: | ---: |"
    if full:
        head += " Fact (câu trả lời) | Citation hợp lệ | Judge (0-5) | p50 (ms) | p95 (ms) |"
        sep += " ---: | ---: | ---: | ---: | ---: |"
    lines.append(head)
    lines.append(sep)
    for tier, stats in summary["by_tier"].items():
        name = tiers.get(tier, {}).get("name", tier)
        src = "-" if stats.get("source_fact_coverage") is None else f"{stats['source_fact_coverage']:.3f}"
        row = f"| {name} | {stats['questions']} | {stats['hit_rate']:.3f} | {stats['citation_recall']:.3f} | {src} |"
        if full:
            ans = "-" if stats.get("answer_fact_coverage") is None else f"{stats['answer_fact_coverage']:.3f}"
            cit = "-" if stats.get("citation_validity") is None else f"{stats['citation_validity']:.3f}"
            judge = "-" if stats.get("judge_score_avg") is None else f"{stats['judge_score_avg']:.2f}"
            row += f" {ans} | {cit} | {judge} | {stats.get('total_ms_p50', 0):.0f} | {stats.get('total_ms_p95', 0):.0f} |"
        lines.append(row)
    overall = summary["overall"]
    src = "-" if overall.get("source_fact_coverage") is None else f"{overall['source_fact_coverage']:.3f}"
    row = f"| **Tổng** | {overall['questions']} | {overall['hit_rate']:.3f} | {overall['citation_recall']:.3f} | {src} |"
    if full:
        ans = "-" if overall.get("answer_fact_coverage") is None else f"{overall['answer_fact_coverage']:.3f}"
        cit = "-" if overall.get("citation_validity") is None else f"{overall['citation_validity']:.3f}"
        judge = "-" if overall.get("judge_score_avg") is None else f"{overall['judge_score_avg']:.2f}"
        row += f" {ans} | {cit} | {judge} | {overall.get('total_ms_p50', 0):.0f} | {overall.get('total_ms_p95', 0):.0f} |"
    lines.append(row)
    lines.append("")

    lines.append("## 2. Kết quả theo mức độ")
    lines.append("")
    lines.append("| Mức | Số câu | Hit@k | Citation recall | MRR |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for level, stats in summary["by_level"].items():
        lines.append(
            f"| {level} | {stats['questions']} | {stats['hit_rate']:.3f} | "
            f"{stats['citation_recall']:.3f} | {stats['mrr']:.3f} |"
        )
    lines.append("")

    lines.append("## 3. Kết quả theo chủ đề")
    lines.append("")
    lines.append("| Chủ đề | Số câu | Hit@k | Citation recall |")
    lines.append("| --- | ---: | ---: | ---: |")
    for topic, stats in summary["by_topic"].items():
        lines.append(f"| {topic} | {stats['questions']} | {stats['hit_rate']:.3f} | {stats['citation_recall']:.3f} |")
    lines.append("")

    lines.append("## 4. Chi tiết từng câu hỏi")
    lines.append("")
    head = "| ID | Tầng | Hop | Hit | Recall | Fact nguồn |"
    sep = "| --- | --- | ---: | --- | ---: | ---: |"
    if full:
        head += " Fact đáp án | Judge | Ret (ms) | Gen (ms) |"
        sep += " ---: | ---: | ---: | ---: |"
    head += " Câu hỏi |"
    sep += " --- |"
    lines.append(head)
    lines.append(sep)
    for row in results:
        srcf = "-" if row["source_fact_score"] is None else f"{row['source_fact_score']:.2f}"
        line = (
            f"| {row['id']} | {row['tier']} | {row['hops']} | "
            f"{'✅' if row['hit'] else '❌'} | {row['citation_score']:.2f} | {srcf} |"
        )
        if full:
            ansf = "-" if row.get("answer_fact_score") is None else f"{row['answer_fact_score']:.2f}"
            line += (
                f" {ansf} | {row.get('judge_score', '-')} | "
                f"{row.get('retrieval_ms', 0):.0f} | {row.get('generation_ms', 0):.0f} |"
            )
        line += f" {row['question'][:90]} |"
        lines.append(line)
    lines.append("")

    failures = [row for row in results if not row["hit"]]
    if failures:
        lines.append("## 5. Câu chưa đạt và căn cứ còn thiếu")
        lines.append("")
        for row in failures:
            lines.append(f"- **{row['id']}** ({row['tier']}): thiếu `{', '.join(row['missing']) or 'không khớp'}` — {row['question']}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LaborCare GraphRAG question bank.")
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--mode", choices=["retrieval", "full"], default="retrieval")
    parser.add_argument("--tier", action="append", help="Only run these tiers (repeatable).")
    parser.add_argument("--level", type=int, action="append", help="Only run these levels (repeatable).")
    parser.add_argument("--topic", action="append", help="Only run these topics (repeatable).")
    parser.add_argument("--store", choices=["local", "postgres", "neo4j", "hybrid"], default="local")
    parser.add_argument("--concurrency", type=int, default=4, help="Parallel LLM calls in full mode.")
    parser.add_argument("--judge", action="store_true", help="Also score answers with an LLM judge.")
    parser.add_argument("--report", type=Path, help="Write the full JSON report here.")
    parser.add_argument("--markdown", type=Path, help="Write a Markdown report here.")
    args = parser.parse_args()

    bank = json.loads(args.bank.read_text(encoding="utf-8"))
    questions = bank["questions"]
    if args.tier:
        questions = [q for q in questions if q.get("tier") in set(args.tier)]
    if args.level:
        questions = [q for q in questions if q["level"] in set(args.level)]
    if args.topic:
        questions = [q for q in questions if q.get("topic") in set(args.topic)]
    if not questions:
        raise SystemExit("No questions selected.")

    store = open_store(args.store)
    matcher = CitationMatcher(load_code_map(store))

    started = time.time()
    results: list[dict[str, Any]] = []
    retrieved: dict[str, list[dict[str, Any]]] = {}

    # Warm the embedding endpoint so the first question does not absorb auth
    # refresh, connection setup, and Vertex AI cold-path latency.
    store.retrieve("khởi động hệ thống", top_k=1)

    for index, question in enumerate(questions, start=1):
        clock = time.perf_counter()
        rows = store.retrieve(question["question"], top_k=args.top_k)
        elapsed_ms = (time.perf_counter() - clock) * 1000
        retrieved[question["id"]] = rows
        row = grade_retrieval(question, rows, matcher)
        row["retrieval_ms"] = round(elapsed_ms, 1)
        results.append(row)
        print(f"  retrieving [{index:3d}/{len(questions)}] {question['id']}   ", end="\r", flush=True)

    model = ""
    if args.mode == "full":
        from app.core.config import Settings

        os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
        model = Settings().gemini_model
        asyncio.run(run_full_pipeline(questions, results, retrieved, args.concurrency, args.judge))

    elapsed = time.time() - started
    summary = aggregate(bank, results)
    print_report(bank, results, summary, args.mode)
    print(f"\nThời gian chạy: {elapsed:.1f}s")

    meta = {
        "store": args.store,
        "top_k": args.top_k,
        "mode": args.mode,
        "model": model,
        "elapsed_seconds": round(elapsed, 2),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                {
                    "bank": bank.get("name"),
                    "bank_version": bank.get("version"),
                    **meta,
                    "summary": summary,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Báo cáo JSON: {args.report}")
    if args.markdown:
        write_markdown(args.markdown, bank, summary, results, args.mode, meta)
        print(f"Báo cáo Markdown: {args.markdown}")

    if hasattr(store, "close"):
        store.close()


if __name__ == "__main__":
    main()
