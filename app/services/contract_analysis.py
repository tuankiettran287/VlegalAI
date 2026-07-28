from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Any

MAX_DIFF_CONTEXT_CHARS = 80_000
MAX_DIFF_BLOCK_CHARS = 5_000
MAX_DIFF_BLOCKS = 2_000

_HEADING_RE = re.compile(
    r"^\s*(?:điều|chương|mục|phần|article|chapter|section)\s+"
    r"[0-9ivxlcdm]+(?:[.:)\-\s]+.*)?$",
    re.IGNORECASE,
)
def _ascii(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    ).casefold()


def _clean_block(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _normalized_block(value: str) -> str:
    return re.sub(r"\s+", " ", _ascii(value)).strip()


def contract_clause_headings(text: str, *, limit: int = 12) -> list[str]:
    headings: list[str] = []
    for raw_line in text.splitlines():
        line = _clean_block(raw_line)
        if not line or len(line) > 180:
            continue
        ascii_line = _ascii(line)
        is_contract_title = "hop dong" in ascii_line and len(line.split()) <= 16
        is_heading = bool(_HEADING_RE.match(line))
        if not (is_contract_title or is_heading):
            continue
        # Retrieval only needs the subject and clause labels. Remove long
        # number sequences that may be contract/customer identifiers.
        safe_line = re.sub(r"\d{5,}", "[số]", line)
        if safe_line.casefold() not in {item.casefold() for item in headings}:
            headings.append(safe_line)
        if len(headings) >= limit:
            break
    return headings


def looks_like_contract(text: str) -> bool:
    headings = contract_clause_headings(text, limit=4)
    has_contract_title = any("hop dong" in _ascii(heading) for heading in headings)
    return len(headings) >= 2 or (has_contract_title and len(text) >= 1_000)


def contract_retrieval_query(action: str, *documents: str) -> str:
    headings: list[str] = []
    for document in documents:
        headings.extend(contract_clause_headings(document, limit=8))
    unique_headings = list(dict.fromkeys(heading.casefold() for heading in headings))
    display_headings = []
    for normalized in unique_headings[:12]:
        display_headings.append(next(item for item in headings if item.casefold() == normalized))
    query = (
        f"{action} theo pháp luật Việt Nam. "
        "Tập trung vào hình thức, nội dung bắt buộc, quyền và nghĩa vụ, thanh toán, "
        "trách nhiệm, phạt vi phạm, bồi thường, chấm dứt và giải quyết tranh chấp."
    )
    if display_headings:
        query += " Cấu trúc tài liệu: " + "; ".join(display_headings)
    return query[:1_600]


def _paragraph_blocks(text: str) -> tuple[list[str], bool]:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    paragraphs = [
        _clean_block(block)
        for block in re.split(r"\n\s*\n+", cleaned)
        if _clean_block(block)
    ]
    if len(paragraphs) <= 1:
        paragraphs = [
            _clean_block(line)
            for line in cleaned.splitlines()
            if _clean_block(line)
        ]

    blocks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= MAX_DIFF_BLOCK_CHARS:
            blocks.append(paragraph)
            continue
        sentences = re.split(r"(?<=[.;!?])\s+", paragraph)
        buffer = ""
        for sentence in sentences:
            candidate = f"{buffer} {sentence}".strip()
            if buffer and len(candidate) > MAX_DIFF_BLOCK_CHARS:
                blocks.append(buffer)
                buffer = sentence
            else:
                buffer = candidate
        if buffer:
            blocks.append(buffer)
    return blocks[:MAX_DIFF_BLOCKS], len(blocks) > MAX_DIFF_BLOCKS


def build_contract_diff(original: str, revised: str) -> dict[str, Any]:
    original_blocks, original_blocks_truncated = _paragraph_blocks(original)
    revised_blocks, revised_blocks_truncated = _paragraph_blocks(revised)
    matcher = difflib.SequenceMatcher(
        None,
        [_normalized_block(block) for block in original_blocks],
        [_normalized_block(block) for block in revised_blocks],
        autojunk=True,
    )
    changes: list[dict[str, str]] = []
    counts = {"added": 0, "deleted": 0, "modified": 0}
    used_chars = 0
    omitted = int(original_blocks_truncated or revised_blocks_truncated)

    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        before = "\n\n".join(original_blocks[old_start:old_end])[:MAX_DIFF_BLOCK_CHARS]
        after = "\n\n".join(revised_blocks[new_start:new_end])[:MAX_DIFF_BLOCK_CHARS]
        change_type = {
            "insert": "added",
            "delete": "deleted",
            "replace": "modified",
        }[tag]
        counts[change_type] += 1
        entry_size = len(before) + len(after)
        if used_chars + entry_size > MAX_DIFF_CONTEXT_CHARS:
            omitted += 1
            continue
        changes.append(
            {
                "type": change_type,
                "before": before,
                "after": after,
            }
        )
        used_chars += entry_size

    return {
        "similarity": round(matcher.ratio() * 100),
        "counts": counts,
        "changes": changes,
        "omitted_change_groups": omitted,
        "truncated_for_analysis": bool(omitted),
    }
