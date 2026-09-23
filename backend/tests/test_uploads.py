"""Atomic PDF submission and scoped downloads; never touches the working database."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.uploads import MAX_PDF_BYTES, MAX_REQUEST_BYTES
from test_part1_api import BUSINESS, STUDENT, checked, create_task, empty_fields, publish_task

PDF = (Path(__file__).resolve().parents[2] / "fixtures" / "proposal_demo.pdf").read_bytes()


def payload(client):
    return {
        "teamId": checked(client.get("/api/teams"))[0]["id"],
        "idea": "Список заказов с поиском и импортом синтетического CSV.",
        "plan": ["Согласовать критерии", "Собрать прототип", "Проверить импорт"],
        "durationDays": 7,
        "prototypeUrl": "https://example.com/demo",
    }


def upload(client, task, proposal=None, *, name="План решения.pdf", content=PDF, mime="application/pdf", headers=STUDENT):
    return client.post(f"/api/tasks/{task['id']}/proposals/upload", headers=headers,
                       data={"proposal": json.dumps(proposal or payload(client), ensure_ascii=False)},
                       files={"file": (name, content, mime)})


def download_path(proposal):
    return f"/api/proposals/{proposal['id']}/attachments/{proposal['attachments'][0]['id']}"


def test_pdf_and_low_score_proposal_are_atomic_persisted_and_downloadable(client, app_factory):
    task = publish_task(client, empty_fields(title="Задача без подробностей"), skills=["UnmatchedSkill"])
    assert task["rating"]["score"] == 0
    result = checked(upload(client, task), 201)
    assert result["status"] == "submitted"
    assert len(result["attachments"]) == 1
    attachment = result["attachments"][0]
    assert attachment["name"] == "План решения.pdf"
    assert attachment["size"] == len(PDF)
    assert attachment["mediaType"] == "application/pdf"
    path = download_path(result)
    response = client.get(path, headers=BUSINESS)
    assert response.status_code == 200 and response.content == PDF
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    with TestClient(app_factory()) as restarted:
        restored = checked(restarted.get("/api/proposals", params={"teamId": result["teamId"]}, headers=STUDENT))
        assert next(item for item in restored if item["id"] == result["id"])["attachments"] == result["attachments"]
        assert restarted.get(path, headers=STUDENT, params={"teamId": result["teamId"]}).content == PDF


def test_attachment_download_checks_role_team_proposal_and_business_owner(client, app_db_path):
    task = publish_task(client)
    result = checked(upload(client, task), 201)
    path = download_path(result)
    assert client.get(path).status_code == 403
    assert client.get(path, headers=STUDENT).status_code == 403
    other_team = checked(client.get("/api/teams"))[1]["id"]
    assert client.get(path, headers=STUDENT, params={"teamId": other_team}).status_code == 403
    other = checked(upload(client, task), 201)
    wrong_pair = f"/api/proposals/{other['id']}/attachments/{result['attachments'][0]['id']}"
    assert client.get(wrong_pair, headers=BUSINESS).status_code == 404
    assert client.get(f"/api/proposals/{uuid4()}/attachments/{uuid4()}", headers=BUSINESS).status_code == 404
    import sqlite3
    with sqlite3.connect(app_db_path) as connection:
        connection.execute("UPDATE tasks SET owner_id = ? WHERE id = ?", ("another-business", task["id"]))
    assert client.get(path, headers=BUSINESS).status_code == 404


@pytest.mark.parametrize("changes", [
    {"name": "plan.exe"}, {"name": "plan.html"}, {"name": "a" * 170 + ".pdf"},
    {"content": b""}, {"content": b"<html>fake PDF</html>"},
    {"content": b"%PDF-1.7\ntruncated"}, {"mime": "text/html"},
])
def test_rejected_pdf_creates_neither_file_nor_proposal(client, app_db_path, changes):
    import sqlite3
    task = publish_task(client)
    before = checked(client.get("/api/proposals", params={"taskId": task["id"]}, headers=BUSINESS))
    assert upload(client, task, **changes).status_code == 422
    assert checked(client.get("/api/proposals", params={"taskId": task["id"]}, headers=BUSINESS)) == before
    with sqlite3.connect(app_db_path) as connection:
        assert connection.execute("SELECT count(*) FROM proposal_attachments").fetchone()[0] == 0


@pytest.mark.parametrize("size", [MAX_PDF_BYTES + 1, MAX_REQUEST_BYTES + 1])
def test_upload_limits_are_enforced_before_saving(client, size):
    task = publish_task(client)
    oversized = b"%PDF-1.4\n" + b" " * size + b"\n%%EOF"
    assert upload(client, task, content=oversized).status_code == 413
    assert checked(client.get("/api/proposals", params={"taskId": task["id"]}, headers=BUSINESS)) == []


def test_upload_rejects_bad_form_invalid_proposal_private_tasks_and_wrong_roles(client):
    private = create_task(client)
    public = publish_task(client)
    assert upload(client, public, headers={}).status_code == 403
    assert upload(client, public, headers=BUSINESS).status_code == 403
    assert upload(client, private).status_code == 404
    for change in ({"durationDays": 0}, {"plan": []}, {"idea": ""}, {"teamId": str(uuid4())}):
        response = upload(client, public, {**payload(client), **change})
        assert response.status_code == (404 if "teamId" in change else 422)
    route = f"/api/tasks/{public['id']}/proposals/upload"
    assert client.post(route, headers=STUDENT, json=payload(client)).status_code == 415
    assert client.post(route, headers=STUDENT, data={"proposal": "{invalid"}, files={"file": ("p.pdf", PDF, "application/pdf")}).status_code == 422
    assert client.post(route, headers=STUDENT, data={"proposal": json.dumps(payload(client))}, files=[("file", ("one.pdf", PDF)), ("file", ("two.pdf", PDF))]).status_code == 400
    assert checked(client.get("/api/proposals", params={"taskId": public['id']}, headers=BUSINESS)) == []


def test_pdf_name_is_data_not_a_path_or_header(client):
    task = publish_task(client)
    result = checked(upload(client, task, name="../../план.pdf"), 201)
    assert result["attachments"][0]["name"] == "план.pdf"
    assert client.get(download_path(result), headers=BUSINESS).content == PDF
