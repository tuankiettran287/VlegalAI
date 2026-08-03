from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RetrievalRoute = Literal["single_hop", "multi_hop", "multi_abstract"]


@dataclass(frozen=True, slots=True)
class ChatProcessingProfile:
    route: RetrievalRoute
    thinking_budget: int
    max_output_tokens: int
    retrieval_top_k: int | None
    retrieval_query_limit: int


CHAT_PROCESSING_PROFILES: dict[RetrievalRoute, ChatProcessingProfile] = {
    "single_hop": ChatProcessingProfile(
        route="single_hop",
        thinking_budget=0,
        max_output_tokens=1_800,
        retrieval_top_k=8,
        retrieval_query_limit=3,
    ),
    "multi_hop": ChatProcessingProfile(
        route="multi_hop",
        thinking_budget=1_024,
        max_output_tokens=3_600,
        retrieval_top_k=None,
        retrieval_query_limit=5,
    ),
    "multi_abstract": ChatProcessingProfile(
        route="multi_abstract",
        thinking_budget=4_096,
        max_output_tokens=8_192,
        retrieval_top_k=16,
        retrieval_query_limit=5,
    ),
}


def chat_profile_for_route(route: RetrievalRoute | str) -> ChatProcessingProfile:
    return CHAT_PROCESSING_PROFILES.get(
        str(route).strip().lower(),  # type: ignore[arg-type]
        CHAT_PROCESSING_PROFILES["multi_hop"],
    )
