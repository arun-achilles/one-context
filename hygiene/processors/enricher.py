import anthropic
from hygiene.models import RawContent

client = anthropic.Anthropic()

SYSTEM_PROMPT = """You enrich content for a software team knowledge base.
For each document extract:
- A concise 2-3 sentence summary of what it contains and why it matters
- Key entities: service names, team names, feature names, tech names mentioned
- Tags for searchability (kebab-case, e.g. auth, payment-service, mobile-team)"""

BATCH_SIZE = 5


def enrich_batch(items: list[RawContent]) -> list[dict]:
    results = []
    for i in range(0, len(items), BATCH_SIZE):
        results.extend(_enrich_batch(items[i : i + BATCH_SIZE]))
    return results


def _enrich_batch(items: list[RawContent]) -> list[dict]:
    content_list = "\n\n---\n\n".join(
        f"[{idx}] TITLE: {item.title}\nBODY: {item.body[:1500]}"
        for idx, item in enumerate(items)
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Enrich these {len(items)} items:\n\n{content_list}",
            }
        ],
        tools=[
            {
                "name": "enrich_content",
                "description": "Return enrichment for each item in order",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "enrichments": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "summary": {"type": "string"},
                                    "entities": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "tags": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": ["summary", "entities", "tags"],
                            },
                        }
                    },
                    "required": ["enrichments"],
                },
            }
        ],
        tool_choice={"type": "tool", "name": "enrich_content"},
    )

    tool_use = next(b for b in response.content if b.type == "tool_use")
    return tool_use.input["enrichments"]
