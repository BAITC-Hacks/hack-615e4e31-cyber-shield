"""Pure readiness rules; no AI, persistence or team assignment."""

from .models import Rating, RatingItem, Readiness, TaskFields
from .quality import assess_quality, has_content

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
    quality = assess_quality(fields)
    eligible = set(quality.eligibleFields)
    field_quality = {item.field: item for item in quality.fields}
    breakdown: list[RatingItem] = []
    missing_fields: list[str] = []
    for key, label, members in RATING_GROUPS:
        missing = [name for name, _ in members if not has_content(getattr(fields, name))]
        missing_fields.extend(missing)
        earned = sum(weight for name, weight in members if name in eligible and (confirmed_fields is None or name in confirmed_fields)) if confirmed else 0
        breakdown.append(RatingItem(
            key=key,
            label=label,
            earned=earned,
            max=sum(weight for _, weight in members),
            missing=[field_quality[name].suggestion for name, _ in members if name not in eligible],
        ))
    score = sum(item.earned for item in breakdown)
    return Rating(score=score, level=readiness(score), breakdown=breakdown, missingFields=missing_fields, quality=quality)
