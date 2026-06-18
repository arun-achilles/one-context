"""Central model routing policy for One Context.

This module provides task-based model selection and an optional fallback path
so nodes can choose cheap/strong models consistently.
"""

from __future__ import annotations

import os
from typing import Any


MODEL_FAST = os.getenv("MODEL_FAST", "claude-haiku-4-5-20251001")
MODEL_STRONG = os.getenv("MODEL_STRONG", "claude-sonnet-4-6")
MODEL_FALLBACK = os.getenv("MODEL_FALLBACK", MODEL_FAST)
MODEL_FALLBACK_ENABLED = os.getenv("MODEL_FALLBACK_ENABLED", "1").strip() != "0"


TASK_MODEL: dict[str, str] = {
    "router": MODEL_FAST,
    "followup_resolver": MODEL_FAST,
    "retrieval_rewrite": MODEL_FAST,
    "memory_update": MODEL_FAST,
    "conversation_compress": MODEL_FAST,
    "session_summary": MODEL_FAST,
    "remember_extract": MODEL_FAST,
    "clarify": MODEL_FAST,
    "confluence_extract": MODEL_FAST,
    "jira_extract": MODEL_FAST,
    "confluence_create_extract": MODEL_FAST,
    "qa_synthesis": MODEL_STRONG,
    "story_draft": MODEL_STRONG,
    "subtasks_draft": MODEL_STRONG,
}


def model_for(task: str) -> str:
    """Return primary model for a given task key."""
    return TASK_MODEL.get(task, MODEL_FAST)


def call_model(
    client,
    *,
    task: str,
    max_tokens: int,
    system: str,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
):
    """Call Anthropic with task-based routing and optional fallback model."""
    primary = model_for(task)
    fallback = MODEL_FALLBACK

    kwargs: dict[str, Any] = {
        "model": primary,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature

    try:
        return client.messages.create(**kwargs)
    except Exception:
        if not MODEL_FALLBACK_ENABLED or not fallback or fallback == primary:
            raise
        kwargs["model"] = fallback
        return client.messages.create(**kwargs)
