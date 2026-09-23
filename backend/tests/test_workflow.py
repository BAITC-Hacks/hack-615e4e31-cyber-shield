"""End-to-end regression: quality, publication, open proposals and human choice."""

from fastapi.testclient import TestClient

from test_part1_api import (
    BUSINESS, STUDENT, FULL_FIELDS, checked, empty_fields, publish_task, task_input,
)


def test_low_quality_task_accepts_proposals_and_later_improves_without_changing_business_choice(client, app_factory):
    task = publish_task(client, empty_fields(
        title="Сквозной тест: учёт заказов",
        successCriteria="Всё должно работать хорошо и качественно",
    ), skills=["Навык, которого нет у команды"])
    assert task["rating"]["score"] == 0
    criterion = next(item for item in task["rating"]["quality"]["fields"] if item["field"] == "successCriteria")
    assert criterion["status"] == "needs_work"
    assert criterion["suggestion"]

    team = checked(client.get("/api/teams"))[0]
    proposal = checked(client.post(f"/api/tasks/{task['id']}/proposals", headers=STUDENT, json={
        "teamId": team["id"],
        "idea": "Собрать список заказов с фильтрами и импортом тестовой таблицы.",
        "plan": ["Уточнить условия приёмки", "Показать прототип", "Проверить импорт"],
        "durationDays": 7,
        "prototypeUrl": "https://example.com/demo-orders",
        "assumptions": ["Используем только синтетические заказы"],
    }), 201)
    assert proposal["status"] == "submitted"
    # Creation of an application must not silently select the team.
    assert checked(client.get(f"/api/tasks/{task['id']}")) == task
    accepted = checked(client.put(f"/api/proposals/{proposal['id']}/decision", headers=BUSINESS, json={
        "status": "accepted", "comment": "Выбираем эту команду для обсуждения прототипа.",
    }))
    assert accepted["status"] == "accepted"

    changed = checked(client.put(f"/api/tasks/{task['id']}", headers=BUSINESS, json=task_input(
        {**FULL_FIELDS, "title": task["fields"]["title"]}, skills=task["requiredSkills"],
    )))
    assert changed["rating"]["score"] == 0
    assert changed["previewRating"]["score"] == 100
    assert checked(client.get(f"/api/tasks/{task['id']}"))["rating"]["score"] == 0
    checked(client.post(f"/api/tasks/{task['id']}/confirm", headers=BUSINESS))
    assert checked(client.get(f"/api/tasks/{task['id']}"))["rating"]["score"] == 0
    updated = checked(client.post(f"/api/tasks/{task['id']}/publish", headers=BUSINESS))
    assert updated["rating"]["score"] == 100

    with TestClient(app_factory()) as restarted:
        rows = checked(restarted.get("/api/proposals", params={"teamId": team["id"]}, headers=STUDENT))
        restored = next(item for item in rows if item["id"] == proposal["id"])
        assert restored["status"] == "accepted"
        assert restored["idea"] == proposal["idea"]
        assert restored["decisionComment"] == accepted["decisionComment"]
        assert checked(restarted.get(f"/api/tasks/{task['id']}"))["rating"]["score"] == 100
