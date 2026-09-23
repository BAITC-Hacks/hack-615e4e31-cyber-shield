"""API-level semantic rating safety and short-input regressions, without live AI."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from app.models import TaskInput
from app.quality import SCORED_FIELDS, assess_quality
from test_part1_api import (
    BUSINESS, STUDENT, FULL_FIELDS, checked, create_task, empty_fields,
    publish_task, task_input,
)


def semantic_report(fields, *, reject=("successCriteria",)):
    report = assess_quality(fields)
    report.mode = "openai"
    report.version = "semantic-v1"
    report.model = "test-semantic-model"
    for item in report.fields:
        if item.field in reject:
            item.status = "needs_work"
            item.message = "Для этой задачи ещё не указан достаточный способ проверки."
            item.suggestion = "Уточните условия проверки и ожидаемый результат."
            item.evidence = getattr(fields, item.field)
    report.eligibleFields = [item.field for item in report.fields if item.status == "ready"]
    report.summary = "Смысл полей проверен; бизнес подтверждает достоверность сведений."
    return report


def private_task(client, task_id):
    return checked(client.get(f"/api/tasks/{task_id}", headers=BUSINESS, params={"view": "business"}))


def test_semantic_review_controls_confirmed_and_published_score_without_rewriting_facts(client, monkeypatch):
    import app.main as main

    evaluator = Mock(side_effect=semantic_report)
    monkeypatch.setattr(main, "semantic_configured", lambda: True)
    monkeypatch.setattr(main, "evaluate_semantic", evaluator)
    task = create_task(client)
    assert task["rating"]["score"] == 0
    assert task["previewRating"]["score"] == 100
    reviewed = checked(client.post("/api/rating/review", headers=BUSINESS, json={"fields": FULL_FIELDS}))
    assert reviewed["score"] == 85
    assert reviewed["quality"]["mode"] == "openai"
    assert reviewed["quality"]["model"] == "test-semantic-model"
    # Reviewing a candidate does not confirm or publish the stored task.
    assert private_task(client, task["id"]) == task
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404
    confirmed = checked(client.post(f"/api/tasks/{task['id']}/confirm", headers=BUSINESS))
    assert confirmed["confirmed"] is True
    assert confirmed["rating"] == confirmed["previewRating"] == reviewed
    assert confirmed["fields"] == FULL_FIELDS
    assert confirmed["revision"] == task["revision"]
    published = checked(client.post(f"/api/tasks/{task['id']}/publish", headers=BUSINESS))
    assert published["rating"] == reviewed
    assert published["fields"] == FULL_FIELDS
    assert checked(client.get(f"/api/tasks/{task['id']}")) == published
    assert evaluator.call_count == 2  # Explicit review plus human confirmation; never on publish/read.


def test_provider_error_keeps_edited_draft_unconfirmed_and_old_public_snapshot_intact(client, monkeypatch):
    import app.main as main
    from app.semantic_quality import SemanticReviewError

    original = publish_task(client)
    changed_fields = deepcopy(FULL_FIELDS)
    changed_fields["context"] = "Менеджеры переносят заказы вручную между тремя отдельными таблицами."
    edited = checked(client.put(f"/api/tasks/{original['id']}", headers=BUSINESS, json=task_input(changed_fields)))
    monkeypatch.setattr(main, "semantic_configured", lambda: True)
    monkeypatch.setattr(main, "evaluate_semantic", Mock(side_effect=SemanticReviewError("AI-проверка временно недоступна. Повторите попытку.")))
    for route, payload in (("/api/rating/review", {"fields": changed_fields}), (f"/api/tasks/{original['id']}/confirm", None)):
        response = client.post(route, headers=BUSINESS, json=payload)
        assert response.status_code == 503, response.text
        assert "detail" in response.json()
    assert private_task(client, original["id"]) == edited
    assert edited["confirmed"] is False and edited["rating"]["score"] == 0
    assert client.post(f"/api/tasks/{original['id']}/publish", headers=BUSINESS).status_code == 409
    assert checked(client.get(f"/api/tasks/{original['id']}")) == original


def test_previously_rules_confirmed_task_requires_semantic_reconfirmation_before_publish(client, monkeypatch):
    import app.main as main

    task = create_task(client)
    rules_confirmed = checked(client.post(f"/api/tasks/{task['id']}/confirm", headers=BUSINESS))
    assert rules_confirmed["rating"]["quality"]["mode"] == "rules"
    monkeypatch.setattr(main, "semantic_configured", lambda: True)
    evaluator = Mock(side_effect=semantic_report)
    monkeypatch.setattr(main, "evaluate_semantic", evaluator)
    assert client.post(f"/api/tasks/{task['id']}/publish", headers=BUSINESS).status_code == 409
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404
    assert private_task(client, task["id"]) == rules_confirmed
    evaluator.assert_not_called()
    confirmed = checked(client.post(f"/api/tasks/{task['id']}/confirm", headers=BUSINESS))
    assert confirmed["rating"]["quality"]["mode"] == "openai"
    assert confirmed["rating"]["score"] == 85
    assert checked(client.post(f"/api/tasks/{task['id']}/publish", headers=BUSINESS))["rating"] == confirmed["rating"]


def test_edit_during_ai_review_conflicts_without_confirming_stale_fields(client, monkeypatch):
    import app.main as main

    original = publish_task(client)
    latest_fields = deepcopy(FULL_FIELDS)
    latest_fields["title"] = "Новая редакция во время проверки AI"
    latest_fields["context"] = "Операторы записывают новые заказы вручную в журнал и чат мастерской."

    def change_during_review(fields):
        assert fields.model_dump() == original["fields"]
        # A separate database connection can edit while the provider is active;
        # confirmation must not hold a write lock during the network call.
        client.app.state.store.update_task(original["id"], TaskInput(**task_input(latest_fields)))
        return semantic_report(fields)

    monkeypatch.setattr(main, "semantic_configured", lambda: True)
    evaluator = Mock(side_effect=change_during_review)
    monkeypatch.setattr(main, "evaluate_semantic", evaluator)
    response = client.post(f"/api/tasks/{original['id']}/confirm", headers=BUSINESS)
    assert response.status_code == 409, response.text
    assert "изменилась" in response.json()["detail"]
    latest = private_task(client, original["id"])
    assert latest["fields"] == latest_fields
    assert latest["revision"] == original["revision"] + 1
    assert latest["confirmed"] is False and latest["rating"]["score"] == 0
    assert checked(client.get(f"/api/tasks/{original['id']}")) == original
    assert client.post(f"/api/tasks/{original['id']}/publish", headers=BUSINESS).status_code == 409
    evaluator.assert_called_once()


def test_readonly_routes_and_local_preview_never_invoke_provider(client, monkeypatch):
    import app.main as main

    original = publish_task(client)
    evaluator = Mock(side_effect=AssertionError("A read-only operation attempted an AI request"))
    monkeypatch.setattr(main, "semantic_configured", lambda: True)
    monkeypatch.setattr(main, "evaluate_semantic", evaluator)
    for route, headers in (("/api/tasks", {}), (f"/api/tasks/{original['id']}", {}), ("/api/tasks?view=business", BUSINESS), (f"/api/tasks/{original['id']}?view=business", BUSINESS), ("/api/ai/status", BUSINESS)):
        checked(client.get(route, headers=headers))
    preview = checked(client.post("/api/rating/preview", json={"fields": FULL_FIELDS}))
    assert preview["quality"]["mode"] == "rules"
    assert preview["score"] == 100
    evaluator.assert_not_called()


def test_review_role_guards_and_status_exposes_model_but_never_api_key(client, monkeypatch):
    import app.main as main

    evaluator = Mock(side_effect=AssertionError("Status/unauthorized review invoked AI"))
    monkeypatch.setattr(main, "evaluate_semantic", evaluator)
    for headers in ({}, STUDENT):
        assert client.post("/api/rating/review", headers=headers, json={"fields": FULL_FIELDS}).status_code == 403
        assert client.get("/api/ai/status", headers=headers).status_code == 403
    assert checked(client.get("/api/ai/status", headers=BUSINESS))["configured"] is False
    secret_marker = "test-only-key-not-a-real-provider-credential"
    monkeypatch.setenv("OPENAI_API_KEY", secret_marker)
    monkeypatch.setenv("OPENAI_RATING_MODEL", "  test-quality-model  ")
    monkeypatch.setenv("OPENAI_MODEL", "test-other-model")
    response = client.get("/api/ai/status", headers=BUSINESS)
    assert checked(response) == {"configured": True, "model": "test-quality-model"}
    assert secret_marker not in response.text
    evaluator.assert_not_called()


@pytest.mark.parametrize("field", SCORED_FIELDS)
@pytest.mark.parametrize("value", ["а", "аб", "абв"])
def test_one_to_three_letters_never_earn_points_in_preview_or_offline_confirmation(client, monkeypatch, field, value):
    import app.main as main

    monkeypatch.setattr(main, "semantic_configured", lambda: False)
    evaluator = Mock(side_effect=AssertionError("Offline confirmation invoked AI"))
    monkeypatch.setattr(main, "evaluate_semantic", evaluator)
    fields = empty_fields(title="Проверка коротких ответов", **{field: value})
    preview = checked(client.post("/api/rating/preview", json={"fields": fields}))
    assert preview["score"] == 0
    quality = next(item for item in preview["quality"]["fields"] if item["field"] == field)
    assert quality["status"] != "ready" and quality["suggestion"]
    task = create_task(client, fields=fields)
    confirmed = checked(client.post(f"/api/tasks/{task['id']}/confirm", headers=BUSINESS))
    assert confirmed["confirmed"] is True
    assert confirmed["rating"]["score"] == 0
    assert confirmed["fields"] == fields
    published = checked(client.post(f"/api/tasks/{task['id']}/publish", headers=BUSINESS))
    assert published["rating"]["score"] == 0
    assert published["rating"]["level"] == "draft"
    assert any(item["id"] == task["id"] for item in checked(client.get("/api/tasks")))
    evaluator.assert_not_called()
