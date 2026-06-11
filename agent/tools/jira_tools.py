"""
Jira write + read tools for the agent.
"""
import os
from atlassian import Jira
from dotenv import load_dotenv

load_dotenv()


def _client() -> Jira:
    return Jira(
        url=os.environ["JIRA_URL"],
        username=os.environ["JIRA_USERNAME"],
        password=os.environ["JIRA_API_TOKEN"],
    )


def get_jira_issue(key: str) -> dict:
    """Fetch a single Jira issue by key. Returns a flat dict with key fields."""
    jira = _client()
    issue = jira.issue(key)
    fields = issue.get("fields", {})
    return {
        "key": issue["key"],
        "url": f"{os.environ['JIRA_URL']}/browse/{issue['key']}",
        "summary": fields.get("summary", ""),
        "status": (fields.get("status") or {}).get("name", ""),
        "issue_type": (fields.get("issuetype") or {}).get("name", ""),
        "assignee": ((fields.get("assignee") or {}).get("displayName", "Unassigned")),
        "description": str(fields.get("description") or ""),
        "labels": fields.get("labels", []),
    }


def create_jira_story(
    title: str,
    description: str,
    acceptance_criteria: str,
    labels: list[str] | None = None,
    project_key: str | None = None,
) -> dict:
    """
    Create a Jira story. Returns {key, url}.
    Requires JIRA_PROJECT_KEY in environment (or pass project_key explicitly).
    """
    project = project_key or os.environ.get("JIRA_PROJECT_KEY", "CL")
    jira = _client()

    full_description = description
    if acceptance_criteria:
        full_description += f"\n\n*Acceptance Criteria:*\n{acceptance_criteria}"

    fields = {
        "project": {"key": project},
        "summary": title,
        "description": full_description,
        "issuetype": {"name": "Story"},
    }
    if labels:
        fields["labels"] = labels

    result = jira.create_issue(fields=fields)
    key = result.get("key", "")
    return {
        "key": key,
        "url": f"{os.environ['JIRA_URL']}/browse/{key}",
    }


def search_jira(query: str, project_key: str | None = None, max_results: int = 5) -> list[dict]:
    """Text search across Jira issues in the configured project."""
    project = project_key or os.environ.get("JIRA_PROJECT_KEY", "CL")
    jira = _client()
    jql = f'project = {project} AND text ~ "{query}" ORDER BY updated DESC'
    results = jira.jql(jql, limit=max_results)
    issues = []
    for issue in results.get("issues", []):
        fields = issue.get("fields", {})
        issues.append({
            "key": issue["key"],
            "url": f"{os.environ['JIRA_URL']}/browse/{issue['key']}",
            "summary": fields.get("summary", ""),
            "status": (fields.get("status") or {}).get("name", ""),
        })
    return issues
