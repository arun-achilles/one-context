from connectors.base import BaseConnector

# Registry maps source type keys (as used in onecontext.yaml) to connector classes.
# Import connectors lazily to avoid loading optional dependencies (e.g. PyGithub)
# when they are not configured.
def _get_registry() -> dict[str, type[BaseConnector]]:
    from hygiene.extractors.jira_extractor import JiraExtractor
    from hygiene.extractors.confluence_extractor import ConfluenceExtractor
    from hygiene.extractors.github_extractor import GitHubExtractor
    return {
        "jira": JiraExtractor,
        "confluence": ConfluenceExtractor,
        "code": GitHubExtractor,    # primary key — works with any git host
        "github": GitHubExtractor,  # backward-compat alias
    }


def get_connector(source_type: str) -> BaseConnector:
    registry = _get_registry()
    cls = registry.get(source_type)
    if cls is None:
        raise ValueError(
            f"Unknown source type '{source_type}'. "
            f"Available: {list(registry.keys())}"
        )
    return cls()
