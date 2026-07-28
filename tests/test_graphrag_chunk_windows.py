from __future__ import annotations

from collections import OrderedDict

from app.legal_graphrag import (
    CHUNK_WINDOW_WORDS,
    LegalGraphBuilder,
    embedding_text_windows,
)


def test_short_embedding_text_is_not_split() -> None:
    text = "Quy định về quyền và nghĩa vụ của người lao động."

    assert embedding_text_windows(text) == [text]


def test_long_embedding_text_is_split_into_overlapping_bounded_windows() -> None:
    text = " ".join(f"word{index}" for index in range(1000))

    windows = embedding_text_windows(text)
    split_windows = [window.split() for window in windows]

    assert len(windows) == 4
    assert all(len(window) <= CHUNK_WINDOW_WORDS for window in split_windows)
    assert split_windows[0][0] == "word0"
    assert split_windows[1][0] == "word290"
    assert split_windows[-1][-1] == "word999"


def test_builder_windows_every_long_structural_node_type(tmp_path) -> None:
    builder = LegalGraphBuilder(tmp_path, tmp_path)
    node_types = {
        "document": ("VănBản", "document_intro"),
        "article": ("Điều", "article"),
        "clause": ("Khoản", "clause"),
        "point": ("Điểm", "point"),
        "table": ("PhụLục_Bảng", "table"),
    }
    builder.nodes = OrderedDict(
        (
            node_id,
            {
                "node_id": node_id,
                "doc_id": "test-document",
                "node_type": node_type,
                "label": node_id,
                "path_label": f"Test > {node_id}",
                "text": " ".join(f"{node_id}{index}" for index in range(1000)),
            },
        )
        for node_id, (node_type, _) in node_types.items()
    )

    builder._build_chunks()

    for node_id, (_, primary_type) in node_types.items():
        rows = [
            row
            for row in builder.chunks.values()
            if row["node_id"] == node_id
        ]
        assert len(rows) == 4
        assert rows[0]["chunk_type"] == primary_type
        assert all(
            row["chunk_type"] == "sliding"
            for row in rows[1:]
        )
        assert all(
            len(row["text"].split()) <= CHUNK_WINDOW_WORDS
            for row in rows
        )
        assert any(f"{node_id}999" in row["text"] for row in rows)
