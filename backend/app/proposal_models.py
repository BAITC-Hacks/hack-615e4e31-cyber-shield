"""Validated team/proposal contracts; no automatic assignment fields."""

from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, HttpUrl, StringConstraints, field_validator

from .models import APIModel

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
PrototypeURL = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)]
ProposalStatus = Literal["submitted", "accepted", "rejected"]


def validate_prototype_url(value: str) -> str:
    """Validate only; never retrieve the URL or inspect its remote contents."""
    if not value.lower().startswith(("https://", "http://")) or any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError("Укажите корректную ссылку на прототип с http:// или https://")
    HttpUrl(value)
    return value


def is_placeholder_url(value: str) -> bool:
    hostname = (urlsplit(value).hostname or "").lower().rstrip(".")
    reserved = ("example.com", "example.org", "example.net", "example.invalid", "example")
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in reserved) or hostname.endswith((".invalid", ".example"))


class Team(APIModel):
    id: str
    sourceId: str | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    skills: Annotated[list[ShortText], Field(max_length=30)]
    technologies: Annotated[list[ShortText], Field(max_length=30)]
    interests: Annotated[list[ShortText], Field(max_length=30)]


class ProposalInput(APIModel):
    teamId: UUID
    idea: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]
    plan: Annotated[list[ShortText], Field(min_length=1, max_length=20)]
    durationDays: Annotated[int, Field(strict=True, ge=1, le=365)]
    prototypeUrl: PrototypeURL
    assumptions: Annotated[list[ShortText], Field(max_length=20)] = Field(default_factory=list)

    @field_validator("prototypeUrl")
    @classmethod
    def http_url_only(cls, value: str) -> str:
        return validate_prototype_url(value)


class ProposalDecisionInput(APIModel):
    status: ProposalStatus
    comment: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""


class ProposalAttachment(APIModel):
    id: str
    name: str
    size: int
    mediaType: Literal["application/pdf"] = "application/pdf"
    createdAt: str


class ProposalCompletion(APIModel):
    confirmedAt: str
    summary: str
    pointsAwarded: int


class ProposalCompletionInput(APIModel):
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)]


class Proposal(APIModel):
    id: str
    sourceId: str | None = None
    taskId: str
    teamId: str
    team: Team
    idea: str
    plan: list[str]
    durationDays: int
    prototypeUrl: str
    prototypeIsPlaceholder: bool
    assumptions: list[str]
    status: ProposalStatus
    decisionComment: str
    createdAt: str
    updatedAt: str
    taskTitle: str
    attachments: list[ProposalAttachment] = Field(default_factory=list)
    completion: ProposalCompletion | None = None
