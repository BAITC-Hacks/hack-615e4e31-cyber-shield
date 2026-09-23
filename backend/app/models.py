"""Validated API models. Field names intentionally match the TypeScript contract."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Readiness = Literal["draft", "workable", "ready", "priority"]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=6000)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Skill = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Skills = Annotated[list[Skill], Field(max_length=20)]


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskFields(APIModel):
    title: Title
    context: Text
    need: Text
    users: Text
    data: Text
    constraints: Text
    expectedResult: Text
    successCriteria: Text
    contact: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
    interactionFormat: Text
    feedbackProcess: Text


def unique_skills(skills: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for skill in skills:
        if skill.casefold() not in seen:
            seen.add(skill.casefold())
            result.append(skill)
    return result


class TaskInput(APIModel):
    fields: TaskFields
    company: Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]
    topic: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)]
    requiredSkills: Skills

    @field_validator("requiredSkills")
    @classmethod
    def deduplicate_skills(cls, skills: list[str]) -> list[str]:
        return unique_skills(skills)


class RatingItem(APIModel):
    key: str
    label: str
    earned: int
    max: int
    missing: list[str]


class Rating(APIModel):
    score: int
    level: Readiness
    breakdown: list[RatingItem]
    missingFields: list[str]


class Task(TaskInput):
    confirmedFields: list[str] | None = None
    sourceId: str | None = None
    sourceDraftId: str | None = None
    industry: str = ""
    id: str
    published: bool
    confirmed: bool
    hasUnpublishedChanges: bool
    rating: Rating
    previewRating: Rating
    revision: int
    publishedRevision: int | None
    updatedAt: str


class StudentProfile(APIModel):
    id: str
    name: str
    course: str
    skills: list[str]
    interests: list[str]


class SkillsInput(APIModel):
    skills: Skills

    @field_validator("skills")
    @classmethod
    def deduplicate_skills(cls, skills: list[str]) -> list[str]:
        return unique_skills(skills)


class RatingInput(APIModel):
    fields: TaskFields


class Quest(APIModel):
    task: Task
    matchedSkills: list[str]
    matchedInterests: list[str] = Field(default_factory=list)
    decision: Literal["saved", "dismissed"] | None


class DecisionInput(APIModel):
    profileId: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    decision: Literal["saved", "dismissed"]
