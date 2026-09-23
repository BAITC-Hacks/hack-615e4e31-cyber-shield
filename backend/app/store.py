"""SQLite persistence with separate private drafts and immutable public snapshots."""

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator, Literal
from uuid import uuid4

from .domain import calculate_rating
from .models import QualityReport, Quest, Readiness, StudentProfile, Task, TaskInput

DEMO_OWNER = "business-demo"


class StoreError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def make_draft(task_input: TaskInput, *, task_id: str | None = None) -> Task:
    return Task(
        **task_input.model_dump(),
        id=task_id or str(uuid4()),
        published=False,
        confirmed=False,
        hasUnpublishedChanges=False,
        rating=calculate_rating(task_input.fields, confirmed=False),
        previewRating=calculate_rating(task_input.fields),
        revision=1,
        publishedRevision=None,
        updatedAt=utc_now(),
    )


def sort_tasks(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (-task.rating.score, task.id))


class Store:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path).expanduser().resolve()

    @contextmanager
    def connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection(write=True) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    draft_json TEXT NOT NULL,
                    published_json TEXT
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS tasks_owner ON tasks(owner_id)")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY,
                    profile_json TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS quest_decisions (
                    profile_id TEXT NOT NULL REFERENCES profiles(id),
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    decision TEXT NOT NULL CHECK(decision IN ('saved', 'dismissed')),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (profile_id, task_id)
                )
            """)
            connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS fixture_records (section TEXT NOT NULL, source_id TEXT NOT NULL, record_json TEXT NOT NULL, PRIMARY KEY(section, source_id))")
            version = connection.execute("SELECT value FROM metadata WHERE key = ?", ("seed_version",)).fetchone()
            if version is None or version["value"] != "2":
                from .seed import seed_database

                seed_database(connection)
                connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)", ("seed_version", "2"))
            from .quality import QUALITY_VERSION

            rating_version = connection.execute("SELECT value FROM metadata WHERE key = ?", ("rating_version",)).fetchone()
            if rating_version is None or rating_version["value"] != str(QUALITY_VERSION):
                # Recalculate each snapshot from its own fields. Never publish draft edits.
                for row in connection.execute("SELECT id, draft_json, published_json FROM tasks").fetchall():
                    values = []
                    for column in ("draft_json", "published_json"):
                        if row[column] is None:
                            values.append(None)
                            continue
                        task = Task.model_validate_json(row[column])
                        task.rating = calculate_rating(task.fields, confirmed=task.confirmed, confirmed_fields=task.confirmedFields)
                        task.previewRating = calculate_rating(task.fields)
                        values.append(task.model_dump_json())
                    connection.execute("UPDATE tasks SET draft_json = ?, published_json = ? WHERE id = ?", (*values, row["id"]))
                connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)", ("rating_version", str(QUALITY_VERSION)))
            from .proposals import initialize_proposals

            initialize_proposals(connection)
            from .rewards import initialize_rewards

            initialize_rewards(connection)

    @staticmethod
    def _owned_row(connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM tasks WHERE id = ? AND owner_id = ?", (task_id, DEMO_OWNER)
        ).fetchone()
        if row is None:
            raise StoreError(404, "Задача не найдена")
        return row

    @staticmethod
    def _published_row(connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT published_json FROM tasks WHERE id = ? AND published_json IS NOT NULL", (task_id,)
        ).fetchone()
        if row is None:
            raise StoreError(404, "Опубликованная задача не найдена")
        return row

    @staticmethod
    def _profile(connection: sqlite3.Connection, profile_id: str) -> StudentProfile:
        row = connection.execute("SELECT profile_json FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if row is None:
            raise StoreError(404, "Профиль не найден")
        return StudentProfile.model_validate_json(row["profile_json"])

    def list_tasks(
        self,
        *,
        business: bool = False,
        topic: str | None = None,
        readiness: Readiness | None = None,
        q: str | None = None,
    ) -> list[Task]:
        with self.connection() as connection:
            if business:
                rows = connection.execute("SELECT draft_json AS task_json FROM tasks WHERE owner_id = ?", (DEMO_OWNER,)).fetchall()
            else:
                rows = connection.execute("SELECT published_json AS task_json FROM tasks WHERE published_json IS NOT NULL").fetchall()
        tasks = [Task.model_validate_json(row["task_json"]) for row in rows]
        if topic:
            tasks = [task for task in tasks if task.topic.casefold() == topic.strip().casefold()]
        if readiness:
            tasks = [task for task in tasks if task.rating.level == readiness]
        if q and (query := q.strip().casefold()):
            tasks = [task for task in tasks if query in " ".join([
                *task.fields.model_dump().values(), task.company, task.topic, *task.requiredSkills,
            ]).casefold()]
        return sort_tasks(tasks)

    def get_task(self, task_id: str, *, business: bool = False) -> Task:
        with self.connection() as connection:
            if business:
                return Task.model_validate_json(self._owned_row(connection, task_id)["draft_json"])
            return Task.model_validate_json(self._published_row(connection, task_id)["published_json"])

    def create_task(self, task_input: TaskInput) -> Task:
        task = make_draft(task_input)
        with self.connection(write=True) as connection:
            connection.execute(
                "INSERT INTO tasks(id, owner_id, draft_json) VALUES (?, ?, ?)",
                (task.id, DEMO_OWNER, task.model_dump_json()),
            )
        return task

    def update_task(self, task_id: str, task_input: TaskInput) -> Task:
        with self.connection(write=True) as connection:
            current = Task.model_validate_json(self._owned_row(connection, task_id)["draft_json"])
            task = Task(
                **task_input.model_dump(),
                sourceId=current.sourceId,
                sourceDraftId=current.sourceDraftId,
                industry=current.industry,
                id=task_id,
                published=current.published,
                confirmed=False,
                hasUnpublishedChanges=current.published,
                rating=calculate_rating(task_input.fields, confirmed=False),
                previewRating=calculate_rating(task_input.fields),
                revision=current.revision + 1,
                publishedRevision=current.publishedRevision,
                updatedAt=utc_now(),
            )
            connection.execute("UPDATE tasks SET draft_json = ? WHERE id = ? AND owner_id = ?", (
                task.model_dump_json(), task_id, DEMO_OWNER,
            ))
        return task

    def confirm_task(self, task_id: str, *, quality: QualityReport | None = None, expected_revision: int | None = None) -> Task:
        with self.connection(write=True) as connection:
            task = Task.model_validate_json(self._owned_row(connection, task_id)["draft_json"])
            if expected_revision is not None and task.revision != expected_revision:
                raise StoreError(409, "Карточка изменилась во время проверки. Откройте текущую версию и подтвердите её снова")
            if not task.confirmed or quality is not None:
                task.confirmed = True
                task.confirmedFields = list(task.fields.model_dump())
                task.rating = calculate_rating(task.fields, quality=quality)
                task.previewRating = task.rating.model_copy(deep=True)
                task.updatedAt = utc_now()
                connection.execute("UPDATE tasks SET draft_json = ? WHERE id = ? AND owner_id = ?", (
                    task.model_dump_json(), task_id, DEMO_OWNER,
                ))
        return task

    def publish_task(self, task_id: str, *, require_semantic: bool = False) -> Task:
        with self.connection(write=True) as connection:
            task = Task.model_validate_json(self._owned_row(connection, task_id)["draft_json"])
            if not task.confirmed:
                raise StoreError(409, "Сначала подтвердите текущую версию карточки")
            if require_semantic and (task.rating.quality is None or task.rating.quality.mode != "openai"):
                raise StoreError(409, "Подключена AI-проверка. Повторно подтвердите карточку, чтобы проверить смысл перед публикацией")
            if not task.fields.title.strip():
                raise StoreError(422, "Перед публикацией укажите название задачи")
            task.published = True
            task.hasUnpublishedChanges = False
            task.publishedRevision = task.revision
            task.updatedAt = utc_now()
            serialized = task.model_dump_json()
            connection.execute("UPDATE tasks SET draft_json = ?, published_json = ? WHERE id = ? AND owner_id = ?", (
                serialized, serialized, task_id, DEMO_OWNER,
            ))
        return task

    def list_profiles(self) -> list[StudentProfile]:
        with self.connection() as connection:
            rows = connection.execute("SELECT profile_json FROM profiles ORDER BY rowid").fetchall()
        return [StudentProfile.model_validate_json(row["profile_json"]) for row in rows]

    def update_skills(self, profile_id: str, skills: list[str]) -> StudentProfile:
        with self.connection(write=True) as connection:
            profile = self._profile(connection, profile_id)
            profile.skills = skills
            connection.execute("UPDATE profiles SET profile_json = ? WHERE id = ?", (profile.model_dump_json(), profile_id))
        return profile

    def list_quests(self, profile_id: str) -> list[Quest]:
        with self.connection() as connection:
            profile = self._profile(connection, profile_id)
            rows = connection.execute("""
                SELECT published_json FROM tasks
                WHERE published_json IS NOT NULL AND id NOT IN (
                    SELECT task_id FROM quest_decisions WHERE profile_id = ?
                )
            """, (profile_id,)).fetchall()
        profile_skills = {skill.casefold() for skill in profile.skills}
        tasks = sort_tasks([Task.model_validate_json(row["published_json"]) for row in rows])
        matches = []
        for task in tasks:
            if task.rating.score < 40:
                continue
            skills_match = bool(task.requiredSkills) and all(skill.casefold() in profile_skills for skill in task.requiredSkills)
            interests = [interest for interest in profile.interests if interest.casefold() in {task.topic.casefold(), task.industry.casefold()}]
            # The supplied dataset has no required skills. Do not invent them:
            # offer an explicitly labelled interest match only when requirements are absent.
            if skills_match or (not task.requiredSkills and interests):
                matches.append(Quest(task=task, matchedSkills=task.requiredSkills if skills_match else [], matchedInterests=interests, decision=None))
        return matches[:3]

    def record_decision(self, task_id: str, profile_id: str, decision: Literal["saved", "dismissed"]) -> None:
        with self.connection(write=True) as connection:
            self._profile(connection, profile_id)
            self._published_row(connection, task_id)
            connection.execute("""
                INSERT INTO quest_decisions(profile_id, task_id, decision, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(profile_id, task_id) DO UPDATE SET decision = excluded.decision, updated_at = excluded.updated_at
            """, (profile_id, task_id, decision, utc_now()))

    def list_saved(self, profile_id: str) -> list[Task]:
        with self.connection() as connection:
            self._profile(connection, profile_id)
            rows = connection.execute("""
                SELECT tasks.published_json FROM tasks
                JOIN quest_decisions ON tasks.id = quest_decisions.task_id
                WHERE quest_decisions.profile_id = ? AND quest_decisions.decision = ?
                    AND tasks.published_json IS NOT NULL
            """, (profile_id, "saved")).fetchall()
        return sort_tasks([Task.model_validate_json(row["published_json"]) for row in rows])
