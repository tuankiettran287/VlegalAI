from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.embeddings import EmbeddingConfig, get_embedding_service
from app.main import (
    backend_mode_label,
    call_groq_chat,
    get_store,
    normalize_backend,
    repair_text,
)


DEFAULT_DATASET = PROJECT_ROOT / "eval_legal_rag_graphrag_1000.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "storage" / "eval" / "ragas"
DEFAULT_METRICS = [
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_relevancy",
    "answer_correctness",
]
CONTEXT_METRICS = {"context_precision", "context_recall"}
RESPONSE_METRICS = {"faithfulness", "answer_relevancy", "answer_correctness"}


class LocalBgeEmbeddings:
    """LangChain-compatible embeddings backed by the local BGE-M3 model."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return get_embedding_service(EmbeddingConfig.from_env()).embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return get_embedding_service(EmbeddingConfig.from_env()).embed_query(text)


def now_slug() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def clean_text(value: Any) -> str:
    return repair_text(value).strip()


def backend_slug(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def load_eval_samples(path: Path, offset: int = 0, limit: int | None = None) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"Expected a JSON list in {path}")
    end = None if limit is None else offset + max(limit, 0)
    return rows[offset:end]


def question_from_sample(sample: dict[str, Any]) -> str:
    ragas_fields = sample.get("ragas_fields") or {}
    return clean_text(ragas_fields.get("user_input") or sample.get("question") or "")


def reference_from_sample(sample: dict[str, Any]) -> str:
    ragas_fields = sample.get("ragas_fields") or {}
    return clean_text(ragas_fields.get("reference") or sample.get("reference_answer") or "")


def expected_chunk_ids(sample: dict[str, Any]) -> list[str]:
    contexts = sample.get("relevant_contexts") or []
    return [
        clean_text(item.get("chunk_id"))
        for item in contexts
        if isinstance(item, dict) and item.get("chunk_id")
    ]


def context_text_from_source(source: dict[str, Any]) -> str:
    citation = clean_text(source.get("citation") or source.get("title") or "")
    text = clean_text(source.get("text") or "")
    if citation and text:
        return f"{citation}\n{text}"
    return text or citation


def compact_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": source.get("source_id"),
        "chunk_id": source.get("chunk_id"),
        "doc_id": source.get("doc_id"),
        "node_id": source.get("node_id"),
        "chunk_type": clean_text(source.get("chunk_type") or ""),
        "citation": clean_text(source.get("citation") or source.get("title") or ""),
        "score": source.get("score"),
        "reasons": source.get("reasons") or [],
    }


def exact_retrieval_scores(
    retrieved_sources: list[dict[str, Any]],
    expected_ids: list[str],
) -> dict[str, float | int | bool | None]:
    retrieved_ids = [
        clean_text(source.get("chunk_id"))
        for source in retrieved_sources
        if source.get("chunk_id")
    ]
    expected = list(dict.fromkeys(expected_ids))
    retrieved = list(dict.fromkeys(retrieved_ids))
    expected_set = set(expected)
    retrieved_set = set(retrieved)
    hits = expected_set & retrieved_set
    first_rank = None
    for index, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in expected_set:
            first_rank = index
            break
    return {
        "exact_hit_at_k": bool(hits),
        "exact_hits": len(hits),
        "exact_precision": len(hits) / len(retrieved) if retrieved else 0.0,
        "exact_recall": len(hits) / len(expected) if expected else None,
        "exact_mrr": 1.0 / first_rank if first_rank else 0.0,
    }


def response_for_sample(
    response_mode: str,
    sample: dict[str, Any],
    question: str,
    reference: str,
    sources: list[dict[str, Any]],
    mode_label: str,
) -> str:
    ragas_response = clean_text((sample.get("ragas_fields") or {}).get("response") or "")
    if response_mode == "dataset":
        return ragas_response
    if response_mode == "reference":
        return reference
    if response_mode == "none":
        return ""
    if response_mode == "generate" and ragas_response:
        return ragas_response
    return clean_text(call_groq_chat(question, sources, mode_label))


def build_records_for_backend(
    backend: str,
    samples: list[dict[str, Any]],
    top_k: int,
    response_mode: str,
) -> list[dict[str, Any]]:
    backend_name = backend_slug(backend)
    canonical_backend = normalize_backend(backend)
    store = None
    if canonical_backend != "dataset":
        store = get_store(canonical_backend)
    records: list[dict[str, Any]] = []
    mode_label = "Dataset"
    if canonical_backend != "dataset":
        mode_label = backend_mode_label(canonical_backend)

    for index, sample in enumerate(samples, start=1):
        started = time.time()
        question = question_from_sample(sample)
        reference = reference_from_sample(sample)
        if not question:
            raise ValueError(f"Sample {sample.get('id') or index} has no question")

        if store is None:
            contexts = [
                clean_text(value)
                for value in ((sample.get("ragas_fields") or {}).get("retrieved_contexts") or [])
                if clean_text(value)
            ]
            sources = []
        else:
            sources = store.retrieve(question, top_k=top_k)
            contexts = [context_text_from_source(source) for source in sources]

        response = response_for_sample(
            response_mode=response_mode,
            sample=sample,
            question=question,
            reference=reference,
            sources=sources,
            mode_label=mode_label,
        )
        expected_ids = expected_chunk_ids(sample)
        exact_scores = exact_retrieval_scores(sources, expected_ids)
        record = {
            "id": sample.get("id") or f"sample_{index:06d}",
            "backend": backend_name,
            "canonical_backend": canonical_backend,
            "question_type": sample.get("question_type"),
            "difficulty": sample.get("difficulty"),
            "user_input": question,
            "reference": reference,
            "retrieved_contexts": contexts,
            "response": response,
            "expected_chunk_ids": expected_ids,
            "retrieved_sources": [compact_source(source) for source in sources],
            "latency_seconds": round(time.time() - started, 4),
            **exact_scores,
        }
        records.append(record)
        if index % 25 == 0:
            print(f"[{backend_name}] prepared {index}/{len(samples)} samples", flush=True)
    return records


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_records_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "id",
        "backend",
        "canonical_backend",
        "question_type",
        "difficulty",
        "exact_hit_at_k",
        "exact_hits",
        "exact_precision",
        "exact_recall",
        "exact_mrr",
        "latency_seconds",
        "user_input",
        "reference",
        "response",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def ragas_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "user_input": record["user_input"],
            "retrieved_contexts": record["retrieved_contexts"],
            "response": record["response"],
            "reference": record["reference"],
        }
        for record in records
    ]


def selected_metric_names(metric_names: list[str], response_mode: str) -> list[str]:
    names = list(dict.fromkeys(metric_names))
    if response_mode == "none":
        names = [name for name in names if name in CONTEXT_METRICS]
    missing = [name for name in names if name not in CONTEXT_METRICS | RESPONSE_METRICS]
    if missing:
        raise ValueError(f"Unsupported metrics: {', '.join(missing)}")
    return names


def build_ragas_metrics(metric_names: list[str]) -> list[Any]:
    from ragas.metrics import (
        answer_correctness,
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    mapping = {
        "context_precision": context_precision,
        "context_recall": context_recall,
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "answer_correctness": answer_correctness,
    }
    return [copy.deepcopy(mapping[name]) for name in metric_names]


def build_evaluator_llm(provider: str, model: str | None, temperature: float) -> Any:
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for --evaluator-provider openai")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model or "gpt-4o-mini", temperature=temperature)
    if provider == "groq":
        if not os.getenv("GROQ_API_KEY"):
            raise RuntimeError("GROQ_API_KEY is required for --evaluator-provider groq")
        from langchain_groq import ChatGroq

        return ChatGroq(model=model or "llama-3.3-70b-versatile", temperature=temperature)
    raise ValueError(f"Unsupported evaluator provider: {provider}")


def resolve_evaluator_provider(value: str) -> str:
    if value != "auto":
        return value
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    raise RuntimeError(
        "No evaluator provider is configured. Set OPENAI_API_KEY or GROQ_API_KEY, "
        "or run with --prepare-only."
    )


def build_embeddings(provider: str, model: str | None) -> Any:
    if provider == "local_bge":
        from langchain_core.embeddings import Embeddings

        class LangChainLocalBgeEmbeddings(LocalBgeEmbeddings, Embeddings):
            pass

        return LangChainLocalBgeEmbeddings()
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for --embedding-provider openai")
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=model or "text-embedding-3-small")
    raise ValueError(f"Unsupported embedding provider: {provider}")


def mean_or_none(values: list[Any]) -> float | None:
    nums = [
        float(value)
        for value in values
        if value is not None
        and not isinstance(value, bool)
        and isinstance(value, (int, float))
        and not math.isnan(float(value))
    ]
    if not nums:
        return None
    return sum(nums) / len(nums)


def exact_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sample_count": len(records),
        "exact_hit_rate": mean_or_none([1.0 if row["exact_hit_at_k"] else 0.0 for row in records]),
        "exact_precision": mean_or_none([row["exact_precision"] for row in records]),
        "exact_recall": mean_or_none([row["exact_recall"] for row in records]),
        "exact_mrr": mean_or_none([row["exact_mrr"] for row in records]),
        "avg_latency_seconds": mean_or_none([row["latency_seconds"] for row in records]),
    }


def run_ragas(
    records: list[dict[str, Any]],
    metric_names: list[str],
    evaluator_provider: str,
    judge_model: str | None,
    embedding_provider: str,
    embedding_model: str | None,
    batch_size: int | None,
    raise_exceptions: bool,
    show_progress: bool,
) -> tuple[dict[str, Any], Any]:
    from datasets import Dataset
    from ragas import evaluate

    dataset = Dataset.from_list(ragas_rows(records))
    llm = build_evaluator_llm(evaluator_provider, judge_model, temperature=0.0)
    embeddings = build_embeddings(embedding_provider, embedding_model)
    result = evaluate(
        dataset=dataset,
        metrics=build_ragas_metrics(metric_names),
        llm=llm,
        embeddings=embeddings,
        batch_size=batch_size,
        raise_exceptions=raise_exceptions,
        show_progress=show_progress,
    )
    summary = {}
    try:
        summary = dict(result)
    except Exception:
        for name in metric_names:
            value = getattr(result, name, None)
            if value is not None:
                summary[name] = value
    return summary, result


def write_ragas_outputs(
    run_dir: Path,
    backend_name: str,
    records: list[dict[str, Any]],
    result: Any,
) -> None:
    try:
        frame = result.to_pandas()
    except Exception:
        return
    frame.insert(0, "id", [row["id"] for row in records])
    frame.insert(1, "backend", [row["backend"] for row in records])
    frame.insert(2, "question_type", [row["question_type"] for row in records])
    frame.insert(3, "difficulty", [row["difficulty"] for row in records])
    frame.to_csv(run_dir / f"{backend_name}_ragas_scores.csv", index=False, encoding="utf-8-sig")


def write_comparison_csv(path: Path, summaries: list[dict[str, Any]]) -> None:
    keys: list[str] = []
    for summary in summaries:
        for key in summary:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(summaries)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate VLegalAI RAG and GraphRAG backends with RAGAS."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--backends", nargs="+", default=["rag", "graphrag"])
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--metrics", nargs="+", default=DEFAULT_METRICS)
    parser.add_argument(
        "--response-mode",
        choices=["generate", "dataset", "reference", "none"],
        default="generate",
        help=(
            "generate calls the app LLM, dataset uses ragas_fields.response, "
            "reference is diagnostic, none runs context metrics only."
        ),
    )
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--evaluator-provider",
        choices=["auto", "openai", "groq"],
        default=os.getenv("RAGAS_EVALUATOR_PROVIDER", "auto"),
    )
    parser.add_argument("--judge-model", default=os.getenv("RAGAS_EVALUATOR_MODEL"))
    parser.add_argument(
        "--embedding-provider",
        choices=["local_bge", "openai"],
        default=os.getenv("RAGAS_EMBEDDING_PROVIDER", "local_bge"),
    )
    parser.add_argument("--embedding-model", default=os.getenv("RAGAS_EMBEDDING_MODEL"))
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--raise-exceptions", action="store_true")
    parser.add_argument("--no-progress", action="store_true")
    return parser.parse_args()


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    args = parse_args()

    if not args.dataset.exists():
        raise FileNotFoundError(args.dataset)
    samples = load_eval_samples(args.dataset, offset=args.offset, limit=args.limit)
    if not samples:
        raise ValueError("No samples selected")

    metric_names = selected_metric_names(args.metrics, args.response_mode)
    run_dir = args.out_dir / now_slug()
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Dataset: {args.dataset}")
    print(f"Samples: {len(samples)} (offset={args.offset}, limit={args.limit})")
    print(f"Run dir: {run_dir}")
    print(f"Metrics: {', '.join(metric_names)}")
    if args.response_mode == "generate" and not os.getenv("GROQ_API_KEY"):
        print("Warning: GROQ_API_KEY is not set. Generated responses will use fallback text.")

    summaries: list[dict[str, Any]] = []
    for backend in args.backends:
        backend_name = backend_slug(backend)
        print(f"Preparing backend: {backend_name}", flush=True)
        records = build_records_for_backend(
            backend=backend,
            samples=samples,
            top_k=args.top_k,
            response_mode=args.response_mode,
        )
        write_jsonl(run_dir / f"{backend_name}_prepared.jsonl", records)
        write_records_csv(run_dir / f"{backend_name}_prepared.csv", records)

        summary = {
            "backend": backend_name,
            "canonical_backend": records[0]["canonical_backend"] if records else normalize_backend(backend),
            "response_mode": args.response_mode,
            "top_k": args.top_k,
            **exact_summary(records),
        }

        if not args.prepare_only:
            evaluator_provider = resolve_evaluator_provider(args.evaluator_provider)
            ragas_summary, ragas_result = run_ragas(
                records=records,
                metric_names=metric_names,
                evaluator_provider=evaluator_provider,
                judge_model=args.judge_model,
                embedding_provider=args.embedding_provider,
                embedding_model=args.embedding_model,
                batch_size=args.batch_size,
                raise_exceptions=args.raise_exceptions,
                show_progress=not args.no_progress,
            )
            write_ragas_outputs(run_dir, backend_name, records, ragas_result)
            for key, value in ragas_summary.items():
                summary[f"ragas_{key}"] = value

        summaries.append(summary)
        (run_dir / f"{backend_name}_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    comparison_path = run_dir / "comparison.csv"
    write_comparison_csv(comparison_path, summaries)
    (run_dir / "comparison.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Comparison written to: {comparison_path}")


if __name__ == "__main__":
    main()
