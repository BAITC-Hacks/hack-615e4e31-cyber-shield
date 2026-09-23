"""Real proposal flow, additive fixture import and snapshot-safe rating migration."""

import json
import sqlite3
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.models import Task, TaskFields

BUSINESS = {"X-Demo-Role": "business"}
STUDENT = {"X-Demo-Role": "student"}


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def task_input(**field_values):
    return {
        "fields": {name: field_values.get(name, "") for name in TaskFields.model_fields},
        "company": "Тестовый бизнес", "topic": "Торговля", "requiredSkills": ["UniqueSkillNobodyHas"],
    }


def new_task(client, *, publish=True):
    task = checked(client.post("/api/tasks", headers=BUSINESS, json=task_input(title="Задача для отклика")), 201)
    if publish:
        checked(client.post(f"/api/tasks/{task['id']}/confirm", headers=BUSINESS))
        task = checked(client.post(f"/api/tasks/{task['id']}/publish", headers=BUSINESS))
    return task


def proposal_input(team_id, **changes):
    return {
        "teamId": team_id,
        "idea": "Собрать веб-форму и проверить её на примерах бизнеса.",
        "plan": ["Уточнить поля и примеры.", "Собрать прототип.", "Показать результат бизнесу."],
        "durationDays": 7,
        "prototypeUrl": "https://prototype.my-project.kz/demo",
        "assumptions": ["Доступ к примерам предоставляет бизнес."],
        **changes,
    }


def submit(client, task_id, team_id, **changes):
    return checked(client.post(f"/api/tasks/{task_id}/proposals", headers=STUDENT, json=proposal_input(team_id, **changes)), 201)


def proposals_for_task(client, task_id):
    return checked(client.get("/api/proposals", params={"taskId": task_id}, headers=BUSINESS))


def test_fixture_teams_and_proposals_are_live_entities_with_original_metadata(client, app_factory):
    dataset = checked(client.get("/api/demo-data"))
    teams = checked(client.get("/api/teams"))
    assert len(teams) == 5
    by_source = {team["sourceId"]: team for team in teams}
    proposals = []
    for source in dataset["teams"]:
        team = by_source[source["id"]]
        UUID(team["id"])
        for field in ("name", "skills", "technologies", "interests"):
            assert team[field] == source[field]
        proposals.extend(checked(client.get("/api/proposals", params={"teamId": team["id"]}, headers=STUDENT)))
    assert len(proposals) == 5
    by_proposal_source = {proposal["sourceId"]: proposal for proposal in proposals}
    for source in dataset["proposals"]:
        proposal = by_proposal_source[source["id"]]
        UUID(proposal["id"])
        assert proposal["taskId"] == dataset["apiIds"][source["task_id"]]
        assert proposal["teamId"] == by_source[source["team_id"]]["id"]
        assert proposal["idea"] == source["idea"]
        assert proposal["plan"] == [step["description"] for step in source["plan"]]
        assert proposal["durationDays"] == source["duration_days"]
        assert proposal["prototypeUrl"] == source["prototype_url"]
        assert proposal["prototypeIsPlaceholder"] is source["prototype_url_is_placeholder"]
        assert proposal["assumptions"] == source["assumptions"]
        assert proposal["createdAt"] == source["submitted_at"]
        assert proposal["status"] == "submitted"
    target = proposals[0]
    changed = checked(client.put(f"/api/proposals/{target['id']}/decision", headers=BUSINESS, json={"status": "accepted", "comment": "Начнём с уточнения данных."}))
    task = new_task(client)
    user_proposal = submit(client, task["id"], teams[0]["id"])
    with TestClient(app_factory()) as restarted:
        assert checked(restarted.get("/api/teams")) == teams
        restored = proposals_for_task(restarted, target["taskId"])
        assert next(item for item in restored if item["id"] == target["id"]) == changed
        assert proposals_for_task(restarted, task["id"]) == [user_proposal]
        all_ids = [item["id"] for team in teams for item in checked(restarted.get("/api/proposals", params={"teamId": team["id"]}, headers=STUDENT))]
        assert len(all_ids) == len(set(all_ids)) == 6


def test_any_team_can_submit_repeated_proposals_to_zero_score_task_without_assignment(client, app_factory):
    teams = checked(client.get("/api/teams"))
    task = new_task(client)
    assert task["rating"]["score"] == 0
    before_task = checked(client.get(f"/api/tasks/{task['id']}"))
    first = submit(client, task["id"], teams[0]["id"])
    second = submit(client, task["id"], teams[0]["id"], idea="Другой вариант решения той же команды.")
    third = submit(client, task["id"], teams[1]["id"])
    assert len({first["id"], second["id"], third["id"]}) == 3
    assert all(item["status"] == "submitted" for item in proposals_for_task(client, task["id"]))
    assert "sourceId" not in first
    assert not first["prototypeIsPlaceholder"]
    assert first["createdAt"].endswith("Z") and first["updatedAt"].endswith("Z")
    assert checked(client.get(f"/api/tasks/{task['id']}")) == before_task
    with TestClient(app_factory()) as restarted:
        assert {item["id"] for item in proposals_for_task(restarted, task["id"])} == {first["id"], second["id"], third["id"]}


def test_manual_business_decisions_allow_zero_one_many_and_do_not_change_other_proposals(client):
    teams = checked(client.get("/api/teams"))
    task = new_task(client)
    first = submit(client, task["id"], teams[0]["id"])
    second = submit(client, task["id"], teams[1]["id"])
    third = submit(client, task["id"], teams[2]["id"])
    for proposal in (first, second):
        result = checked(client.put(f"/api/proposals/{proposal['id']}/decision", headers=BUSINESS, json={"status": "accepted", "comment": "Готовы продолжить обсуждение."}))
        assert result["status"] == "accepted"
        assert result["createdAt"] == proposal["createdAt"]
    current = {item["id"]: item for item in proposals_for_task(client, task["id"])}
    assert current[third["id"]] == third
    assert sum(item["status"] == "accepted" for item in current.values()) == 2
    for proposal in (first, second):
        checked(client.put(f"/api/proposals/{proposal['id']}/decision", headers=BUSINESS, json={"status": "rejected", "comment": "Пока не выбираем команду."}))
    assert not any(item["status"] == "accepted" for item in proposals_for_task(client, task["id"]))
    reset = checked(client.put(f"/api/proposals/{first['id']}/decision", headers=BUSINESS, json={"status": "submitted", "comment": "Нужно обсудить ещё раз."}))
    assert reset["status"] == "submitted"
    assert reset["decisionComment"] == "Нужно обсудить ещё раз."


def test_private_task_unknown_task_and_unknown_team_are_rejected(client):
    team = checked(client.get("/api/teams"))[0]
    private = new_task(client, publish=False)
    assert client.post(f"/api/tasks/{private['id']}/proposals", headers=STUDENT, json=proposal_input(team["id"])).status_code == 404
    assert client.post(f"/api/tasks/{uuid4()}/proposals", headers=STUDENT, json=proposal_input(team["id"])).status_code == 404
    public = new_task(client)
    assert client.post(f"/api/tasks/{public['id']}/proposals", headers=STUDENT, json=proposal_input(str(uuid4()))).status_code == 404
    assert proposals_for_task(client, private["id"]) == []


def test_role_guards_and_unambiguous_query_filters(client):
    team = checked(client.get("/api/teams"))[0]
    task = new_task(client)
    for role in ({}, BUSINESS):
        assert client.post(f"/api/tasks/{task['id']}/proposals", headers=role, json=proposal_input(team["id"])).status_code == 403
    proposal = submit(client, task["id"], team["id"])
    for role in ({}, STUDENT):
        assert client.put(f"/api/proposals/{proposal['id']}/decision", headers=role, json={"status": "accepted", "comment": ""}).status_code == 403
        assert client.get("/api/proposals", headers=role, params={"taskId": task["id"]}).status_code == 403
    for role in ({}, BUSINESS):
        assert client.get("/api/proposals", headers=role, params={"teamId": team["id"]}).status_code == 403
    for params in ({}, {"teamId": team["id"], "taskId": task["id"]}, {"teamId": "not-uuid"}):
        assert client.get("/api/proposals", headers=STUDENT, params=params).status_code == 422
    assert client.get("/api/proposals", headers=STUDENT, params={"teamId": str(uuid4())}).status_code == 404
    assert client.put(f"/api/proposals/{uuid4()}/decision", headers=BUSINESS, json={"status": "accepted"}).status_code == 404


@pytest.mark.parametrize("changes", [
    {"idea": " "}, {"idea": "x" * 6001}, {"teamId": "team_001"},
    {"plan": []}, {"plan": [""]}, {"plan": ["x"] * 21}, {"plan": ["x" * 1001]},
    {"durationDays": 0}, {"durationDays": 366}, {"durationDays": 1.5}, {"durationDays": True},
    {"prototypeUrl": "javascript:alert(1)"}, {"prototypeUrl": "file:///tmp/demo"},
    {"prototypeUrl": "//example.com/demo"}, {"prototypeUrl": "https:example.com"},
    {"prototypeUrl": "https://"}, {"prototypeUrl": "https://example.com/ bad"},
    {"prototypeUrl": "https://example.com/" + "x" * 2048},
    {"assumptions": ["x"] * 21}, {"assumptions": [""]}, {"status": "accepted"},
])
def test_proposal_input_bounds_types_and_safe_url_schemes(client, changes):
    team = checked(client.get("/api/teams"))[0]
    task = new_task(client)
    response = client.post(f"/api/tasks/{task['id']}/proposals", headers=STUDENT, json=proposal_input(team["id"], **changes))
    assert response.status_code == 422, response.text
    assert "detail" in response.json()
    assert proposals_for_task(client, task["id"]) == []


@pytest.mark.parametrize("url", ["https://example.com/demo", "http://prototype.example.org", "https://demo.invalid/prototype"])
def test_reserved_demo_urls_keep_placeholder_flag(client, url):
    team = checked(client.get("/api/teams"))[0]
    task = new_task(client)
    proposal = submit(client, task["id"], team["id"], prototypeUrl=url)
    assert proposal["prototypeUrl"] == url
    assert proposal["prototypeIsPlaceholder"] is True


def test_assumptions_can_be_omitted(client):
    team = checked(client.get("/api/teams"))[0]
    task = new_task(client)
    payload = proposal_input(team["id"])
    del payload["assumptions"]
    proposal = checked(client.post(f"/api/tasks/{task['id']}/proposals", headers=STUDENT, json=payload), 201)
    assert proposal["assumptions"] == []


def test_student_proposal_title_never_exposes_unpublished_edits_and_foreign_owner_blocks_business(client, app_db_path):
    team = checked(client.get("/api/teams"))[0]
    task = new_task(client)
    proposal = submit(client, task["id"], team["id"])
    checked(client.put(f"/api/tasks/{task['id']}", headers=BUSINESS, json=task_input(title="Приватное новое название")))
    listed = checked(client.get("/api/proposals", headers=STUDENT, params={"teamId": team["id"]}))
    assert next(item for item in listed if item["id"] == proposal["id"])["taskTitle"] == task["fields"]["title"]
    with sqlite3.connect(app_db_path) as connection:
        connection.execute("UPDATE tasks SET owner_id = ? WHERE id = ?", ("another-business", task["id"]))
    assert client.get("/api/proposals", headers=BUSINESS, params={"taskId": task["id"]}).status_code == 404
    assert client.put(f"/api/proposals/{proposal['id']}/decision", headers=BUSINESS, json={"status": "accepted"}).status_code == 404


def test_invalid_business_decision_cannot_change_proposal(client):
    team = checked(client.get("/api/teams"))[0]
    task = new_task(client)
    proposal = submit(client, task["id"], team["id"])
    for payload in ({"status": "assigned"}, {"status": "accepted", "comment": "x" * 2001}, {"status": "accepted", "taskId": str(uuid4())}):
        assert client.put(f"/api/proposals/{proposal['id']}/decision", headers=BUSINESS, json=payload).status_code == 422
    assert proposals_for_task(client, task["id"]) == [proposal]


def test_rating_version_migration_preserves_separate_snapshots_and_all_user_state(client, app_factory, app_db_path):
    from app.domain import calculate_rating
    from app.quality import QUALITY_VERSION

    public = checked(client.get("/api/tasks"))[0]
    draft_input = {key: deepcopy(public[key]) for key in ("fields", "company", "topic", "requiredSkills")}
    draft_input["fields"]["context"] = "Новое описание пока находится только в закрытом черновике."
    draft = checked(client.put(f"/api/tasks/{public['id']}", headers=BUSINESS, json=draft_input))
    team = checked(client.get("/api/teams"))[0]
    proposal = submit(client, public["id"], team["id"])
    proposal = checked(client.put(f"/api/proposals/{proposal['id']}/decision", headers=BUSINESS, json={"status": "accepted", "comment": "Сохранить решение при миграции."}))
    old_snapshots = []
    for snapshot in (draft, public):
        old = deepcopy(snapshot)
        for key in ("rating", "previewRating"):
            old[key]["quality"] = None
            old[key]["score"] = 99
        old_snapshots.append(old)
    with sqlite3.connect(app_db_path) as connection:
        connection.execute("UPDATE tasks SET draft_json = ?, published_json = ? WHERE id = ?", (
            json.dumps(old_snapshots[0]), json.dumps(old_snapshots[1]), public["id"],
        ))
        connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)", ("rating_version", "older-formula"))
    with TestClient(app_factory()) as restarted:
        new_draft = checked(restarted.get(f"/api/tasks/{public['id']}?view=business", headers=BUSINESS))
        new_public = checked(restarted.get(f"/api/tasks/{public['id']}"))
        for old, current in zip(old_snapshots, (new_draft, new_public)):
            assert {key: value for key, value in current.items() if key not in ("rating", "previewRating")} == {
                key: value for key, value in old.items() if key not in ("rating", "previewRating")
            }
            model = Task.model_validate(current)
            assert current["rating"] == calculate_rating(model.fields, confirmed=model.confirmed, confirmed_fields=model.confirmedFields).model_dump()
            assert current["previewRating"] == calculate_rating(model.fields).model_dump()
            assert current["rating"]["quality"] is not None
        assert new_draft["fields"] != new_public["fields"]
        assert new_draft["rating"]["score"] == 0
        assert next(item for item in proposals_for_task(restarted, public["id"]) if item["id"] == proposal["id"]) == proposal
    with sqlite3.connect(app_db_path) as connection:
        assert connection.execute("SELECT value FROM metadata WHERE key = ?", ("rating_version",)).fetchone()[0] == str(QUALITY_VERSION)
        first_migration = connection.execute("SELECT draft_json, published_json FROM tasks WHERE id = ?", (public["id"],)).fetchone()
    with TestClient(app_factory()):
        pass
    with sqlite3.connect(app_db_path) as connection:
        assert connection.execute("SELECT draft_json, published_json FROM tasks WHERE id = ?", (public["id"],)).fetchone() == first_migration
