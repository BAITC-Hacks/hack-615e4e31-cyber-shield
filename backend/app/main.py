"""HTTP API for the first MVP stage; demo roles are deliberately not authentication."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .domain import calculate_rating
from .config import load_local_env
from .semantic_quality import SemanticReviewError, evaluate_semantic, semantic_configured
from .ai import router as ai_router
from .description_expansion import router as description_expansion_router
from .models import DecisionInput, Quest, Rating, RatingInput, Readiness, SkillsInput, StudentProfile, Task, TaskInput
from .store import Store, StoreError
from .proposals import router as proposals_router
from .rewards import router as rewards_router

DemoRole = Annotated[str | None, Header(alias="X-Demo-Role")]


def require_business(role: DemoRole = None) -> None:
    if role != "business":
        raise HTTPException(status_code=403, detail="Выберите тестовую роль «Бизнес»")


def require_student(role: DemoRole = None) -> None:
    if role != "student":
        raise HTTPException(status_code=403, detail="Выберите тестовую роль «Студент»")


def create_app(db_path: str | Path | None = None) -> FastAPI:
    load_local_env()
    resolved_path = db_path or os.environ.get("APP_DB_PATH") or Path(__file__).resolve().parents[1] / "data" / "hackalem.sqlite3"
    store = Store(resolved_path)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        store.initialize()
        yield

    application = FastAPI(title="HackAlem · часть 1", version="1.0.0", lifespan=lifespan)
    application.include_router(ai_router, dependencies=[Depends(require_business)])
    application.include_router(description_expansion_router, dependencies=[Depends(require_business)])
    application.include_router(proposals_router)
    application.include_router(rewards_router)
    application.state.store = store
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-Demo-Role"],
    )

    @application.exception_handler(StoreError)
    async def handle_store_error(request: Request, error: StoreError):
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})

    @application.exception_handler(SemanticReviewError)
    async def handle_semantic_error(request: Request, error: SemanticReviewError):
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @application.get("/api/ai/status", dependencies=[Depends(require_business)])
    def ai_status():
        return {
            "configured": semantic_configured(),
            "model": os.environ.get("OPENAI_RATING_MODEL", "").strip() or os.environ.get("OPENAI_MODEL", "").strip() or "gpt-4.1-mini",
        }

    @application.get("/api/health")
    def health():
        return {"status": "ok", "stage": 1}

    @application.get("/api/demo-data")
    def demo_data():
        from .seed import demo_dataset
        return demo_dataset()

    @application.get("/api/tasks", response_model=list[Task])
    def tasks(
        view: Literal["business"] | None = None,
        topic: Annotated[str | None, Query(max_length=80)] = None,
        readiness: Readiness | None = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        role: DemoRole = None,
    ):
        if view == "business":
            require_business(role)
        return store.list_tasks(business=view == "business", topic=topic, readiness=readiness, q=q)

    @application.get("/api/tasks/{task_id}", response_model=Task)
    def task(task_id: UUID, view: Literal["business"] | None = None, role: DemoRole = None):
        if view == "business":
            require_business(role)
        return store.get_task(str(task_id), business=view == "business")

    @application.post("/api/tasks", response_model=Task, status_code=201, dependencies=[Depends(require_business)])
    def create_task(task_input: TaskInput):
        return store.create_task(task_input)

    @application.put("/api/tasks/{task_id}", response_model=Task, dependencies=[Depends(require_business)])
    def update_task(task_id: UUID, task_input: TaskInput):
        return store.update_task(str(task_id), task_input)

    @application.post("/api/tasks/{task_id}/confirm", response_model=Task, dependencies=[Depends(require_business)])
    def confirm_task(task_id: UUID):
        snapshot = store.get_task(str(task_id), business=True)
        # Network calls happen before taking the SQLite write lock. A concurrent
        # edit invalidates this review rather than confirming different fields.
        quality = evaluate_semantic(snapshot.fields) if semantic_configured() else None
        return store.confirm_task(str(task_id), quality=quality, expected_revision=snapshot.revision)

    @application.post("/api/tasks/{task_id}/publish", response_model=Task, dependencies=[Depends(require_business)])
    def publish_task(task_id: UUID):
        return store.publish_task(str(task_id), require_semantic=semantic_configured())

    @application.post("/api/rating/preview", response_model=Rating)
    def preview_rating(rating_input: RatingInput):
        return calculate_rating(rating_input.fields)

    @application.post("/api/rating/review", response_model=Rating, dependencies=[Depends(require_business)])
    def review_rating(rating_input: RatingInput):
        return calculate_rating(rating_input.fields, quality=evaluate_semantic(rating_input.fields))

    @application.get("/api/profiles", response_model=list[StudentProfile])
    def profiles():
        return store.list_profiles()

    @application.put("/api/profiles/{profile_id}/skills", response_model=StudentProfile, dependencies=[Depends(require_student)])
    def update_skills(profile_id: UUID, skills_input: SkillsInput):
        return store.update_skills(str(profile_id), skills_input.skills)

    @application.get("/api/quests", response_model=list[Quest])
    def quests(profileId: UUID):
        return store.list_quests(str(profileId))

    @application.post("/api/quests/{task_id}/decision", dependencies=[Depends(require_student)])
    def decision(task_id: UUID, decision_input: DecisionInput):
        try:
            profile_id = str(UUID(decision_input.profileId))
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Некорректный идентификатор профиля") from error
        store.record_decision(str(task_id), profile_id, decision_input.decision)
        return {"ok": True}

    @application.get("/api/saved", response_model=list[Task])
    def saved(profileId: UUID):
        return store.list_saved(str(profileId))

    return application


app = create_app()
