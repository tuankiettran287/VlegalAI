from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ChatEffort = Literal["instant", "medium", "high"]


@dataclass(frozen=True, slots=True)
class ChatEffortProfile:
    name: ChatEffort
    thinking_budget: int
    max_output_tokens: int
    retrieval_top_k: int | None
    retrieval_query_limit: int
    skip_query_rewrite: bool


CHAT_EFFORT_PROFILES: dict[ChatEffort, ChatEffortProfile] = {
    "instant": ChatEffortProfile(
        name="instant",
        thinking_budget=0,
        max_output_tokens=900,
        retrieval_top_k=5,
        retrieval_query_limit=1,
        skip_query_rewrite=True,
    ),
    "medium": ChatEffortProfile(
        name="medium",
        thinking_budget=1_024,
        max_output_tokens=3_600,
        retrieval_top_k=None,
        retrieval_query_limit=5,
        skip_query_rewrite=False,
    ),
    "high": ChatEffortProfile(
        name="high",
        thinking_budget=4_096,
        max_output_tokens=8_192,
        retrieval_top_k=16,
        retrieval_query_limit=5,
        skip_query_rewrite=False,
    ),
}


def chat_effort_profile(effort: ChatEffort | str) -> ChatEffortProfile:
    return CHAT_EFFORT_PROFILES.get(
        str(effort).strip().lower(),  # type: ignore[arg-type]
        CHAT_EFFORT_PROFILES["medium"],
    )
