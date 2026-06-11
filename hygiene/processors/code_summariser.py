"""
Translates source code modules into business-language summaries using Claude Haiku.

This is the critical step that makes code searchable by POs and BAs —
raw code is never embedded; only the business description is.
"""
import json
import anthropic

client = anthropic.Anthropic()

MAX_MODULE_CHARS = 40_000   # ~10k tokens — well within Haiku's context
MAX_FILE_CHARS = 8_000      # per file before truncation

SYSTEM = """You analyse source code to help Product Owners and Business Analysts understand what a software system does.
Your job is to describe code in plain business language — no technical jargon, no implementation details.
Write as if explaining to a non-technical product manager who needs to understand system capabilities before planning new features.
Always respond with valid JSON only."""

PROMPT_TEMPLATE = """Analyse this source code module and describe it in business terms.

Module: {module_path}
Repository: {repo}
Files: {file_list}

--- CODE ---
{code}
--- END CODE ---

Respond with JSON only, no other text:
{{
  "summary": "One paragraph describing what this module does in business terms — what problem it solves, what users/processes it serves.",
  "capabilities": ["list of specific features or flows this module implements, each as a plain English phrase"],
  "integrations": ["list of external services, APIs, or databases this module calls — e.g. Stripe, SendGrid, PostgreSQL"],
  "entities": ["list of core business objects this module manages — e.g. Order, Customer, Invoice"],
  "primary_content_type": "one of: business_flow | api_capability | integration | domain_entity"
}}"""


def summarise_module(
    repo: str,
    module_path: str,
    files: dict[str, str],  # {relative_path: file_content}
) -> dict:
    """
    Summarise a module (directory of related files) in business language.
    Returns the parsed JSON dict from Claude.
    """
    file_list = ", ".join(files.keys())

    # Build code block — cap each file and the total
    code_parts = []
    total_chars = 0
    for path, content in files.items():
        capped = content[:MAX_FILE_CHARS]
        if len(content) > MAX_FILE_CHARS:
            capped += f"\n... [{len(content) - MAX_FILE_CHARS} chars truncated]"
        entry = f"// {path}\n{capped}"
        if total_chars + len(entry) > MAX_MODULE_CHARS:
            code_parts.append(f"// ... remaining files omitted (module too large)")
            break
        code_parts.append(entry)
        total_chars += len(entry)

    code = "\n\n".join(code_parts)
    prompt = PROMPT_TEMPLATE.format(
        module_path=module_path,
        repo=repo,
        file_list=file_list,
        code=code,
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        return json.loads(response.content[0].text)
    except (json.JSONDecodeError, IndexError):
        # Fallback — return a minimal summary if parsing fails
        return {
            "summary": f"Module at {module_path} in {repo}.",
            "capabilities": [],
            "integrations": [],
            "entities": [],
            "primary_content_type": "business_flow",
        }


def summarise_modules_batch(
    repo: str,
    modules: dict[str, dict[str, str]],  # {module_path: {file_path: content}}
    progress_callback=None,
) -> dict[str, dict]:
    """
    Summarise multiple modules. Returns {module_path: summary_dict}.
    Calls progress_callback(done, total) if provided.
    """
    results = {}
    total = len(modules)
    for i, (module_path, files) in enumerate(modules.items()):
        results[module_path] = summarise_module(repo, module_path, files)
        if progress_callback:
            progress_callback(i + 1, total)
    return results
