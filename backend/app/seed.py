"""Import the user-provided synthetic dataset without overwriting saved work."""

import json
import sqlite3
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from .domain import calculate_rating
from .models import StudentProfile, TaskFields, TaskInput
from .store import DEMO_OWNER, make_draft

# Source checkout: backend/app/seed.py -> repository root.
DATASET = Path(__file__).resolve().parents[2] / "fixtures" / "hackalem_synthetic_data.json"
FIELD_MAP = {"expectedResult": "expected_result", "successCriteria": "success_criteria", "interactionFormat": "interaction_format"}


def seed_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"https://hackalem.example.invalid/stage1/{name}"))


def load_dataset() -> dict:
    with DATASET.open(encoding="utf-8") as source:
        return json.load(source)


def demo_dataset() -> dict:
    data = load_dataset()
    return {**data, "apiIds": {item["id"]: seed_id(item["id"]) for section in ("drafts", "task_cards") for item in data[section]}}


def fields(**values: str) -> TaskFields:
    return TaskFields(**{name: values.get(name, "") for name in TaskFields.model_fields})


def seed_database(connection: sqlite3.Connection) -> None:
    data = load_dataset()
    for section in ("drafts", "task_cards", "teams", "proposals"):
        for record in data[section]:
            connection.execute("INSERT OR IGNORE INTO fixture_records(section, source_id, record_json) VALUES (?, ?, ?)", (section, record["id"], json.dumps(record, ensure_ascii=False)))
    cards = {card["id"]: card for card in data["task_cards"]}
    for source in data["task_cards"]:
        values = {name: source.get(FIELD_MAP.get(name, name)) or "" for name in TaskFields.model_fields}
        task = make_draft(TaskInput(fields=fields(**values), company=source["business_name"], topic=source["topic"], requiredSkills=[]), task_id=seed_id(source["id"]))
        task.sourceId = source["id"]
        task.sourceDraftId = source["source_draft_id"]
        task.industry = source["industry"]
        task.confirmed = source["confirmed_by_business"]
        task.confirmedFields = [name for name in TaskFields.model_fields if FIELD_MAP.get(name, name) in source["confirmed_fields"]]
        task.published = source["publication_status"] == "published"
        task.publishedRevision = task.revision if task.published else None
        task.rating = calculate_rating(task.fields, confirmed=task.confirmed, confirmed_fields=task.confirmedFields)
        if task.rating.score != source["rating"]["total"]:
            raise ValueError(f"Dataset rating mismatch: {source['id']}")
        connection.execute("INSERT OR IGNORE INTO tasks(id, owner_id, draft_json, published_json) VALUES (?, ?, ?, ?)", (task.id, DEMO_OWNER, task.model_dump_json(), task.model_dump_json() if task.published else None))
    for source in data["drafts"]:
        card = cards[source["card_id"]]
        task = make_draft(TaskInput(fields=fields(title=card["title"], context=source["text"]), company=card["business_name"], topic=card["topic"], requiredSkills=[]), task_id=seed_id(source["id"]))
        task.sourceId = source["id"]
        task.sourceDraftId = source["id"]
        task.industry = source["industry"]
        connection.execute("INSERT OR IGNORE INTO tasks(id, owner_id, draft_json) VALUES (?, ?, ?)", (task.id, DEMO_OWNER, task.model_dump_json()))

    profiles = [
        ("Аян · демо", "2 курс · Информационные системы", ["Python", "SQL", "Аналитика"], ["Торговля", "Логистика"]),
        ("Дана · демо", "3 курс · Разработка ПО", ["React", "TypeScript", "Figma"], ["Образование"]),
        ("Тимур · демо", "2 курс · Дизайн", ["Дизайн", "Figma"], ["HoReCa", "Сервисы"]),
        ("Алия · демо", "1 курс · Компьютерные науки", ["Python", "Автоматизация"], ["Сервисы"]),
        ("Мирас · демо", "3 курс · Анализ данных", ["SQL", "Аналитика", "Python", "React"], ["Логистика", "Торговля"]),
    ]
    for index, (name, course, skills, interests) in enumerate(profiles):
        profile = StudentProfile(id=seed_id(f"profile-{index + 1}"), name=name, course=course, skills=skills, interests=interests)
        connection.execute("INSERT OR IGNORE INTO profiles(id, profile_json) VALUES (?, ?)", (profile.id, profile.model_dump_json()))
