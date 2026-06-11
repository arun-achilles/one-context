from abc import ABC, abstractmethod
from hygiene.models import RawContent


class BaseConnector(ABC):
    """
    All data source connectors implement this interface.
    The hygiene pipeline, chunker, embedder, and loader are source-agnostic —
    they only consume RawContent objects returned by extract().
    """

    @abstractmethod
    def extract(self, config: dict) -> list[RawContent]:
        """
        Pull content from the source system.

        config: the source-specific block from onecontext.yaml
                (e.g. {"boards": [1108], "custom_fields": {...}} for Jira)

        Returns: list of RawContent, one per extractable unit.
        IDs must be globally unique — use the pattern "<source>:<external_id>"
        (e.g. "jira:CL-123", "confluence:12345", "github:org/repo:path/to/file").
        """
        ...

    def validate_config(self, config: dict) -> None:
        """
        Raise ValueError if required config keys are missing.
        Called by the pipeline before extract(). Override per connector.
        """
        pass
