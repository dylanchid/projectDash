import aiosqlite
import json
from pathlib import Path
from typing import Any, List, Optional
from projectdash.models import User, Project, Issue, LinearWorkflowState

DB_PATH = Path("projectdash.db")

class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    avatar_url TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT,
                    issues_count INTEGER,
                    in_progress_count INTEGER,
                    blocked_count INTEGER,
                    due_date TEXT,
                    cycle TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS issues (
                    id TEXT PRIMARY KEY,
                    linear_id TEXT,
                    title TEXT NOT NULL,
                    priority TEXT,
                    status TEXT,
                    state_id TEXT,
                    team_id TEXT,
                    assignee_id TEXT,
                    points INTEGER DEFAULT 0,
                    due_date TEXT,
                    project_id TEXT,
                    FOREIGN KEY (assignee_id) REFERENCES users (id),
                    FOREIGN KEY (project_id) REFERENCES projects (id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS workflow_states (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    team_id TEXT NOT NULL,
                    team_key TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    result TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    diagnostics_json TEXT NOT NULL
                )
            """)
            try:
                await db.execute("ALTER TABLE issues ADD COLUMN due_date TEXT")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE issues ADD COLUMN linear_id TEXT")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE issues ADD COLUMN state_id TEXT")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE issues ADD COLUMN team_id TEXT")
            except aiosqlite.OperationalError:
                pass
            await db.commit()

    async def save_users(self, users: List[User]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO users (id, name, avatar_url) VALUES (?, ?, ?)",
                [(u.id, u.name, u.avatar_url) for u in users]
            )
            await db.commit()

    async def save_projects(self, projects: List[Project]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO projects (id, name, status, issues_count, in_progress_count, blocked_count, due_date, cycle) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(p.id, p.name, p.status, p.issues_count, p.in_progress_count, p.blocked_count, p.due_date, p.cycle) for p in projects]
            )
            await db.commit()

    async def save_issues(self, issues: List[Issue], project_id: Optional[str] = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO issues (id, linear_id, title, priority, status, state_id, team_id, assignee_id, points, due_date, project_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        i.id,
                        i.linear_id,
                        i.title,
                        i.priority,
                        i.status,
                        i.state_id,
                        i.team_id,
                        i.assignee.id if i.assignee else None,
                        i.points,
                        i.due_date,
                        i.project_id or project_id,
                    )
                    for i in issues
                ]
            )
            await db.commit()

    async def save_workflow_states(self, workflow_states: List[LinearWorkflowState]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM workflow_states")
            if workflow_states:
                await db.executemany(
                    "INSERT OR REPLACE INTO workflow_states (id, name, type, team_id, team_key) VALUES (?, ?, ?, ?, ?)",
                    [(s.id, s.name, s.type, s.team_id, s.team_key) for s in workflow_states],
                )
            await db.commit()

    async def get_users(self) -> List[User]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users") as cursor:
                rows = await cursor.fetchall()
                return [User(id=row["id"], name=row["name"], avatar_url=row["avatar_url"]) for row in rows]

    async def get_projects(self) -> List[Project]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM projects") as cursor:
                rows = await cursor.fetchall()
                return [Project(**dict(row)) for row in rows]

    async def get_issues(self) -> List[Issue]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            # Join with users to get assignee details
            query = """
                SELECT i.*, u.name as user_name, u.avatar_url as user_avatar 
                FROM issues i 
                LEFT JOIN users u ON i.assignee_id = u.id
            """
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                issues = []
                for row in rows:
                    assignee = None
                    if row["assignee_id"]:
                        assignee = User(id=row["assignee_id"], name=row["user_name"], avatar_url=row["user_avatar"])
                    issues.append(Issue(
                        id=row["id"],
                        title=row["title"],
                        priority=row["priority"],
                        status=row["status"],
                        assignee=assignee,
                        points=row["points"],
                        due_date=row["due_date"],
                        project_id=row["project_id"],
                        linear_id=row["linear_id"],
                        team_id=row["team_id"],
                        state_id=row["state_id"],
                    ))
                return issues

    async def get_workflow_states(self) -> List[LinearWorkflowState]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id, name, type, team_id, team_key FROM workflow_states") as cursor:
                rows = await cursor.fetchall()
                return [LinearWorkflowState(**dict(row)) for row in rows]

    async def append_sync_history(
        self,
        *,
        created_at: str,
        result: str,
        summary: str,
        diagnostics: dict[str, str],
        max_entries: int = 20,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sync_history (created_at, result, summary, diagnostics_json) VALUES (?, ?, ?, ?)",
                (created_at, result, summary, json.dumps(diagnostics, sort_keys=True)),
            )
            if max_entries > 0:
                await db.execute(
                    """
                    DELETE FROM sync_history
                    WHERE id NOT IN (
                        SELECT id FROM sync_history
                        ORDER BY id DESC
                        LIMIT ?
                    )
                    """,
                    (max_entries,),
                )
            await db.commit()

    async def get_sync_history(self, limit: int = 20) -> List[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, created_at, result, summary, diagnostics_json
                FROM sync_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                history: list[dict[str, Any]] = []
                for row in rows:
                    raw = row["diagnostics_json"]
                    try:
                        diagnostics = json.loads(raw) if raw else {}
                    except json.JSONDecodeError:
                        diagnostics = {}
                    history.append(
                        {
                            "id": row["id"],
                            "created_at": row["created_at"],
                            "result": row["result"],
                            "summary": row["summary"],
                            "diagnostics": diagnostics,
                        }
                    )
                return history
