"""Earn-once completion, an atomic points ledger and server-priced decorations."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.proposal_models import ProposalCompletionInput
from app.rewards import RewardRepository
from app.store import Store, StoreError

BUSINESS = {"X-Demo-Role": "business"}
STUDENT = {"X-Demo-Role": "student"}
SUMMARY = "Проверили прототип на примерах бизнеса и приняли результат проекта."


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def team_and_task(client):
    return checked(client.get("/api/teams"))[0], checked(client.get("/api/tasks"))[-1]


def propose(client, team_id, task_id, *, accepted=True):
    proposal = checked(client.post(f"/api/tasks/{task_id}/proposals", headers=STUDENT, json={
        "teamId": team_id, "idea": "Решить задачу на данных бизнеса.",
        "plan": ["Собрать прототип и проверить на примерах."],
        "durationDays": 7, "prototypeUrl": "https://example.com/prototype",
    }), 201)
    if accepted:
        proposal = checked(client.put(f"/api/proposals/{proposal['id']}/decision", headers=BUSINESS, json={"status": "accepted"}))
    return proposal


def state(client, team_id):
    return checked(client.get(f"/api/teams/{team_id}/rewards", headers=STUDENT))


def complete(client, proposal_id, summary=SUMMARY):
    return checked(client.post(f"/api/proposals/{proposal_id}/complete", headers=BUSINESS, json={"summary": summary}))


def purchase(client, team_id, item_id):
    return client.post(f"/api/teams/{team_id}/rewards/purchase", headers=STUDENT, json={"itemId": item_id})


def equip(client, team_id, slot, item_id):
    return client.put(f"/api/teams/{team_id}/rewards/equip", headers=STUDENT, json={"slot": slot, "itemId": item_id})


def test_initial_balance_zero_and_only_manual_success_awards_points(client):
    team, task = team_and_task(client)
    assert task["rating"]["score"] < 40
    before = state(client, team["id"])
    assert (before["balance"], before["totalEarned"], before["completedProjects"]) == (0, 0, 0)
    assert before["history"] == before["ownedItemIds"] == []
    assert before["equipped"] == {"background": None, "poster": None, "plant": None, "lamp": None}
    assert {item["id"]: item["cost"] for item in before["items"]} == {
        "background-dawn": 60, "background-night": 80, "poster-orbit": 60,
        "poster-mountains": 60, "plant": 40, "lamp": 60,
    }
    proposal = propose(client, team["id"], task["id"], accepted=False)
    assert state(client, team["id"]) == before
    checked(client.put(f"/api/proposals/{proposal['id']}/decision", headers=BUSINESS, json={"status": "accepted"}))
    assert state(client, team["id"]) == before
    result = complete(client, proposal["id"], "  " + SUMMARY + "  ")
    assert result["status"] == "accepted"
    assert result["completion"]["summary"] == SUMMARY
    assert result["completion"]["pointsAwarded"] == 100
    assert result["completion"]["confirmedAt"].endswith("Z")
    earned = state(client, team["id"])
    assert (earned["balance"], earned["totalEarned"], earned["completedProjects"]) == (100, 100, 1)
    assert len(earned["history"]) == 1
    assert earned["history"][0]["proposalId"] == proposal["id"]
    assert earned["history"][0]["kind"] == "project_reward"
    assert earned["history"][0]["amount"] == 100
    assert earned["history"][0]["itemId"] is None
    # Team points never alter the business task's readiness or visibility.
    assert checked(client.get(f"/api/tasks/{task['id']}")) == task
    other_team = checked(client.get("/api/teams"))[1]
    assert state(client, other_team["id"])["balance"] == 0


def test_completion_is_idempotent_blocks_decision_and_duplicate_pair_reward(client):
    team, task = team_and_task(client)
    first = propose(client, team["id"], task["id"])
    duplicate = propose(client, team["id"], task["id"])
    completed = complete(client, first["id"])
    before = state(client, team["id"])
    assert complete(client, first["id"], "Повторное подтверждение не заменяет исходный результат.") == completed
    assert client.post(f"/api/proposals/{duplicate['id']}/complete", headers=BUSINESS, json={"summary": SUMMARY}).status_code == 409
    for status in ("submitted", "accepted", "rejected"):
        assert client.put(f"/api/proposals/{first['id']}/decision", headers=BUSINESS, json={"status": status}).status_code == 409
    assert state(client, team["id"]) == before
    proposals = checked(client.get("/api/proposals", headers=STUDENT, params={"teamId": team["id"]}))
    assert next(item for item in proposals if item["id"] == first["id"]) == completed
    assert next(item for item in proposals if item["id"] == duplicate["id"]).get("completion") is None


def test_other_projects_and_other_teams_can_earn_independently(client):
    teams = checked(client.get("/api/teams"))
    tasks = checked(client.get("/api/tasks"))
    for team, task in ((teams[0], tasks[0]), (teams[0], tasks[1]), (teams[1], tasks[0])):
        complete(client, propose(client, team["id"], task["id"])["id"])
    assert state(client, teams[0]["id"])["balance"] == 200
    assert state(client, teams[0]["id"])["completedProjects"] == 2
    assert state(client, teams[1]["id"])["balance"] == 100


def test_only_accepted_owned_proposals_can_complete(client, app_db_path):
    team, task = team_and_task(client)
    proposal = propose(client, team["id"], task["id"], accepted=False)
    for status in ("submitted", "rejected"):
        checked(client.put(f"/api/proposals/{proposal['id']}/decision", headers=BUSINESS, json={"status": status}))
        assert client.post(f"/api/proposals/{proposal['id']}/complete", headers=BUSINESS, json={"summary": SUMMARY}).status_code == 409
    checked(client.put(f"/api/proposals/{proposal['id']}/decision", headers=BUSINESS, json={"status": "accepted"}))
    with sqlite3.connect(app_db_path) as connection:
        connection.execute("UPDATE tasks SET owner_id = 'different-business' WHERE id = ?", (task["id"],))
    assert client.post(f"/api/proposals/{proposal['id']}/complete", headers=BUSINESS, json={"summary": SUMMARY}).status_code == 404
    assert client.post(f"/api/proposals/{uuid4()}/complete", headers=BUSINESS, json={"summary": SUMMARY}).status_code == 404
    assert state(client, team["id"])["balance"] == 0


def test_role_guards_on_every_reward_route(client):
    team, task = team_and_task(client)
    proposal = propose(client, team["id"], task["id"])
    for role in ({}, STUDENT):
        assert client.post(f"/api/proposals/{proposal['id']}/complete", headers=role, json={"summary": SUMMARY}).status_code == 403
    for role in ({}, BUSINESS):
        assert client.get(f"/api/teams/{team['id']}/rewards", headers=role).status_code == 403
        assert client.post(f"/api/teams/{team['id']}/rewards/purchase", headers=role, json={"itemId": "plant"}).status_code == 403
        assert client.put(f"/api/teams/{team['id']}/rewards/equip", headers=role, json={"slot": "plant", "itemId": None}).status_code == 403
    assert state(client, team["id"])["balance"] == 0


@pytest.mark.parametrize("payload", [{}, {"summary": " "}, {"summary": "short"}, {"summary": "a" * 2001}, {"summary": SUMMARY, "pointsAwarded": 1000}])
def test_completion_input_validates_summary_and_forbids_client_amounts(client, payload):
    team, task = team_and_task(client)
    proposal = propose(client, team["id"], task["id"])
    assert client.post(f"/api/proposals/{proposal['id']}/complete", headers=BUSINESS, json=payload).status_code == 422
    assert state(client, team["id"])["balance"] == 0


def test_purchase_spends_once_and_equip_reset_does_not_refund_or_spend(client):
    team, task = team_and_task(client)
    complete(client, propose(client, team["id"], task["id"])["id"])
    bought = checked(purchase(client, team["id"], "background-dawn"))
    assert bought["balance"] == 40
    assert bought["totalEarned"] == 100
    assert bought["completedProjects"] == 1
    assert bought["ownedItemIds"] == ["background-dawn"]
    assert bought["equipped"]["background"] is None
    assert bought["history"][0]["kind"] == "purchase"
    assert bought["history"][0]["amount"] == -60
    assert bought["history"][0]["proposalId"] is None
    assert checked(purchase(client, team["id"], "background-dawn")) == bought
    selected = checked(equip(client, team["id"], "background", "background-dawn"))
    assert selected["equipped"]["background"] == "background-dawn"
    assert selected["history"] == bought["history"]
    assert checked(equip(client, team["id"], "background", None)) == bought
    remaining = checked(purchase(client, team["id"], "plant"))
    assert remaining["balance"] == 0
    assert remaining["totalEarned"] == 100
    assert remaining["ownedItemIds"] == ["background-dawn", "plant"]
    assert checked(purchase(client, team["id"], "plant")) == remaining


def test_insufficient_unknown_unowned_wrong_slot_and_team_are_rejected(client):
    team, _ = team_and_task(client)
    before = state(client, team["id"])
    assert purchase(client, team["id"], "plant").status_code == 409
    assert purchase(client, team["id"], "subscription").status_code == 404
    assert equip(client, team["id"], "plant", "plant").status_code == 409
    assert equip(client, team["id"], "poster", "plant").status_code == 422
    assert equip(client, team["id"], "plant", "unknown").status_code == 404
    assert equip(client, team["id"], "unknown", None).status_code == 422
    assert state(client, team["id"]) == before
    missing = str(uuid4())
    assert client.get(f"/api/teams/{missing}/rewards", headers=STUDENT).status_code == 404
    assert purchase(client, missing, "plant").status_code == 404
    assert equip(client, missing, "plant", None).status_code == 404


@pytest.mark.parametrize("payload", [{"itemId": ""}, {"itemId": "plant", "cost": 0}, {"itemId": "plant", "balance": 10000}, {"itemId": "plant", "teamId": "other-team"}])
def test_purchase_rejects_unknown_fields_and_client_controlled_prices(client, payload):
    team, _ = team_and_task(client)
    assert client.post(f"/api/teams/{team['id']}/rewards/purchase", headers=STUDENT, json=payload).status_code == 422


def test_rewards_and_equipment_persist_without_duplicate_seed_awards(client, app_factory):
    team, task = team_and_task(client)
    proposal = complete(client, propose(client, team["id"], task["id"])["id"])
    checked(purchase(client, team["id"], "plant"))
    expected = checked(equip(client, team["id"], "plant", "plant"))
    with TestClient(app_factory()) as restarted:
        assert state(restarted, team["id"]) == expected
        assert complete(restarted, proposal["id"]) == proposal
        assert state(restarted, team["id"]) == expected


def test_additive_migration_keeps_old_accepted_proposals_without_free_points(client, app_factory, app_db_path):
    team, task = team_and_task(client)
    proposal = propose(client, team["id"], task["id"])
    with sqlite3.connect(app_db_path) as connection:
        connection.execute("DROP TABLE reward_equipment")
        connection.execute("DROP TABLE reward_transactions")
        row = connection.execute("SELECT proposal_json FROM proposals WHERE id = ?", (proposal["id"],)).fetchone()
        old_json = json.loads(row[0])
        old_json.pop("completion", None)
        connection.execute("UPDATE proposals SET proposal_json = ? WHERE id = ?", (json.dumps(old_json), proposal["id"]))
    with TestClient(app_factory()) as restarted:
        assert state(restarted, team["id"])["balance"] == 0
        listed = checked(restarted.get("/api/proposals", headers=STUDENT, params={"teamId": team["id"]}))
        assert next(item for item in listed if item["id"] == proposal["id"]) == proposal
        complete(restarted, proposal["id"])
        assert state(restarted, team["id"])["balance"] == 100


def race(*operations):
    barrier = Barrier(len(operations))

    def invoke(operation):
        barrier.wait(timeout=10)
        try:
            return operation()
        except StoreError as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        return list(pool.map(invoke, operations))


def test_concurrent_duplicate_completion_is_idempotent(client, app_db_path):
    team, task = team_and_task(client)
    proposal = propose(client, team["id"], task["id"])
    repository = RewardRepository(Store(app_db_path))
    def finish():
        return repository.complete(proposal["id"], ProposalCompletionInput(summary=SUMMARY))
    results = race(finish, finish)
    assert results[0] == results[1]
    assert state(client, team["id"])["balance"] == 100
    assert len(state(client, team["id"])["history"]) == 1


def test_concurrent_two_proposals_same_team_task_earn_once(client, app_db_path):
    team, task = team_and_task(client)
    proposals = [propose(client, team["id"], task["id"]) for _ in range(2)]
    repository = RewardRepository(Store(app_db_path))
    results = race(*(lambda proposal=proposal: repository.complete(proposal["id"], ProposalCompletionInput(summary=SUMMARY)) for proposal in proposals))
    assert sum(result == 409 for result in results) == 1
    assert state(client, team["id"])["balance"] == 100


def test_concurrent_purchases_cannot_overspend_or_charge_same_item_twice(client, app_db_path):
    team, task = team_and_task(client)
    complete(client, propose(client, team["id"], task["id"])["id"])
    repository = RewardRepository(Store(app_db_path))
    results = race(lambda: repository.purchase(team["id"], "background-dawn"), lambda: repository.purchase(team["id"], "poster-orbit"))
    assert sum(result == 409 for result in results) == 1
    assert state(client, team["id"])["balance"] == 40
    repeated = race(lambda: repository.purchase(team["id"], "plant"), lambda: repository.purchase(team["id"], "plant"))
    assert repeated[0] == repeated[1]
    final = state(client, team["id"])
    assert final["balance"] == 0
    assert len(final["history"]) == 3


def test_failed_completion_rolls_back_award_and_proposal_together(client, app_db_path):
    team, task = team_and_task(client)
    proposal = propose(client, team["id"], task["id"])
    with sqlite3.connect(app_db_path) as connection:
        connection.execute("""
            CREATE TRIGGER reject_proposal_update BEFORE UPDATE ON proposals
            BEGIN SELECT RAISE(ABORT, 'simulated disk write failure'); END
        """)
    repository = RewardRepository(Store(app_db_path))
    with pytest.raises(sqlite3.IntegrityError, match="simulated disk write failure"):
        repository.complete(proposal["id"], ProposalCompletionInput(summary=SUMMARY))
    assert state(client, team["id"])["balance"] == 0
    listed = checked(client.get("/api/proposals", headers=STUDENT, params={"teamId": team["id"]}))
    assert next(item for item in listed if item["id"] == proposal["id"]) == proposal
