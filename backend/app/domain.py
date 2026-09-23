"""Pure readiness rules; no AI, persistence or team assignment."""

import re

from .models import Rating, RatingItem, Readiness, TaskFields

FIELD_LABELS = {
    "context": "Контекст",
    "need": "Потребность",
    "data": "Данные и материалы",
    "expectedResult": "Ожидаемый результат",
    "successCriteria": "Критерии успеха",
    "constraints": "Ограничения",
    "users": "Пользователи",
    "contact": "Контакт",
    "interactionFormat": "Консультации и обратная связь",
    "feedbackProcess": "Порядок обратной связи",
}

RATING_GROUPS = (
    ("contextNeed", "Контекст и потребность", (("context", 10), ("need", 10))),
    ("data", "Данные и материалы", (("data", 20),)),
    ("expectedResult", "Ожидаемый результат", (("expectedResult", 15),)),
    ("successCriteria", "Критерии успеха", (("successCriteria", 15),)),
    ("constraints", "Ограничения", (("constraints", 10),)),
    ("users", "Пользователи", (("users", 10),)),
    ("businessContact", "Связь с бизнесом", (("contact", 5), ("interactionFormat", 5))),
)

PLACEHOLDERS = {"уточнить", "неизвестно", "tbd", "todo", "n/a", "пока неизвестно", "будет уточнено"}


def has_content(value: str) -> bool:
    """Reject empty/punctuation-only text and explicit whole-field placeholders.

    This assesses completion, not the factual truth or quality of a claim.
    """
    normalized = " ".join(value.casefold().split()).strip(" .…!?;:—–-_\"'«»()[]")
    return bool(re.search(r"\w", normalized, flags=re.UNICODE)) and normalized not in PLACEHOLDERS


def readiness(score: int) -> Readiness:
    if score < 40:
        return "draft"
    if score < 70:
        return "workable"
    if score < 90:
        return "ready"
    return "priority"


def calculate_rating(fields: TaskFields, *, confirmed: bool = True, confirmed_fields: list[str] | None = None) -> Rating:
    """Preview defaults to confirmed=True; draft callers explicitly pass False."""
    breakdown: list[RatingItem] = []
    missing_fields: list[str] = []
    for key, label, members in RATING_GROUPS:
        missing = [name for name, _ in members if not has_content(getattr(fields, name))]
        missing_fields.extend(missing)
        earned = sum(weight for name, weight in members if has_content(getattr(fields, name)) and (confirmed_fields is None or name in confirmed_fields)) if confirmed else 0
        breakdown.append(RatingItem(
            key=key,
            label=label,
            earned=earned,
            max=sum(weight for _, weight in members),
            missing=[f"Добавьте: {FIELD_LABELS[name].lower()}" for name in missing],
        ))
    score = sum(item.earned for item in breakdown)
    return Rating(score=score, level=readiness(score), breakdown=breakdown, missingFields=missing_fields)
