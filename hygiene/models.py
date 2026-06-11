from pydantic import BaseModel
from enum import Enum
from datetime import datetime
from typing import Optional


class ContentType(str, Enum):
    DECISION = "decision"
    REQUIREMENT = "requirement"
    MEETING_NOTE = "meeting_note"
    ADR = "adr"
    BUG = "bug"
    PROCESS_DOC = "process_doc"
    SPEC = "spec"
    NOISE = "noise"


class ContentStatus(str, Enum):
    AUTO_INCLUDED = "auto_included"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class RawContent(BaseModel):
    id: str
    source: str  # "jira" | "confluence" | "github"
    title: str
    body: str
    url: str
    last_updated: datetime
    author: Optional[str] = None
    metadata: dict = {}


class ProcessedContent(BaseModel):
    raw: RawContent
    content_type: Optional[ContentType] = None
    quality_score: Optional[int] = None  # 1-5
    is_stale: bool = False
    staleness_reason: Optional[str] = None
    duplicate_of: Optional[str] = None  # ID of the original
    summary: Optional[str] = None
    entities: list[str] = []
    tags: list[str] = []
    status: ContentStatus = ContentStatus.PENDING_REVIEW
    review_reason: Optional[str] = None
