"""Atomic demo-team rewards for human-confirmed project completion.

Points do not affect task readiness, catalog visibility or team selection.
The ledger is the source of truth; balances and ownership are derived from it.
"""

import sqlite3
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request

from .proposal_models import Proposal, ProposalCompletion, ProposalCompletionInput
from .proposals import ProposalRepository, _business, _student
from .reward_models import (
    RewardEquipment, RewardEquipInput, RewardItem, RewardPurchaseInput,
    RewardTransaction, TeamRewards,
)
from .store import DEMO_OWNER, Store, StoreError, utc_now

router = APIRouter(prefix="/api", tags=["Team rewards"])
PROJECT_REWARD = 100
REWARD_ITEMS = (
    RewardItem(id="background-dawn", name="Утреннее небо", description="Светлый фон комнаты команды.", cost=60, slot="background", style="dawn"),
    RewardItem(id="background-night", name="Ночной город", description="Тёмный фон для комнаты команды.", cost=80, slot="background", style="night"),
    RewardItem(id="poster-orbit", name="Орбита", description="Постер с космическими орбитами.", cost=60, slot="poster", style="orbit"),
    RewardItem(id="poster-mountains", name="Горизонт", description="Постер с горным пейзажем.", cost=60, slot="poster", style="mountains"),
    RewardItem(id="plant", name="Монстера", description="Зелёное растение для комнаты команды.", cost=40, slot="plant", style="monstera"),
    RewardItem(id="lamp", name="Тёплый свет", description="Лампа для уютного рабочего места.", cost=60, slot="lamp", style="warm"),
)


def initialize_rewards(connection: sqlite3.Connection) -> None:
    """Add tables without awarding points for historical choices or seed proposals."""
    connection.execute("""
        CREATE TABLE IF NOT EXISTS reward_transactions (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL REFERENCES teams(id),
            kind TEXT NOT NULL CHECK(kind IN ('project_reward', 'purchase')),
            amount INTEGER NOT NULL,
            label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            proposal_id TEXT REFERENCES proposals(id),
            task_id TEXT REFERENCES tasks(id),
            item_id TEXT,
            CHECK (
                (kind = 'project_reward' AND amount = 100 AND proposal_id IS NOT NULL AND task_id IS NOT NULL AND item_id IS NULL)
                OR (kind = 'purchase' AND amount < 0 AND proposal_id IS NULL AND task_id IS NULL AND item_id IS NOT NULL)
            )
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS rewards_by_team ON reward_transactions(team_id)")
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS reward_once_per_project ON reward_transactions(team_id, task_id) WHERE kind = 'project_reward'")
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS reward_once_per_item ON reward_transactions(team_id, item_id) WHERE kind = 'purchase'")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS reward_equipment (
            team_id TEXT NOT NULL REFERENCES teams(id),
            slot TEXT NOT NULL CHECK(slot IN ('background', 'poster', 'plant', 'lamp')),
            item_id TEXT NOT NULL,
            PRIMARY KEY(team_id, slot)
        )
    """)


class RewardRepository:
    def __init__(self, store: Store):
        self.store = store

    @staticmethod
    def _item(item_id: str) -> RewardItem:
        item = next((item for item in REWARD_ITEMS if item.id == item_id), None)
        if item is None:
            raise StoreError(404, "Предмет не найден в магазине")
        return item

    @staticmethod
    def _state(connection: sqlite3.Connection, team_id: str) -> TeamRewards:
        ProposalRepository._team(connection, team_id)
        rows = connection.execute("""
            SELECT * FROM reward_transactions WHERE team_id = ? ORDER BY created_at DESC, rowid DESC
        """, (team_id,)).fetchall()
        history = [RewardTransaction(
            id=row["id"], kind=row["kind"], amount=row["amount"], label=row["label"],
            createdAt=row["created_at"], proposalId=row["proposal_id"], itemId=row["item_id"],
        ) for row in rows]
        rewards = [row for row in rows if row["kind"] == "project_reward"]
        equipment = connection.execute("SELECT slot, item_id FROM reward_equipment WHERE team_id = ?", (team_id,)).fetchall()
        return TeamRewards(
            teamId=team_id,
            balance=sum(row["amount"] for row in rows),
            totalEarned=sum(row["amount"] for row in rewards),
            completedProjects=len(rewards), items=list(REWARD_ITEMS),
            ownedItemIds=sorted(row["item_id"] for row in rows if row["kind"] == "purchase"),
            equipped=RewardEquipment(**{row["slot"]: row["item_id"] for row in equipment}),
            history=history,
        )

    def get(self, team_id: str) -> TeamRewards:
        with self.store.connection() as connection:
            # Multiple reads must see the same ledger/equipment snapshot.
            connection.execute("BEGIN")
            return self._state(connection, team_id)

    def complete(self, proposal_id: str, completion_input: ProposalCompletionInput) -> Proposal:
        with self.store.connection(write=True) as connection:
            row = connection.execute("""
                SELECT proposals.proposal_json FROM proposals
                JOIN tasks ON tasks.id = proposals.task_id
                WHERE proposals.id = ? AND tasks.owner_id = ?
            """, (proposal_id, DEMO_OWNER)).fetchone()
            if row is None:
                raise StoreError(404, "Отклик не найден")
            proposal = ProposalRepository._proposal(connection, row)
            if proposal.completion is not None:
                return proposal
            if proposal.status != "accepted":
                raise StoreError(409, "Сначала бизнес должен выбрать команду для этой задачи")
            previous = connection.execute("""
                SELECT id FROM reward_transactions
                WHERE team_id = ? AND task_id = ? AND kind = 'project_reward'
            """, (proposal.teamId, proposal.taskId)).fetchone()
            if previous is not None:
                raise StoreError(409, "Эта команда уже получила баллы за завершение этой задачи")
            timestamp = utc_now()
            proposal.completion = ProposalCompletion(
                confirmedAt=timestamp, summary=completion_input.summary, pointsAwarded=PROJECT_REWARD,
            )
            proposal.updatedAt = timestamp
            # BEGIN IMMEDIATE serializes competing completions/purchases. The
            # unique index additionally protects the team/task business rule.
            connection.execute("""
                INSERT INTO reward_transactions(id, team_id, kind, amount, label, created_at, proposal_id, task_id)
                VALUES (?, ?, 'project_reward', ?, ?, ?, ?, ?)
            """, (str(uuid4()), proposal.teamId, PROJECT_REWARD, f"Проект завершён: {proposal.taskTitle}", timestamp, proposal.id, proposal.taskId))
            connection.execute("UPDATE proposals SET proposal_json = ? WHERE id = ?", (proposal.model_dump_json(), proposal.id))
            return proposal

    def purchase(self, team_id: str, item_id: str) -> TeamRewards:
        item = self._item(item_id)
        with self.store.connection(write=True) as connection:
            current = self._state(connection, team_id)
            if item.id in current.ownedItemIds:
                return current
            if current.balance < item.cost:
                raise StoreError(409, "Недостаточно баллов. Они начисляются после подтверждённого завершения проекта")
            connection.execute("""
                INSERT INTO reward_transactions(id, team_id, kind, amount, label, created_at, item_id)
                VALUES (?, ?, 'purchase', ?, ?, ?, ?)
            """, (str(uuid4()), team_id, -item.cost, f"Покупка: {item.name}", utc_now(), item.id))
            return self._state(connection, team_id)

    def equip(self, team_id: str, equipment_input: RewardEquipInput) -> TeamRewards:
        with self.store.connection(write=True) as connection:
            current = self._state(connection, team_id)
            if equipment_input.itemId is None:
                connection.execute("DELETE FROM reward_equipment WHERE team_id = ? AND slot = ?", (team_id, equipment_input.slot))
            else:
                item = self._item(equipment_input.itemId)
                if item.slot != equipment_input.slot:
                    raise StoreError(422, "Предмет не подходит для этого места в комнате")
                if item.id not in current.ownedItemIds:
                    raise StoreError(409, "Сначала приобретите этот предмет за баллы")
                connection.execute("""
                    INSERT INTO reward_equipment(team_id, slot, item_id) VALUES (?, ?, ?)
                    ON CONFLICT(team_id, slot) DO UPDATE SET item_id = excluded.item_id
                """, (team_id, item.slot, item.id))
            return self._state(connection, team_id)


def _repository(request: Request) -> RewardRepository:
    return RewardRepository(request.app.state.store)


@router.post("/proposals/{proposal_id}/complete", response_model=Proposal, response_model_exclude_none=True, dependencies=[Depends(_business)])
def complete_proposal(proposal_id: UUID, completion_input: ProposalCompletionInput, request: Request):
    return _repository(request).complete(str(proposal_id), completion_input)


@router.get("/teams/{team_id}/rewards", response_model=TeamRewards, dependencies=[Depends(_student)])
def team_rewards(team_id: UUID, request: Request):
    return _repository(request).get(str(team_id))


@router.post("/teams/{team_id}/rewards/purchase", response_model=TeamRewards, dependencies=[Depends(_student)])
def purchase_reward(team_id: UUID, purchase_input: RewardPurchaseInput, request: Request):
    return _repository(request).purchase(str(team_id), purchase_input.itemId)


@router.put("/teams/{team_id}/rewards/equip", response_model=TeamRewards, dependencies=[Depends(_student)])
def equip_reward(team_id: UUID, equipment_input: RewardEquipInput, request: Request):
    return _repository(request).equip(str(team_id), equipment_input)
