import os
from datetime import datetime
from atlassian import Jira
from hygiene.models import RawContent
from connectors.base import BaseConnector

PAGE_SIZE = 100


class JiraExtractor(BaseConnector):
    def _get_client(self) -> Jira:
        return Jira(
            url=os.environ["JIRA_URL"],
            username=os.environ["JIRA_USERNAME"],
            password=os.environ["JIRA_API_TOKEN"],
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def list_boards(self) -> list[dict]:
        """Helper: print all boards the account can see, so you can pick IDs."""
        client = self._get_client()
        boards = []
        start = 0
        while True:
            page = client.get(
                "rest/agile/1.0/board",
                params={"startAt": start, "maxResults": PAGE_SIZE},
            )
            values = page.get("values", [])
            boards.extend(values)
            if page.get("isLast", True) or len(values) < PAGE_SIZE:
                break
            start += PAGE_SIZE
        return boards



    def validate_config(self, config: dict) -> None:
        if "boards" not in config or not config["boards"]:
            raise ValueError("jira source requires at least one board ID under 'boards'")

    def extract(self, config: dict) -> list[RawContent]:
        """
        Extract all issues from one or more Jira boards.
        config keys: boards (list[int]), custom_fields (dict, optional)
        Deduplicates — an issue on multiple boards is only returned once.
        """
        self.validate_config(config)
        self.client = self._get_client()
        self._custom_fields = config.get("custom_fields", {})
        board_ids = config["boards"]

        seen: set[str] = set()
        items: list[RawContent] = []

        for board_id in board_ids:
            board_name = self._get_board_name(board_id)
            print(f"  Board {board_id} ({board_name})...")
            for issue in self._fetch_board_issues(board_id):
                key = issue["key"]
                if key in seen:
                    continue
                seen.add(key)
                items.append(self._to_raw_content(issue, board_id, board_name))

        return items

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _get_board_name(self, board_id: int) -> str:
        try:
            board = self.client.get(f"rest/agile/1.0/board/{board_id}")
            return board.get("name", str(board_id))
        except Exception:
            return str(board_id)

    def _fetch_board_issues(self, board_id: int):
        """
        Pages through all issues on a board — backlog + all sprints combined.
        Uses the Agile board endpoint so we get sprint context alongside each issue.
        """
        start = 0
        # Request sprint field (customfield_10020) alongside standard fields
        fields = (
            "summary,description,status,issuetype,priority,assignee,"
            "labels,comment,updated,customfield_10014,customfield_10020,"
            "customfield_acceptance_criteria"
        )
        while True:
            response = self.client.get(
                f"rest/agile/1.0/board/{board_id}/issue",
                params={
                    "startAt": start,
                    "maxResults": PAGE_SIZE,
                    "fields": fields,
                },
            )
            issues = response.get("issues", [])
            yield from issues
            total = response.get("total", 0)
            start += len(issues)
            if start >= total or not issues:
                break

    def _to_raw_content(self, issue: dict, board_id: int, board_name: str) -> RawContent:
        fields = issue["fields"]
        return RawContent(
            id=f"jira:{issue['key']}",
            source="jira",
            title=fields.get("summary", ""),
            body=self._build_body(fields),
            url=f"{os.environ['JIRA_URL']}/browse/{issue['key']}",
            last_updated=datetime.fromisoformat(
                fields["updated"].replace("Z", "+00:00")
            ),
            author=(
                (fields.get("assignee") or {}).get("displayName")
            ),
            metadata={
                "status": (fields.get("status") or {}).get("name"),
                "issue_type": (fields.get("issuetype") or {}).get("name"),
                "priority": (fields.get("priority") or {}).get("name"),
                "labels": fields.get("labels") or [],
                "board_id": board_id,
                "board_name": board_name,
                "epic_link": fields.get(self._custom_fields.get("epic_link", "customfield_10014")),
                "sprint": self._extract_sprint(fields.get("customfield_10020")),
            },
        )

    def _build_body(self, fields: dict) -> str:
        parts = []
        if fields.get("description"):
            parts.append(str(fields["description"]))
        ac_field = self._custom_fields.get("acceptance_criteria", "customfield_acceptance_criteria")
        if fields.get(ac_field):
            parts.append(f"Acceptance Criteria:\n{fields[ac_field]}")
        comments = fields.get("comment", {}).get("comments", [])
        if comments:
            recent = comments[-3:]
            parts.append(
                "Recent Comments:\n"
                + "\n".join(
                    f"- {c['author']['displayName']}: {c['body']}"
                    for c in recent
                )
            )
        return "\n\n".join(parts)

    def _extract_sprint(self, sprint_field) -> dict | None:
        """Sprint field is a list; return the most recent sprint's name + state."""
        if not sprint_field:
            return None
        # Take the last sprint in the list (most recent)
        sprint = sprint_field[-1] if isinstance(sprint_field, list) else sprint_field
        return {
            "name": sprint.get("name"),
            "state": sprint.get("state"),  # active | closed | future
        }
