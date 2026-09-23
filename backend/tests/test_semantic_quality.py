"""Semantic provider boundaries are mocked: no network or paid requests."""

from copy import deepcopy
import json

import httpx
import pytest

from app import semantic_quality as semantic
from app.domain import calculate_rating
from app.models import TaskFields
from test_part1_api import FULL_FIELDS, empty_fields


@pytest.fixture(autouse=True)
def isolated_semantic_cache(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-semantic-key-never-real")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_RATING_MODEL", raising=False)
    with semantic._cache_lock:
        semantic._cache.clear()
    yield
    with semantic._cache_lock:
        semantic._cache.clear()


def review(values=None):
    values = values or FULL_FIELDS
    return {"fields": [
        {"field": name, "status": "ready" if values[name] else "needs_work",
         "reason": "Есть конкретное описание." if values[name] else "Не хватает описания.",
         "suggestion": "" if values[name] else "Уточните сведения для этого раздела.",
         "evidence": values[name]}
        for name in semantic.SEMANTIC_FIELDS
    ]}


def envelope(result):
    return {"status": "completed", "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "role": "assistant", "status": "completed", "content": [
            {"type": "output_text", "text": json.dumps(result, ensure_ascii=False)},
        ]},
    ]}


def mock_provider(monkeypatch, result=None, *, body=None, timeout=False, status=200):
    calls = []

    def handler(request):
        calls.append(request)
        if timeout:
            raise httpx.ReadTimeout("fake-semantic-key-never-real SECRET_PROVIDER_TRACE", request=request)
        return httpx.Response(status, json=body if body is not None else envelope(result or review()))

    monkeypatch.setattr(semantic, "_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    return calls


def test_semantic_review_uses_strict_schema_excludes_contact_and_preserves_fields(monkeypatch):
    calls = mock_provider(monkeypatch)
    fields = TaskFields(**FULL_FIELDS)
    before = fields.model_dump()
    result = semantic.evaluate_semantic(fields)
    assert result.mode == "openai" and result.version == "semantic-v1"
    assert result.model == "gpt-4.1-mini"
    assert len(result.eligibleFields) == 9
    assert calculate_rating(fields, quality=result).score == 100
    assert calculate_rating(fields, quality=result, confirmed=False).score == 0
    assert fields.model_dump() == before
    request = json.loads(calls[0].content)
    assert calls[0].url == semantic.OPENAI_URL
    assert request["store"] is False
    assert request["text"]["format"]["strict"] is True
    assert request["text"]["format"]["schema"]["additionalProperties"] is False
    values = json.loads(request["input"][1]["content"])["fields"]
    assert set(values) == set(semantic.SEMANTIC_FIELDS)
    assert "contact" not in values and FULL_FIELDS["contact"] not in calls[0].content.decode()
    assert "fake-semantic-key" not in calls[0].content.decode()
    assert calls[0].headers["Authorization"] == "Bearer fake-semantic-key-never-real"
    assert "UNTRUSTED DATA" in request["input"][0]["content"]


def test_semantic_rejection_removes_only_server_owned_weight(monkeypatch):
    result = review()
    item = next(item for item in result["fields"] if item["field"] == "successCriteria")
    item.update(status="needs_work", reason="Критерий противоречит описанному результату.", suggestion="Уточните проверку результата.")
    mock_provider(monkeypatch, result)
    fields = TaskFields(**FULL_FIELDS)
    report = semantic.evaluate_semantic(fields)
    assert calculate_rating(fields, quality=report).score == 85
    # eligibleFields is a display list; it cannot override field assessments.
    report.eligibleFields.append("successCriteria")
    assert calculate_rating(fields, quality=report).score == 85


@pytest.mark.parametrize("value", ["а", "аб", "абв", "ыва", "qwe", "ааааа", "asdf qwerty", "Сделать хорошо", "для всех"])
def test_local_hard_floor_cannot_be_overruled_by_ai(monkeypatch, value):
    values = empty_fields(**{field: value for field in semantic.SEMANTIC_FIELDS})
    mock_provider(monkeypatch, review(values))
    fields = TaskFields(**values)
    result = semantic.evaluate_semantic(fields)
    assert all(item.status != "ready" for item in result.fields)
    assert calculate_rating(fields, quality=result).score == 0


def test_missing_fields_stay_missing_and_short_meaningful_constraint_can_earn(monkeypatch):
    values = empty_fields(constraints="Только Python")
    mock_provider(monkeypatch, review(values))
    fields = TaskFields(**values)
    report = semantic.evaluate_semantic(fields)
    assert next(item for item in report.fields if item.field == "context").status == "missing"
    assert calculate_rating(fields, quality=report).score == 10


def test_contact_is_local_even_when_model_marks_every_reviewed_field_ready(monkeypatch):
    values = {**FULL_FIELDS, "contact": "Позвоните кому-нибудь"}
    calls = mock_provider(monkeypatch, review(values))
    fields = TaskFields(**values)
    result = semantic.evaluate_semantic(fields)
    assert calculate_rating(fields, quality=result).score == 95
    assert values["contact"] not in calls[0].content.decode()


@pytest.mark.parametrize("mutate", [
    lambda result: result["fields"].pop(),
    lambda result: result["fields"].append(deepcopy(result["fields"][0])),
    lambda result: result["fields"].__setitem__(1, deepcopy(result["fields"][0])),
    lambda result: result["fields"][0].update(field="contact"),
    lambda result: result["fields"][0].update(evidence="Выдуманный факт, которого нет у бизнеса"),
    lambda result: result["fields"][0].update(evidence=FULL_FIELDS["need"]),
    lambda result: result["fields"][0].update(evidence=""),
    lambda result: result["fields"][0].update(score=100),
    lambda result: result["fields"][0].update(status="needs_work", suggestion=""),
    lambda result: result.update(score=100),
])
def test_invalid_fields_or_ungrounded_evidence_fail_closed(monkeypatch, mutate):
    result = review()
    mutate(result)
    calls = mock_provider(monkeypatch, result)
    for _ in range(2):
        with pytest.raises(semantic.SemanticReviewError, match="формата или источников"):
            semantic.evaluate_semantic(TaskFields(**FULL_FIELDS))
    assert len(calls) == 2  # Failures must not be cached.


@pytest.mark.parametrize("body", [
    {"status": "incomplete", "output": []},
    {"status": "completed", "output": "not a list"},
    {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "refusal", "refusal": "SECRET_PROVIDER_TRACE"}]}]},
    {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": "{malformed SECRET_PROVIDER_TRACE"}]}]},
])
def test_refusal_malformed_or_incomplete_response_is_safe_error(monkeypatch, body):
    mock_provider(monkeypatch, body=body)
    with pytest.raises(semantic.SemanticReviewError) as error:
        semantic.evaluate_semantic(TaskFields(**FULL_FIELDS))
    assert "SECRET_PROVIDER_TRACE" not in str(error.value)
    assert "fake-semantic-key" not in str(error.value)


@pytest.mark.parametrize("timeout,status", [(True, 200), (False, 401), (False, 429), (False, 503)])
def test_provider_error_does_not_leak_secrets_or_fallback_silently(monkeypatch, timeout, status):
    mock_provider(monkeypatch, body={"error": "fake-semantic-key-never-real SECRET_PROVIDER_TRACE"}, timeout=timeout, status=status)
    with pytest.raises(semantic.SemanticReviewError) as error:
        semantic.evaluate_semantic(TaskFields(**FULL_FIELDS))
    assert "SECRET_PROVIDER_TRACE" not in str(error.value)
    assert "fake-semantic-key" not in str(error.value)
    assert "не завершилась вовремя" in str(error.value) if timeout else "недоступен" in str(error.value)


def test_key_is_required_and_configuration_does_not_call_network(monkeypatch):
    calls = mock_provider(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", " ")
    assert not semantic.semantic_configured()
    with pytest.raises(semantic.SemanticReviewError, match="OPENAI_API_KEY"):
        semantic.evaluate_semantic(TaskFields(**FULL_FIELDS))
    assert calls == []


def test_success_cache_is_isolated_from_mutation_expires_and_is_bounded(monkeypatch):
    calls = mock_provider(monkeypatch)
    clock = [100.0]
    monkeypatch.setattr(semantic.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(semantic, "CACHE_MAX_ENTRIES", 2)
    fields = TaskFields(**FULL_FIELDS)
    original = semantic.evaluate_semantic(fields)
    original.fields[0].status = "needs_work"
    assert semantic.evaluate_semantic(fields).fields[0].status == "ready"
    assert len(calls) == 1
    clock[0] += 601
    semantic.evaluate_semantic(fields)
    assert len(calls) == 2
    # Changes to any source field invalidate the cache, including locally
    # evaluated contact and the task's non-scored title.
    semantic.evaluate_semantic(fields.model_copy(update={"contact": "another@example.invalid"}))
    semantic.evaluate_semantic(fields.model_copy(update={"title": "Другая версия задачи"}))
    assert len(calls) == 4 and len(semantic._cache) == 2
    semantic.evaluate_semantic(fields)
    assert len(calls) == 5


def test_cache_invalidation_for_input_model_prompt_and_credentials(monkeypatch):
    calls = mock_provider(monkeypatch)
    fields = TaskFields(**FULL_FIELDS)
    semantic.evaluate_semantic(fields)
    monkeypatch.setenv("OPENAI_MODEL", "generic-model")
    semantic.evaluate_semantic(fields)
    monkeypatch.setenv("OPENAI_RATING_MODEL", "rating-model")
    semantic.evaluate_semantic(fields)
    monkeypatch.setattr(semantic, "PROMPT_VERSION", "semantic-test-version")
    semantic.evaluate_semantic(fields)
    monkeypatch.setenv("OPENAI_API_KEY", "different-test-key")
    semantic.evaluate_semantic(fields)
    # Longer source still contains the response's literal original quote.
    semantic.evaluate_semantic(fields.model_copy(update={"context": fields.context + " Это учебный процесс."}))
    assert len(calls) == 6
    assert [json.loads(call.content)["model"] for call in calls[:3]] == ["gpt-4.1-mini", "generic-model", "rating-model"]
