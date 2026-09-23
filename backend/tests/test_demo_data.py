"""Integration checks for the user-provided fixture import and migration."""

import json
from pathlib import Path
import sqlite3
from uuid import UUID

from fastapi.testclient import TestClient

from test_part1_api import (
    BUSINESS, STUDENT, FIELD_NAMES, FULL_FIELDS, checked, empty_fields,
    publish_task, set_test_profile, task_input,
)


FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "hackalem_synthetic_data.json"
FIELD_MAP = {
    "expectedResult": "expected_result",
    "successCriteria": "success_criteria",
    "interactionFormat": "interaction_format",
}


def dataset():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_demo_data_preserves_source_records_and_referential_integrity(client, app_db_path):
    source = dataset()
    response = checked(client.get("/api/demo-data"))
    api_ids = response.pop("apiIds")
    assert response == source
    assert set(api_ids) == {record["id"] for section in ("drafts", "task_cards", "teams", "proposals") for record in source[section]}
    assert len(set(api_ids.values())) == 20
    assert all(UUID(value).version == 5 for value in api_ids.values())
    for section in ("drafts", "task_cards", "teams", "proposals"):
        assert len(source[section]) == 5
        assert len({record["id"] for record in source[section]}) == 5
    task_ids = {task["id"] for task in source["task_cards"]}
    team_ids = {team["id"] for team in source["teams"]}
    assert all(proposal["task_id"] in task_ids and proposal["team_id"] in team_ids for proposal in source["proposals"])
    assert all(proposal["business_decision"] is None for proposal in source["proposals"])
    assert all(task["selected_team_ids"] == [] for task in source["task_cards"])
    # Verify actual persistence, not only an endpoint reading the fixture file.
    with sqlite3.connect(app_db_path) as connection:
        records = connection.execute("SELECT section, source_id, record_json FROM fixture_records").fetchall()
    stored = {(section, source_id): json.loads(raw) for section, source_id, raw in records}
    expected = {(section, record["id"]): record for section in ("drafts", "task_cards", "teams", "proposals") for record in source[section]}
    assert stored == expected


def test_fresh_seed_maps_source_fields_and_recalculates_published_scores(client, app_factory):
    source = dataset()
    mapping = checked(client.get("/api/demo-data"))["apiIds"]
    public = checked(client.get("/api/tasks"))
    business = checked(client.get("/api/tasks?view=business", headers=BUSINESS))
    assert len(public) == 5 and len(business) == 10
    assert len(checked(client.get("/api/profiles"))) == 5
    assert [task["rating"]["score"] for task in public] == [100, 90, 75, 50, 20]
    by_source = {task["sourceId"]: task for task in business}
    for card in source["task_cards"]:
        actual = by_source[card["id"]]
        assert actual["id"] == mapping[card["id"]]
        assert actual["sourceDraftId"] == card["source_draft_id"]
        assert actual["industry"] == card["industry"]
        assert actual["company"] == card["business_name"]
        assert actual["topic"] == card["topic"]
        assert actual["requiredSkills"] == []  # Do not invent requirements.
        assert actual["confirmed"] and actual["published"]
        assert actual["rating"]["score"] == card["rating"]["total"]
        expected_fields = {field: card.get(FIELD_MAP.get(field, field)) or "" for field in FIELD_NAMES}
        assert actual["fields"] == expected_fields
        assert set(actual["confirmedFields"]) == {
            field for field in FIELD_NAMES if FIELD_MAP.get(field, field) in card["confirmed_fields"]
        }
        preview = checked(client.post("/api/rating/preview", json={"fields": actual["fields"]}))
        assert preview["score"] == card["rating"]["total"]
        assert preview["score"] == sum(item["earned"] for item in preview["breakdown"])
    for draft in source["drafts"]:
        actual = by_source[draft["id"]]
        linked = next(card for card in source["task_cards"] if card["id"] == draft["card_id"])
        assert actual["id"] == mapping[draft["id"]]
        assert actual["sourceDraftId"] == draft["id"]
        assert actual["fields"] == empty_fields(title=linked["title"], context=draft["text"])
        assert not actual["confirmed"] and not actual["published"]
        assert actual["rating"]["score"] == 0
    with TestClient(app_factory()) as restarted:
        assert checked(restarted.get("/api/demo-data"))["apiIds"] == mapping
        assert len(checked(restarted.get("/api/tasks?view=business", headers=BUSINESS))) == 10


def test_source_metadata_survives_edits_and_source_fixture_is_read_only(client):
    raw_before = checked(client.get("/api/demo-data"))
    task_id = raw_before["apiIds"]["task_001"]
    public_before = checked(client.get(f"/api/tasks/{task_id}"))
    edited = checked(client.put(
        f"/api/tasks/{task_id}", json=task_input({**public_before["fields"], "data": FULL_FIELDS["data"]}), headers=BUSINESS,
    ))
    for key in ("sourceId", "sourceDraftId", "industry"):
        assert edited[key] == public_before[key]
    assert not edited["confirmed"] and edited["confirmedFields"] is None
    assert edited["rating"]["score"] == 0 and edited["previewRating"]["score"] == 40
    assert checked(client.get(f"/api/tasks/{task_id}")) == public_before
    checked(client.post(f"/api/tasks/{task_id}/confirm", headers=BUSINESS))
    refreshed = checked(client.post(f"/api/tasks/{task_id}/publish", headers=BUSINESS))
    assert refreshed["rating"]["score"] == 40
    assert checked(client.get("/api/demo-data")) == raw_before


def test_imported_confirmation_only_awards_confirmed_components():
    from app.domain import calculate_rating
    from app.models import TaskFields

    fields = TaskFields(**FULL_FIELDS)
    assert calculate_rating(fields, confirmed_fields=["context", "need"]).score == 20
    assert calculate_rating(fields, confirmed_fields=["contact"]).score == 5
    assert calculate_rating(fields, confirmed_fields=["interactionFormat"]).score == 5
    assert calculate_rating(fields, confirmed_fields=["feedbackProcess"]).score == 0
    assert calculate_rating(fields, confirmed_fields=[]).score == 0
    assert calculate_rating(fields, confirmed=False, confirmed_fields=list(FIELD_NAMES)).score == 0


def test_interest_fallback_uses_official_industry_without_inventing_skills(client):
    profile = checked(client.get("/api/profiles"))[0]
    quests = checked(client.get("/api/quests", params={"profileId": profile["id"]}))
    logistics = next(quest for quest in quests if quest["task"]["sourceId"] == "task_005")
    assert logistics["task"]["requiredSkills"] == []
    assert logistics["matchedSkills"] == []
    assert "Логистика" in logistics["matchedInterests"]
    assert all(quest["task"]["rating"]["score"] >= 40 for quest in quests)


def test_interest_match_cannot_bypass_explicit_missing_skills_or_score(client):
    profile = set_test_profile(client, ["TestAlpha"])
    topic = profile["interests"][0].swapcase()
    eligible = publish_task(client, skills=[], topic=topic)
    missing_skill = publish_task(client, skills=["TestBeta"], topic=topic)
    low_rating = publish_task(client, empty_fields(title="Недостаточно сведений", context=FULL_FIELDS["context"]), skills=[], topic=topic)
    quests = checked(client.get("/api/quests", params={"profileId": profile["id"]}))
    assert [quest["task"]["id"] for quest in quests] == [eligible["id"]]
    assert quests[0]["matchedSkills"] == [] and quests[0]["matchedInterests"]
    assert {missing_skill["id"], low_rating["id"]}.isdisjoint({quest["task"]["id"] for quest in quests})


def test_seed_version_upgrade_preserves_user_data_and_is_idempotent(client, app_factory, app_db_path):
    user_task = publish_task(client)
    profile = checked(client.get("/api/profiles"))[0]
    checked(client.put(f"/api/profiles/{profile['id']}/skills", json={"skills": ["LegacySkill"]}, headers=STUDENT))
    checked(client.post(f"/api/quests/{user_task['id']}/decision", json={"profileId": profile["id"], "decision": "saved"}, headers=STUDENT))
    source_mapping = checked(client.get("/api/demo-data"))["apiIds"]
    source_ids = [source_mapping[record["id"]] for section in ("drafts", "task_cards") for record in dataset()[section]]
    # Simulate the prior schema's seed marker only inside this test's database.
    # There are no decisions for removed fixtures, only for the preserved user task.
    with sqlite3.connect(app_db_path) as connection:
        connection.executemany("DELETE FROM tasks WHERE id = ?", [(task_id,) for task_id in source_ids])
        connection.execute("DELETE FROM fixture_records")
        connection.execute("UPDATE metadata SET value = ? WHERE key = ?", ("1", "seed_version"))
    with TestClient(app_factory()) as migrated:
        assert checked(migrated.get(f"/api/tasks/{user_task['id']}")) == user_task
        tasks = checked(migrated.get("/api/tasks?view=business", headers=BUSINESS))
        assert len(tasks) == 11
        assert {task["id"] for task in tasks} == set(source_ids) | {user_task["id"]}
        saved = checked(migrated.get("/api/saved", params={"profileId": profile["id"]}))
        assert [task["id"] for task in saved] == [user_task["id"]]
        profiles = checked(migrated.get("/api/profiles"))
        assert next(item for item in profiles if item["id"] == profile["id"])["skills"] == ["LegacySkill"]
    with TestClient(app_factory()) as repeated:
        assert len(checked(repeated.get("/api/tasks?view=business", headers=BUSINESS))) == 11
    with sqlite3.connect(app_db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fixture_records").fetchone()[0] == 20
        assert connection.execute("SELECT value FROM metadata WHERE key = ?", ("seed_version",)).fetchone()[0] == "2"
