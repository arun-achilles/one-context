import os
import re
from datetime import datetime
from atlassian import Confluence
from hygiene.models import RawContent
from connectors.base import BaseConnector

BODY_CAP = 5000  # chars — enough context without ballooning embeddings


class ConfluenceExtractor(BaseConnector):
    def _get_client(self) -> Confluence:
        return Confluence(
            url=os.environ["CONFLUENCE_URL"],
            username=os.environ["CONFLUENCE_USERNAME"],
            password=os.environ["CONFLUENCE_API_TOKEN"],
        )

    def validate_config(self, config: dict) -> None:
        if "spaces" not in config or not config["spaces"]:
            raise ValueError("confluence source requires at least one space key under 'spaces'")

    def extract(self, config: dict) -> list[RawContent]:
        """
        config keys: spaces (list[str]), max_results (int, optional)
        """
        self.validate_config(config)
        self.client = self._get_client()
        space_keys = config["spaces"]
        max_results = config.get("max_results", 300)
        exclude_labels = set(config.get("exclude_labels", []))

        items = []
        for space in space_keys:
            pages = self.client.get_all_pages_from_space(
                space,
                start=0,
                limit=max_results,
                expand="body.storage,version,history",
            )
            for page in pages:
                if exclude_labels:
                    page_labels = {
                        lbl["name"]
                        for lbl in page.get("metadata", {}).get("labels", {}).get("results", [])
                    }
                    if page_labels & exclude_labels:
                        continue
                body = self._strip_html(
                    page.get("body", {}).get("storage", {}).get("value", "")
                )
                if not body.strip():
                    continue
                items.append(RawContent(
                    id=f"confluence:{page['id']}",
                    source="confluence",
                    title=page.get("title", ""),
                    body=body[:BODY_CAP],
                    url=(
                        f"{os.environ['CONFLUENCE_URL']}"
                        f"{page.get('_links', {}).get('webui', '')}"
                    ),
                    last_updated=datetime.fromisoformat(
                        page.get("version", {})
                        .get("when", "2020-01-01T00:00:00.000Z")
                        .replace("Z", "+00:00")
                    ),
                    author=(
                        page.get("history", {})
                        .get("lastUpdated", {})
                        .get("by", {})
                        .get("displayName")
                    ),
                    metadata={
                        "space": space,
                        "version": page.get("version", {}).get("number", 1),
                    },
                ))
        return items

    def _strip_html(self, html: str) -> str:
        return re.sub(r"<[^>]+>", " ", html).strip()
