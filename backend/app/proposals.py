"""Team proposals and explicit business decisions; saved quests stay independent."""

import json
import sqlite3
from typing import Annotated
from uuid import UUID, uuid4
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from .models import Task
from .proposal_models import Proposal, ProposalAttachment, ProposalDecisionInput, ProposalInput, Team, is_placeholder_url
from .uploads import read_proposal_upload
from .store import DEMO_OWNER, Store, StoreError, utc_now

router = APIRouter(prefix="/api", tags=["Teams and proposals"])
DemoRole = Annotated[str | None, Header(alias="X-Demo-Role")]


def _business(role: DemoRole = None) -> None:
    if role != "business":
        raise HTTPException(status_code=403, detail="Выберите тестовую роль «Бизнесмен»")


def _student(role: DemoRole = None) -> None:
    if role != "student":
        raise HTTPException(status_code=403, detail="Выберите тестовую роль «Студент»")


def initialize_proposals(connection: sqlite3.Connection) -> None:
    """Create additive schema and import source fixtures exactly once, in caller's transaction."""
    connection.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            source_id TEXT UNIQUE,
            team_json TEXT NOT NULL
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY,
            source_id TEXT UNIQUE,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            team_id TEXT NOT NULL REFERENCES teams(id),
            proposal_json TEXT NOT NULL
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS proposals_by_task ON proposals(task_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS proposals_by_team ON proposals(team_id)")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS proposal_attachments (
            id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL REFERENCES proposals(id),
            name TEXT NOT NULL,
            content BLOB NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS attachments_by_proposal ON proposal_attachments(proposal_id)")
    version = connection.execute("SELECT value FROM metadata WHERE key = ?", ("proposals_seed_version",)).fetchone()
    if version is not None and version["value"] == "1":
        return
    from .seed import seed_id

    team_rows = connection.execute("SELECT record_json FROM fixture_records WHERE section = ? ORDER BY source_id", ("teams",)).fetchall()
    for row in team_rows:
        source = json.loads(row["record_json"])
        team = Team(
            id=seed_id(source["id"]), sourceId=source["id"], name=source["name"],
            skills=source["skills"], technologies=source["technologies"], interests=source["interests"],
        )
        connection.execute("INSERT OR IGNORE INTO teams(id, source_id, team_json) VALUES (?, ?, ?)", (team.id, team.sourceId, team.model_dump_json()))
    proposal_rows = connection.execute("SELECT record_json FROM fixture_records WHERE section = ? ORDER BY source_id", ("proposals",)).fetchall()
    for row in proposal_rows:
        source = json.loads(row["record_json"])
        task_id, team_id = seed_id(source["task_id"]), seed_id(source["team_id"])
        team = ProposalRepository._team(connection, team_id)
        task = Task.model_validate_json(Store._published_row(connection, task_id)["published_json"])
        decision = source.get("business_decision")
        proposal = Proposal(
            id=seed_id(source["id"]), sourceId=source["id"], taskId=task_id, teamId=team_id, team=team,
            idea=source["idea"], plan=[step["description"] for step in source["plan"]],
            durationDays=source["duration_days"], prototypeUrl=source["prototype_url"],
            prototypeIsPlaceholder=source["prototype_url_is_placeholder"], assumptions=source["assumptions"],
            status=source["status"], decisionComment=decision.get("comment", "") if isinstance(decision, dict) else "",
            createdAt=source["submitted_at"], updatedAt=source["submitted_at"], taskTitle=task.fields.title,
        )
        connection.execute("INSERT OR IGNORE INTO proposals(id, source_id, task_id, team_id, proposal_json) VALUES (?, ?, ?, ?, ?)", (
            proposal.id, proposal.sourceId, task_id, team_id, proposal.model_dump_json(),
        ))
    connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)", ("proposals_seed_version", "1"))


class ProposalRepository:
    def __init__(self, store: Store):
        self.store = store

    @staticmethod
    def _team(connection: sqlite3.Connection, team_id: str) -> Team:
        row = connection.execute("SELECT team_json FROM teams WHERE id = ?", (team_id,)).fetchone()
        if row is None:
            raise StoreError(404, "Команда не найдена")
        return Team.model_validate_json(row["team_json"])

    @staticmethod
    def _proposal(connection: sqlite3.Connection, row: sqlite3.Row) -> Proposal:
        proposal = Proposal.model_validate_json(row["proposal_json"])
        proposal.team = ProposalRepository._team(connection, proposal.teamId)
        # Never expose a private draft title through the student-facing list.
        task = Task.model_validate_json(Store._published_row(connection, proposal.taskId)["published_json"])
        proposal.taskTitle = task.fields.title
        return proposal

    def teams(self) -> list[Team]:
        with self.store.connection() as connection:
            rows = connection.execute("SELECT team_json FROM teams ORDER BY rowid").fetchall()
        return [Team.model_validate_json(row["team_json"]) for row in rows]

    def submit(self, task_id: str, proposal_input: ProposalInput, attachment: tuple[str, bytes] | None = None) -> Proposal:
        with self.store.connection(write=True) as connection:
            task = Task.model_validate_json(Store._published_row(connection, task_id)["published_json"])
            team_id = str(proposal_input.teamId)
            team = self._team(connection, team_id)
            timestamp = utc_now()
            proposal = Proposal(
                **proposal_input.model_dump(exclude={"teamId"}),
                id=str(uuid4()), taskId=task_id, teamId=team_id, team=team,
                prototypeIsPlaceholder=is_placeholder_url(proposal_input.prototypeUrl),
                status="submitted", decisionComment="", createdAt=timestamp, updatedAt=timestamp,
                taskTitle=task.fields.title,
            )
            if attachment is not None:
                name, content = attachment
                proposal.attachments = [ProposalAttachment(id=str(uuid4()), name=name, size=len(content), createdAt=timestamp)]
            connection.execute("INSERT INTO proposals(id, task_id, team_id, proposal_json) VALUES (?, ?, ?, ?)", (
                proposal.id, task_id, team_id, proposal.model_dump_json(),
            ))
            if attachment is not None:
                # The proposal and file commit together, or neither is saved.
                connection.execute("INSERT INTO proposal_attachments(id, proposal_id, name, content, created_at) VALUES (?, ?, ?, ?, ?)", (
                    proposal.attachments[0].id, proposal.id, name, content, timestamp,
                ))
        return proposal

    def attachment(self, proposal_id: str, attachment_id: str, *, role: str, team_id: str | None) -> tuple[str, bytes]:
        with self.store.connection() as connection:
            row = connection.execute("SELECT task_id, team_id FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            if row is None:
                raise StoreError(404, "Отклик не найден")
            if role == "business":
                Store._owned_row(connection, row["task_id"])
            elif team_id != row["team_id"]:
                raise StoreError(403, "Файл доступен только команде, отправившей отклик")
            result = connection.execute("SELECT name, content FROM proposal_attachments WHERE id = ? AND proposal_id = ?", (attachment_id, proposal_id)).fetchone()
            if result is None:
                raise StoreError(404, "Файл не найден")
            return result["name"], bytes(result["content"])

    def for_team(self, team_id: str) -> list[Proposal]:
        with self.store.connection() as connection:
            self._team(connection, team_id)
            rows = connection.execute("SELECT proposal_json FROM proposals WHERE team_id = ?", (team_id,)).fetchall()
            result = [self._proposal(connection, row) for row in rows]
        return sorted(result, key=lambda proposal: (proposal.createdAt, proposal.id), reverse=True)

    def for_task(self, task_id: str) -> list[Proposal]:
        with self.store.connection() as connection:
            Store._owned_row(connection, task_id)
            rows = connection.execute("SELECT proposal_json FROM proposals WHERE task_id = ?", (task_id,)).fetchall()
            result = [self._proposal(connection, row) for row in rows]
        return sorted(result, key=lambda proposal: (proposal.createdAt, proposal.id), reverse=True)

    def decide(self, proposal_id: str, decision: ProposalDecisionInput) -> Proposal:
        with self.store.connection(write=True) as connection:
            row = connection.execute("""
                SELECT proposals.proposal_json FROM proposals
                JOIN tasks ON tasks.id = proposals.task_id
                WHERE proposals.id = ? AND tasks.owner_id = ?
            """, (proposal_id, DEMO_OWNER)).fetchone()
            if row is None:
                raise StoreError(404, "Отклик не найден")
            proposal = self._proposal(connection, row)
            proposal.status = decision.status
            proposal.decisionComment = decision.comment
            proposal.updatedAt = utc_now()
            connection.execute("UPDATE proposals SET proposal_json = ? WHERE id = ?", (proposal.model_dump_json(), proposal_id))
        return proposal


def _repository(request: Request) -> ProposalRepository:
    return ProposalRepository(request.app.state.store)


@router.get("/teams", response_model=list[Team], response_model_exclude_none=True)
def list_teams(request: Request):
    return _repository(request).teams()


@router.post("/tasks/{task_id}/proposals", response_model=Proposal, response_model_exclude_none=True, status_code=201, dependencies=[Depends(_student)])
def submit_proposal(task_id: UUID, proposal_input: ProposalInput, request: Request):
    return _repository(request).submit(str(task_id), proposal_input)


@router.post("/tasks/{task_id}/proposals/upload", response_model=Proposal, response_model_exclude_none=True, status_code=201, dependencies=[Depends(_student)], openapi_extra={
    "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["proposal", "file"], "properties": {
            "proposal": {"type": "string", "description": "JSON объекта ProposalInput"},
            "file": {"type": "string", "format": "binary", "description": "PDF до 10 МиБ"},
        },
    }}}},
})
async def submit_proposal_upload(task_id: UUID, request: Request):
    proposal_input, attachment = await read_proposal_upload(request)
    return await run_in_threadpool(_repository(request).submit, str(task_id), proposal_input, attachment)


@router.get("/proposals/{proposal_id}/attachments/{attachment_id}")
def download_attachment(proposal_id: UUID, attachment_id: UUID, request: Request, role: DemoRole = None, teamId: UUID | None = None):
    if role not in ("student", "business"):
        raise HTTPException(status_code=403, detail="Выберите тестовую роль для скачивания файла")
    name, content = _repository(request).attachment(str(proposal_id), str(attachment_id), role=role, team_id=str(teamId) if teamId else None)
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=proposal.pdf; filename*=UTF-8''{quote(name, safe='')}",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
        "Cache-Control": "private, no-store",
    })


@router.get("/proposals", response_model=list[Proposal], response_model_exclude_none=True)
def list_proposals(request: Request, teamId: UUID | None = None, taskId: UUID | None = None, role: DemoRole = None):
    if (teamId is None) == (taskId is None):
        raise HTTPException(status_code=422, detail="Укажите ровно один фильтр: teamId или taskId")
    if teamId is not None:
        _student(role)
        return _repository(request).for_team(str(teamId))
    _business(role)
    return _repository(request).for_task(str(taskId))


@router.put("/proposals/{proposal_id}/decision", response_model=Proposal, response_model_exclude_none=True, dependencies=[Depends(_business)])
def decide_proposal(proposal_id: UUID, decision: ProposalDecisionInput, request: Request):
    return _repository(request).decide(str(proposal_id), decision)
