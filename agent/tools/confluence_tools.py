"""
Confluence read + write tools for the agent.
"""
import os
from atlassian import Confluence
from dotenv import load_dotenv

load_dotenv()


def _client() -> Confluence:
    return Confluence(
        url=os.environ["CONFLUENCE_URL"],
        username=os.environ["CONFLUENCE_USERNAME"],
        password=os.environ["CONFLUENCE_API_TOKEN"],
    )


def _base_url() -> str:
    """Return the Confluence base URL without a trailing /wiki suffix."""
    return os.environ["CONFLUENCE_URL"].rstrip("/").removesuffix("/wiki")


def search_confluence(query: str, space_key: str | None = None, max_results: int = 5) -> list[dict]:
    """Full-text search across Confluence pages."""
    space = space_key or os.environ.get("CONFLUENCE_SPACE_KEY", "CL")
    confluence = _client()
    cql = f'space = "{space}" AND text ~ "{query}" ORDER BY lastModified DESC'
    results = confluence.cql(cql, limit=max_results)
    pages = []
    for r in results.get("results", []):
        pages.append({
            "title": r.get("title", ""),
            "url": _base_url() + r.get("url", ""),
            "excerpt": r.get("excerpt", ""),
        })
    return pages


def update_confluence_page(
    page_title: str,
    new_content: str,
    space_key: str | None = None,
    append: bool = True,
) -> dict:
    """
    Update a Confluence page by appending new_content to the existing body.
    If append=False, prepends. Never overwrites the full page.
    Returns {page_id, url, version}.
    """
    space = space_key or os.environ.get("CONFLUENCE_SPACE_KEY", "CL")
    confluence = _client()

    page = confluence.get_page_by_title(space=space, title=page_title, expand="body.storage,version")
    if not page:
        raise ValueError(f"Confluence page not found: '{page_title}' in space {space}")

    page_id = page["id"]
    current_version = page["version"]["number"]
    existing_body = page["body"]["storage"]["value"]

    # Wrap new content in a simple section
    section = f"<p>{new_content}</p>"
    updated_body = existing_body + section if append else section + existing_body

    confluence.update_page(
        page_id=page_id,
        title=page_title,
        body=updated_body,
        version_increment=1,
    )

    return {
        "page_id": page_id,
        "url": f"{_base_url()}/wiki/spaces/{space}/pages/{page_id}",
        "version": current_version + 1,
    }


def create_confluence_page(
    title: str,
    content: str,
    space_key: str | None = None,
    parent_title: str | None = None,
) -> dict:
    """
    Create a new Confluence page. Returns {page_id, url}.
    """
    space = space_key or os.environ.get("CONFLUENCE_SPACE_KEY", "CL")
    confluence = _client()

    parent_id = None
    if parent_title:
        parent = confluence.get_page_by_title(space=space, title=parent_title)
        if parent:
            parent_id = parent["id"]

    body = f"<p>{content}</p>"
    result = confluence.create_page(
        space=space,
        title=title,
        body=body,
        parent_id=parent_id,
        type="page",
        representation="storage",
    )

    page_id = result.get("id", "")
    return {
        "page_id": page_id,
        "url": f"{_base_url()}/wiki/spaces/{space}/pages/{page_id}",
    }
