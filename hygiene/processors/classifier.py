import anthropic
from hygiene.models import RawContent, ContentType

client = anthropic.Anthropic()

# Cached — reused across every batch call in the same session
SYSTEM_PROMPT = """You are a content classifier for a software team knowledge base.

Content types:
- decision: A team or technical decision that was made
- requirement: A business or functional requirement
- meeting_note: Notes from a meeting
- adr: Architecture Decision Record
- bug: A bug report or incident
- process_doc: Process or workflow documentation
- spec: Technical or product specification
- noise: Low-value content (empty, trivial, templates with no real content)

Quality score (1-5):
1 - Nearly empty or title only
2 - Has content but missing critical context
3 - Useful but incomplete (e.g. story without acceptance criteria)
4 - Good, mostly complete
5 - Excellent — complete with context, decisions, and rationale"""

BATCH_SIZE = 10


class ClassificationResult:
    def __init__(self, content_type: str, quality_score: int, quality_reason: str):
        self.content_type = content_type
        self.quality_score = quality_score
        self.quality_reason = quality_reason


def classify_batch(items: list[RawContent]) -> list[ClassificationResult]:
    results = []
    for i in range(0, len(items), BATCH_SIZE):
        results.extend(_classify_batch(items[i : i + BATCH_SIZE]))
    return results


def _classify_batch(items: list[RawContent]) -> list[ClassificationResult]:
    content_list = "\n\n---\n\n".join(
        f"[{idx}] SOURCE: {item.source}\nTITLE: {item.title}\nBODY: {item.body[:1000]}"
        for idx, item in enumerate(items)
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  # prompt caching
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Classify items 0 to {len(items) - 1}:\n\n{content_list}"
                ),
            }
        ],
        tools=[
            {
                "name": "classify_content",
                "description": "Return classification for all items in order",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "classifications": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content_type": {
                                        "type": "string",
                                        "enum": [t.value for t in ContentType],
                                    },
                                    "quality_score": {
                                        "type": "integer",
                                        "minimum": 1,
                                        "maximum": 5,
                                    },
                                    "quality_reason": {"type": "string"},
                                },
                                "required": [
                                    "content_type",
                                    "quality_score",
                                    "quality_reason",
                                ],
                            },
                        }
                    },
                    "required": ["classifications"],
                },
            }
        ],
        tool_choice={"type": "tool", "name": "classify_content"},
    )

    tool_use = next(b for b in response.content if b.type == "tool_use")
    return [
        ClassificationResult(**c)
        for c in tool_use.input["classifications"]
    ]
