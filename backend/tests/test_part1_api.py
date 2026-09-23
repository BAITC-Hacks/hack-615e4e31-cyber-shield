"""Public API tests for the first stage, not implementation-shaped unit tests."""

from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient


BUSINESS = {"X-Demo-Role": "business"}
STUDENT = {"X-Demo-Role": "student"}
FIELD_NAMES = (
    "title", "context", "need", "users", "data", "constraints",
    "expectedResult", "successCriteria", "contact", "interactionFormat",
    "feedbackProcess",
)
FULL_FIELDS = {
    "title": "Учёт заказов учебной мастерской",
    "context": "Заказы мастерской собираются вручную в нескольких таблицах.",
    "need": "Объединить заказы в одном списке и сократить повторный ввод.",
    "users": "Два менеджера учебной мастерской.",
    "data": "Доступны 100 синтетических заказов в CSV и описание полей.",
    "constraints": "Срок две недели; использовать только синтетические данные.",
    "expectedResult": "Веб-прототип списка заказов с фильтрами и импортом CSV.",
    "successCriteria": "100 строк импортируются без потерь; фильтр отвечает до 1 секунды.",
    "contact": "demo@example.invalid",
    "interactionFormat": "Видеоконсультация по вторникам на 30 минут.",
    "feedbackProcess": "Бизнес проверяет этап и отвечает в течение двух рабочих дней.",
}


def empty_fields(**updates):
    return {**dict.fromkeys(FIELD_NAMES, ""), **updates}


def task_input(fields=None, skills=None, **updates):
    return {
        "fields": deepcopy(FULL_FIELDS if fields is None else fields),
        "company": "Учебная мастерская",
        "topic": "Образование",
        "requiredSkills": ["TestAlpha"] if skills is None else skills,
        **updates,
    }


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def assert_error(response, status):
    body = checked(response, status)
    assert "detail" in body


def create_task(client, fields=None, skills=None, **updates):
    return checked(
        client.post("/api/tasks", json=task_input(fields, skills, **updates), headers=BUSINESS),
        201,
    )


def publish_task(client, fields=None, skills=None, **updates):
    task = create_task(client, fields, skills, **updates)
    checked(client.post(f"/api/tasks/{task['id']}/confirm", headers=BUSINESS))
    return checked(client.post(f"/api/tasks/{task['id']}/publish", headers=BUSINESS))


def set_test_profile(client, skills):
    profile = checked(client.get("/api/profiles"))[0]
    profile = checked(client.put(
        f"/api/profiles/{profile['id']}/skills", json={"skills": skills}, headers=STUDENT,
    ))
    # Official fixtures may match this profile's interests. Dismiss only the
    # existing catalog before creating the tasks exercised by each test.
    for task in checked(client.get("/api/tasks")):
        checked(client.post(
            f"/api/quests/{task['id']}/decision",
            json={"profileId": profile["id"], "decision": "dismissed"}, headers=STUDENT,
        ))
    return profile


def assert_task_shape(task):
    assert {
        "id", "fields", "company", "topic", "requiredSkills", "published",
        "confirmed", "hasUnpublishedChanges", "rating", "previewRating",
        "revision", "publishedRevision", "updatedAt",
    }.issubset(task)
    UUID(task["id"])
    assert set(task["fields"]) == set(FIELD_NAMES)
    assert all(isinstance(value, str) for value in task["fields"].values())
    assert isinstance(task["revision"], int) and task["revision"] >= 1
    assert isinstance(task["published"], bool)
    assert isinstance(task["confirmed"], bool)
    for key in ("rating", "previewRating"):
        rating = task[key]
        assert 0 <= rating["score"] <= 100
        assert rating["level"] in {"draft", "workable", "ready", "priority"}
        assert rating["score"] == sum(item["earned"] for item in rating["breakdown"])
        assert isinstance(rating["missingFields"], list)


def test_bootstrap_contract_and_restart_do_not_duplicate_seeds(client, app_factory):
    assert checked(client.get("/api/health")) == {"status": "ok", "stage": 1}
    public = checked(client.get("/api/tasks"))
    business = checked(client.get("/api/tasks?view=business", headers=BUSINESS))
    profiles = checked(client.get("/api/profiles"))
    assert len(public) >= 5
    assert sum(not task["published"] for task in business) >= 5
    assert len(profiles) >= 5
    for task in public + business:
        assert_task_shape(task)
    assert all(task["published"] for task in public)
    scores = [task["rating"]["score"] for task in public]
    assert scores == sorted(scores, reverse=True)
    with TestClient(app_factory()) as restarted:
        assert {task["id"] for task in checked(restarted.get("/api/tasks?view=business", headers=BUSINESS))} == {
            task["id"] for task in business
        }
        assert checked(restarted.get("/api/profiles")) == profiles


def test_create_confirm_publish_is_a_real_persisted_flow(client, app_factory):
    draft = create_task(client)
    assert_task_shape(draft)
    assert not draft["confirmed"] and not draft["published"]
    assert draft["rating"]["score"] == 0
    assert draft["previewRating"]["score"] == 100
    assert_error(client.get(f"/api/tasks/{draft['id']}"), 404)
    confirmed = checked(client.post(f"/api/tasks/{draft['id']}/confirm", headers=BUSINESS))
    assert confirmed["confirmed"] and confirmed["rating"]["score"] == 100
    published = checked(client.post(f"/api/tasks/{draft['id']}/publish", headers=BUSINESS))
    assert published["published"] and published["confirmed"]
    assert published["publishedRevision"] == published["revision"]
    assert published["fields"] == FULL_FIELDS
    with TestClient(app_factory()) as restarted:
        public = checked(restarted.get(f"/api/tasks/{draft['id']}"))
        assert_task_shape(public)
        assert public["fields"] == FULL_FIELDS
        assert public["rating"]["score"] == 100


def test_publication_requires_confirmation_and_a_title(client):
    task = create_task(client)
    assert_error(client.post(f"/api/tasks/{task['id']}/publish", headers=BUSINESS), 409)
    untitled = create_task(client, empty_fields())
    checked(client.post(f"/api/tasks/{untitled['id']}/confirm", headers=BUSINESS))
    assert_error(client.post(f"/api/tasks/{untitled['id']}/publish", headers=BUSINESS), 422)
    assert_error(client.get(f"/api/tasks/{untitled['id']}"), 404)


def test_edits_invalidate_confirmation_without_mutating_published_snapshot(client):
    original = publish_task(client)
    comparison = publish_task(client, {**FULL_FIELDS, "contact": ""})
    initial_order = [task["id"] for task in checked(client.get("/api/tasks"))]
    assert initial_order.index(original["id"]) < initial_order.index(comparison["id"])
    original_public = checked(client.get(f"/api/tasks/{original['id']}"))
    changed_fields = {**FULL_FIELDS, "context": "", "title": "Исправленный черновик"}
    edited = checked(client.put(
        f"/api/tasks/{original['id']}", json=task_input(changed_fields), headers=BUSINESS,
    ))
    assert edited["revision"] > original["revision"]
    assert not edited["confirmed"] and edited["hasUnpublishedChanges"]
    assert edited["rating"]["score"] == 0
    assert edited["previewRating"]["score"] == 90
    assert checked(client.get(f"/api/tasks/{original['id']}")) == original_public
    assert_error(client.post(f"/api/tasks/{original['id']}/publish", headers=BUSINESS), 409)
    checked(client.post(f"/api/tasks/{original['id']}/confirm", headers=BUSINESS))
    assert checked(client.get(f"/api/tasks/{original['id']}")) == original_public
    checked(client.post(f"/api/tasks/{original['id']}/publish", headers=BUSINESS))
    refreshed = checked(client.get(f"/api/tasks/{original['id']}"))
    assert refreshed["fields"] == changed_fields
    assert refreshed["rating"]["score"] == 90
    assert refreshed["publishedRevision"] == edited["revision"]
    changed_order = [task["id"] for task in checked(client.get("/api/tasks"))]
    assert changed_order.index(original["id"]) > changed_order.index(comparison["id"])


@pytest.mark.parametrize(("fields", "score", "level"), [
    (empty_fields(title="Заголовок не приносит баллов", context="уточнить", need="неизвестно", data="TBD", users="..."), 0, "draft"),
    (FULL_FIELDS, 100, "priority"),
    (empty_fields(context=FULL_FIELDS["context"], data=FULL_FIELDS["data"], expectedResult=FULL_FIELDS["expectedResult"], interactionFormat=FULL_FIELDS["interactionFormat"]), 50, "workable"),
    (empty_fields(context=FULL_FIELDS["context"], need=FULL_FIELDS["need"], data=FULL_FIELDS["data"], expectedResult=FULL_FIELDS["expectedResult"], successCriteria=FULL_FIELDS["successCriteria"]), 70, "ready"),
])
def test_rating_weights_placeholders_and_breakdown(client, fields, score, level):
    response = checked(client.post("/api/rating/preview", json={"fields": fields}))
    assert response["score"] == score
    assert response["level"] == level
    assert sorted(item["max"] for item in response["breakdown"]) == [10, 10, 10, 15, 15, 20, 20]
    assert sum(item["earned"] for item in response["breakdown"]) == score
    assert all(0 <= item["earned"] <= item["max"] for item in response["breakdown"])
    assert response == checked(client.post("/api/rating/preview", json={"fields": fields}))
    if score < 100:
        assert response["missingFields"]
    else:
        assert response["missingFields"] == []


def test_low_rating_stays_public_filterable_and_can_be_saved(client):
    task = publish_task(client, empty_fields(title="Нужно уточнить детали"), skills=[])
    assert task["rating"]["score"] == 0
    filtered = checked(client.get("/api/tasks", params={"topic": "Образование", "readiness": "draft", "q": "Нужно уточнить детали"}))
    assert [item["id"] for item in filtered] == [task["id"]]
    profile = checked(client.get("/api/profiles"))[0]
    checked(client.post(f"/api/quests/{task['id']}/decision", json={"profileId": profile["id"], "decision": "saved"}, headers=STUDENT))
    saved = checked(client.get("/api/saved", params={"profileId": profile["id"]}))
    assert [item["id"] for item in saved] == [task["id"]]


def test_demo_role_guards_business_reads_and_writes(client):
    task = create_task(client)
    assert_error(client.get("/api/tasks?view=business"), 403)
    assert_error(client.get(f"/api/tasks/{task['id']}?view=business", headers=STUDENT), 403)
    assert_error(client.post("/api/tasks", json=task_input(), headers=STUDENT), 403)
    assert_error(client.put(f"/api/tasks/{task['id']}", json=task_input()), 403)
    for operation in ("confirm", "publish"):
        assert_error(client.post(f"/api/tasks/{task['id']}/{operation}", headers=STUDENT), 403)
    assert_error(client.get(f"/api/tasks/{task['id']}"), 404)
    assert_error(client.get(f"/api/tasks/{uuid4()}?view=business", headers=BUSINESS), 404)


def test_quests_require_every_skill_and_at_least_forty_points(client):
    profile = set_test_profile(client, ["testalpha", "TESTBETA"])
    at_forty = empty_fields(title="Квест на пороге", context=FULL_FIELDS["context"], need=FULL_FIELDS["need"], data=FULL_FIELDS["data"])
    eligible = publish_task(client, at_forty, skills=["TestAlpha", "TestBeta"])
    publish_task(client, skills=["TestAlpha", "TestGamma"])
    publish_task(client, empty_fields(title="Пока мало сведений", data=FULL_FIELDS["data"], context=FULL_FIELDS["context"]), skills=["TestAlpha"])
    publish_task(client, skills=[])
    quests = checked(client.get("/api/quests", params={"profileId": profile["id"]}))
    assert [quest["task"]["id"] for quest in quests] == [eligible["id"]]
    assert {skill.casefold() for skill in quests[0]["matchedSkills"]} == {"testalpha", "testbeta"}
    assert quests[0]["decision"] is None


def test_quest_results_are_limited_to_three(client):
    profile = set_test_profile(client, ["TestAlpha"])
    tasks = [publish_task(client) for _ in range(4)]
    quests = checked(client.get("/api/quests", params={"profileId": profile["id"]}))
    assert len(quests) == 3
    assert {quest["task"]["id"] for quest in quests}.issubset({task["id"] for task in tasks})


def test_saved_and_dismissed_quests_survive_restart_without_assigning_tasks(client, app_factory):
    profile = set_test_profile(client, ["TestAlpha"])
    saved_task, dismissed_task = publish_task(client), publish_task(client)
    before = {task["id"]: checked(client.get(f"/api/tasks/{task['id']}")) for task in (saved_task, dismissed_task)}
    for task, decision in ((saved_task, "saved"), (dismissed_task, "dismissed")):
        assert checked(client.post(
            f"/api/quests/{task['id']}/decision",
            json={"profileId": profile["id"], "decision": decision}, headers=STUDENT,
        )) == {"ok": True}
        assert checked(client.get(f"/api/tasks/{task['id']}")) == before[task["id"]]
    with TestClient(app_factory()) as restarted:
        assert checked(restarted.get("/api/quests", params={"profileId": profile["id"]})) == []
        saved = checked(restarted.get("/api/saved", params={"profileId": profile["id"]}))
        assert [task["id"] for task in saved] == [saved_task["id"]]
        profiles = checked(restarted.get("/api/profiles"))
        assert next(item for item in profiles if item["id"] == profile["id"])["skills"] == profile["skills"]


def test_quest_decisions_validate_role_profile_task_and_state(client):
    profile = checked(client.get("/api/profiles"))[0]
    draft = create_task(client)
    published = publish_task(client)
    decision = {"profileId": profile["id"], "decision": "saved"}
    assert_error(client.post(f"/api/quests/{published['id']}/decision", json=decision), 403)
    assert_error(client.put(f"/api/profiles/{profile['id']}/skills", json={"skills": ["Python"]}, headers=BUSINESS), 403)
    assert_error(client.post(f"/api/quests/{draft['id']}/decision", json=decision, headers=STUDENT), 404)
    assert_error(client.post(f"/api/quests/{uuid4()}/decision", json=decision, headers=STUDENT), 404)
    assert_error(client.post(f"/api/quests/{published['id']}/decision", json={**decision, "profileId": str(uuid4())}, headers=STUDENT), 404)
    assert_error(client.post(f"/api/quests/{published['id']}/decision", json={**decision, "decision": "assigned"}, headers=STUDENT), 422)


def test_sql_payloads_are_data_and_never_expand_access(client):
    initial_ids = {task["id"] for task in checked(client.get("/api/tasks"))}
    payload = "'); DROP TABLE tasks; --"
    task = publish_task(client, {**FULL_FIELDS, "title": payload})
    assert checked(client.get(f"/api/tasks/{task['id']}"))["fields"]["title"] == payload
    assert {item["id"] for item in checked(client.get("/api/tasks"))} == initial_ids | {task["id"]}
    assert checked(client.get("/api/tasks", params={"q": "' OR 1=1 --"})) == []
    assert checked(client.get("/api/tasks", params={"topic": "' OR 1=1 --"})) == []
    assert_error(client.get("/api/tasks/not-a-uuid"), 422)
    assert len(checked(client.get("/api/profiles"))) >= 5


@pytest.mark.parametrize("body", [
    {},
    {"fields": []},
    task_input({**FULL_FIELDS, "context": 42}),
    task_input(skills="Python"),
    task_input(confirmed=True),
    task_input(sourceId="task_001"),
    task_input(confirmedFields=["context", "need"]),
])
def test_invalid_task_schemas_do_not_create_records(client, body):
    before = checked(client.get("/api/tasks?view=business", headers=BUSINESS))
    assert_error(client.post("/api/tasks", json=body, headers=BUSINESS), 422)
    after = checked(client.get("/api/tasks?view=business", headers=BUSINESS))
    assert {task["id"] for task in after} == {task["id"] for task in before}
